"""Catalogue, editorial workflows and playback accounting."""
from datetime import timedelta
import io
import json
import secrets
import time
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as XML

from bs4 import BeautifulSoup

import test_platform  # Configure the isolated test application.
from app import SITE_URL, app
from extensions import limiter
from models import AdminUser, Article, Author, Category, db, utcnow
from security_test_support import authenticate_test_session
from video_media import media_fields
from video_models import ScienceVideo, VideoPlayback
from videos import SITEMAP, VIDEO_XML


class ScienceVideoTests(unittest.TestCase):
    def setUp(self):
        context = app.app_context()
        context.push()
        self.addCleanup(context.pop)
        self.addCleanup(setattr, limiter, 'enabled', limiter.enabled)
        limiter.enabled = False
        self.client = app.test_client()
        self.suffix = secrets.token_hex(5)
        self.category = Category.query.filter_by(name='Saúde').one()
        self.author = Author.query.first()
        self.url = f'https://res.cloudinary.com/video-fixture/video/upload/v10/demo/{self.suffix}.mp4'
        cloud = patch.dict('os.environ', {'CLOUDINARY_CLOUD_NAME': 'video-fixture'})
        cloud.start()
        self.addCleanup(cloud.stop)
        self.addCleanup(self.clear_videos)

    def clear_videos(self):
        db.session.rollback()
        db.session.query(VideoPlayback).delete()
        db.session.query(ScienceVideo).delete()
        db.session.commit()

    def sign_in(self, role=None):
        from governance_models import TeamAppointment, TeamMember, TeamRole

        account_id = None
        if role:
            username = f'{role}-{self.suffix}'
            account = AdminUser(username=username, display_name=username, password_hash='fixture',
                                governance_managed=True, two_factor_enabled=True, totp_secret='JBSWY3DPEHPK3PXP')
            member = TeamMember(name=username, email=username + '@example.org', admin=account,
                                status='active', accepted_at=utcnow())
            db.session.add(TeamAppointment(member=member, role=TeamRole.query.filter_by(code=role).one(),
                                           starts_on=utcnow().date()))
            db.session.commit()
            account_id = account.id
        with self.client.session_transaction() as state:
            state.clear()
            state.update(admin_authenticated=True, admin_superuser=not role, admin_last_activity_at=time.time(),
                         admin_2fa_verified=True, csrf_token='video-csrf')
            if account_id:
                state['admin_id'] = account_id
            authenticate_test_session(state)

    def form(self, **changes):
        return dict({
            'csrf_token': 'video-csrf', 'action': 'save', 'language': 'pt', 'title': 'Vídeo científico de ensaio',
            'slug': f'video-{self.suffix}', 'description': 'Descrição científica de teste.',
            'url': self.url, 'thumbnail': 'https://example.org/miniatura.jpg', 'author': 'Autoria de ensaio',
            'category_id': self.category.id, 'duration': 80, 'transcript': 'Transcrição de ensaio.',
        }, **changes)

    def article(self, status='published'):
        article = Article(title='Artigo de ensaio de vídeo', slug='artigo-video-' + self.suffix,
                          summary='Resumo com contexto sobre o vídeo.', body='Texto de ensaio. ' * 10,
                          image='https://example.org/test.jpg', cover_video=self.url, cover_mode='video_controls',
                          status=status, published_at=utcnow(), category_id=self.category.id, author_id=self.author.id)
        db.session.add(article)
        db.session.commit()
        self.addCleanup(self.remove_article, article.id)
        return article

    @staticmethod
    def remove_article(article_id):
        db.session.rollback()
        db.session.query(ScienceVideo).filter_by(article_id=article_id).delete()
        db.session.query(Article).filter_by(id=article_id).delete()
        db.session.commit()

    def make_video(self, locale='pt', **values):
        slug = f'{locale}-{self.suffix}'
        fields = dict(slug=slug, language=locale, title=f'Video {locale}',
                      description='Fixture description', thumbnail='https://example.org/thumbnail.jpg',
                      duration=80, author='Fixture author', category_id=self.category.id,
                      status='published', published_at=utcnow() - timedelta(minutes=1))
        item = ScienceVideo(**{**fields, **media_fields(self.url), **values})
        db.session.add(item)
        db.session.commit()
        return item

    def test_publish_schedule_withdraw_and_archive(self):
        self.assertEqual(self.client.get('/admin/videos').status_code, 302)
        self.sign_in('secretariat')
        self.assertEqual(self.client.get('/admin/videos').status_code, 403)
        self.sign_in('portal_editor')
        self.assertEqual(self.client.post('/admin/videos/novo', data=self.form(action='publish')).status_code, 403)
        self.assertEqual(self.client.post('/admin/videos/novo', data=self.form(csrf_token='bad')).status_code, 400)
        response = self.client.post('/admin/videos/novo', data=self.form())
        self.assertEqual(response.status_code, 302)
        video = ScienceVideo.query.one()
        route = f'/admin/videos/{video.id}'
        path = f'/videos/{video.slug}'
        self.assertEqual(self.client.get(path).status_code, 404)
        preview = self.client.get(route + '/prever')
        self.assertEqual(preview.status_code, 200)
        self.assertIn('noindex', preview.headers['X-Robots-Tag'])
        self.assertEqual(self.client.post('/admin/videos/novo', data=self.form(slug='duplicate')).status_code, 409)
        self.sign_in()
        scheduled = (utcnow() + timedelta(days=1, hours=2)).strftime('%Y-%m-%dT%H:%M')
        response = self.client.post(route, data=self.form(action='schedule', scheduled_at=scheduled, revision=video.revision))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertNotIn(path, self.client.get('/video-sitemap.xml').text)
        video.published_at = video.scheduled_at = utcnow() - timedelta(minutes=1)
        db.session.commit()
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.post(route, data=self.form(action='withdraw', revision=video.revision)).status_code, 302)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.post(route, data=self.form(action='archive', revision=video.revision)).status_code, 302)
        self.assertEqual(self.client.post(route, data=self.form(action='delete', revision=video.revision, confirm_delete='yes')).status_code, 302)
        self.assertEqual(ScienceVideo.query.count(), 0)

    def test_bilingual_seo_visibility_and_search(self):
        article = self.article()
        pt = self.make_video(article_id=article.id)
        en = self.make_video('en', article_id=article.id, series=pt.series)
        with patch('internationalization.interface_ready', return_value=True):
            doc = BeautifulSoup(self.client.get(f'/en/videos/{en.slug}').text, 'html.parser')
            self.assertEqual(doc.h1.text, en.title)
            self.assertEqual(doc.select_one('link[rel=canonical]')['href'], f'{SITE_URL}/en/videos/{en.slug}')
            self.assertEqual(doc.select_one('link[hreflang=pt-MZ]')['href'], f'{SITE_URL}/videos/{pt.slug}')
            self.assertEqual(doc.select_one('#mainNav [href="/en/videos"]').text, 'Science Videos')
            schema = next(json.loads(el.text) for el in doc.select('script[type="application/ld+json"]')
                          if json.loads(el.text).get('@type') == 'VideoObject')
            self.assertEqual(schema['duration'], 'PT80S')
            self.assertEqual(schema['name'], en.title)
            self.assertEqual(doc.select_one('video source')['src'], schema['contentUrl'])
            url = doc.select_one('.language-selector [lang="pt-MZ"]')['href']
            self.assertEqual(self.client.get(url, follow_redirects=True).request.path, f'/videos/{pt.slug}')
            root = XML.fromstring(self.client.get('/video-sitemap.xml').data)
            self.assertEqual(len(root.findall(f'{{{SITEMAP}}}url')), 2)
            self.assertEqual(root.find(f'.//{{{VIDEO_XML}}}duration').text, '80')
            self.assertIn('/video-sitemap.xml', self.client.get('/robots.txt').text)
            self.assertIn('Ver vídeo', self.client.get(f'/artigo/{article.slug}').text)
            self.assertIn(en.title, self.client.get('/en/videos?q=Video&ordem=popular').text)
            article.status = 'draft'
            db.session.commit()
            self.assertEqual(self.client.get(f'/en/videos/{en.slug}').status_code, 404)
            self.assertNotIn(en.slug, self.client.get('/video-sitemap.xml').text)

    def test_import_is_explicit_and_does_not_upload_or_duplicate(self):
        article = self.article('draft')
        self.sign_in()
        listing = self.client.get('/admin/videos/importar')
        self.assertEqual(listing.status_code, 200)
        self.assertIn(article.title, listing.text)
        payload = dict(csrf_token='video-csrf', articles=article.id)
        with patch('storage.cloudinary.uploader.upload') as upload:
            for _ in range(2):
                self.assertEqual(self.client.post('/admin/videos/importar', data=payload).status_code, 302)
            upload.assert_not_called()
        video = ScienceVideo.query.one()
        self.assertEqual((video.status, video.article_id, video.url), ('draft', article.id, article.cover_video))
        self.assertEqual(self.client.post(f'/admin/videos/{video.id}', data=self.form(
            action='publish', article_slug=article.slug, revision=video.revision)).status_code, 400)

    def test_article_form_creates_opted_in_draft_without_reupload(self):
        self.sign_in()
        form = dict(csrf_token='video-csrf', title='Artigo com vídeo de ensaio ' + self.suffix,
                    summary='Resumo de ensaio para a capa.', body='Texto da notícia de ensaio. ' * 4,
                    status='draft', author_id=self.author.id, category_id=self.category.id,
                    cover_video=self.url, cover_mode='video_controls')
        self.assertEqual(self.client.post('/admin/artigos/novo', data=form).status_code, 302)
        first = Article.query.filter_by(title=form['title']).one()
        self.addCleanup(self.remove_article, first.id)
        self.assertEqual(ScienceVideo.query.count(), 0)
        with patch('admin.upload_article_video') as upload:
            response = self.client.post(f'/admin/artigos/{first.id}/editar', data={
                **form, 'science_video_opt_in': 'yes', 'science_video_title': 'Vídeo de teste opt-in',
            })
            self.assertEqual(response.status_code, 302)
            self.assertIn('/admin/videos/', response.location)
            upload.assert_not_called()
        item = ScienceVideo.query.one()
        self.assertEqual((item.url, item.status), (self.url, 'draft'))

    def test_independent_upload_and_metadata_use_the_existing_storage(self):
        self.sign_in()
        metadata = dict(duration=30, width=1280, height=720)
        with patch('video_admin.upload_article_video', return_value=(self.url, metadata)) as upload:
            response = self.client.post('/admin/videos/novo', data=self.form(
                url='', video_file=(io.BytesIO(b'synthetic media'), 'video.mp4')))
            self.assertEqual(response.status_code, 302)
            upload.assert_called_once()
            self.assertTrue(upload.call_args.kwargs['include_metadata'])
        item = ScienceVideo.query.one()
        self.assertEqual((item.url, item.duration, item.width, item.height), (self.url, 30, 1280, 720))
        with patch('video_admin.cloudinary_details', return_value=dict(duration=50, width=1920, height=1080)):
            response = self.client.post(f'/admin/videos/{item.id}', data=self.form(action='metadata', revision=item.revision))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(BeautifulSoup(response.text, 'html.parser').select_one('input[name=duration]')['value'], '50')
        self.assertEqual(item.duration, 30)

    def test_real_playback_counts_and_validation(self):
        from videos import playback_signer
        video = self.make_video()
        token = playback_signer().dumps([video.id, self.suffix])
        for event, seconds in [('view', 0), ('start', 0), ('progress', 17), ('end', 80), ('progress', 40)]:
            response = self.client.post('/api/videos/playback', json=dict(token=token, event=event, seconds=seconds))
            self.assertEqual(response.status_code, 204)
        item = db.session.query(VideoPlayback).one()
        self.assertEqual((item.seconds, item.started, item.completed), (80, True, True))
        self.assertEqual(self.client.post('/api/videos/playback', json=dict(token='invalid', event='view')).status_code, 400)
        self.sign_in()
        self.assertIn('100.0', self.client.get('/admin/videos?ui=en').text)
        for value in ('https://not-cloudinary.example/fake.mp4', 'javascript:alert(1)',
                      'https://www.youtube.com.evil.test/watch?v=OzLX5u3kMyU',
                      'https://res.cloudinary.com/video-fixture/video/upload/v10/../test.mp4'):
            with self.assertRaises(ValueError):
                media_fields(value)
