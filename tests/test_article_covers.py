"""Covers extend the existing editor, private permissions and publication lifecycle."""
import io
import json
import os
import unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from bs4 import BeautifulSoup
from werkzeug.datastructures import FileStorage
from cloudinary.exceptions import Error as CloudinaryError
import test_article_history as fixtures
from app import app
from models import Article, db, utcnow
from governance_models import ArticleRevision, ArticleWorkflow
from storage import upload_article_video, VideoUploadError
from cover_media import owned_cloudinary_video

CLOUD='cover-fixture'
VIDEO=f'https://res.cloudinary.com/{CLOUD}/video/upload/v1/sample.mp4'
OTHER=f'https://res.cloudinary.com/{CLOUD}/video/upload/v2/another.mp4'


class ArticleCoverTests(unittest.TestCase):
    tearDown=fixtures.ArticleHistoryTests.tearDown
    member=fixtures.ArticleHistoryTests.member
    article=fixtures.ArticleHistoryTests.article
    signin=fixtures.ArticleHistoryTests.signin
    post=fixtures.ArticleHistoryTests.post

    def setUp(self):
        fixtures.ArticleHistoryTests.setUp(self)
        env=patch.dict(os.environ,{'CLOUDINARY_CLOUD_NAME':CLOUD,'CLOUDINARY_API_KEY':'fixture','CLOUDINARY_API_SECRET':'fixture'})
        env.start();self.addCleanup(env.stop)

    def edit(self,article,**extra):
        values={name:getattr(article,name) or '' for name in ('title','summary','body','references','keywords','doi','image','cover_video','slug','background')}
        values.update(author_id=article.author_id,category_id=article.category_id,read_minutes=article.read_minutes,
                      status=article.status,version_token=article.updated_at.isoformat(),cover_mode=article.cover_format)
        values.update(extra)
        return self.post(f'/admin/artigos/{article.id}/editar',**values)

    def public(self,article):
        return app.test_client().get('/artigo/'+article.slug)

    def result(self,**extra):
        return dict(secure_url=VIDEO,resource_type='video',width=160,height=80,duration=2,format='mp4',**extra)

    def test_legacy_images_and_controlled_videos_require_no_reediting(self):
        owner=self.member();article=self.article(owner);article.status='published';article.image='https://example.org/cover.jpg';db.session.commit()
        self.assertEqual(article.cover_mode,'auto');self.assertEqual(article.cover_format,'image')
        self.assertIsNotNone(BeautifulSoup(self.public(article).data,'html.parser').select_one('.article-cover-image'))
        article.cover_video='https://example.org/legacy.mp4';db.session.commit()
        self.assertEqual(article.cover_format,'video_controls')
        soup=BeautifulSoup(self.public(article).data,'html.parser');self.assertIsNotNone(soup.select_one('video[controls]'));self.assertIsNone(soup.select_one('video[autoplay]'))
        article.cover_video='https://youtu.be/dQw4w9WgXcQ';db.session.commit()
        self.assertIsNotNone(BeautifulSoup(self.public(article).data,'html.parser').select_one('.article-main-video iframe'))

    def test_modes_save_reopen_without_losing_other_assets_and_explicit_removal(self):
        owner=self.member();article=self.article(owner);article.image='https://example.org/poster.jpg';db.session.commit();self.signin(owner.admin)
        for mode in ['video_animated','video_controls','image','video_animated']:
            self.assertEqual(self.edit(article,cover_mode=mode,cover_video=VIDEO).status_code,302)
            db.session.expire_all();self.assertEqual(article.cover_mode,mode);self.assertEqual(article.cover_video,VIDEO)
            self.assertEqual(article.image,'https://example.org/poster.jpg')
            soup=BeautifulSoup(self.client.get(f'/admin/artigos/{article.id}/editar').data,'html.parser')
            self.assertEqual(soup.select_one('select[name=cover_mode] option[selected]')['value'],mode)
        self.assertEqual(self.edit(article,remove_cover_video='yes').status_code,302)
        self.assertEqual((article.cover_mode,article.cover_video),('image',''));self.assertTrue(article.image)

    def test_animated_markup_fallback_seo_and_lists_stay_static(self):
        owner=self.member();article=self.article(owner);article.cover_mode='video_animated';article.cover_video=VIDEO
        article.image='https://example.org/poster.jpg';article.status='published';db.session.commit()
        soup=BeautifulSoup(self.public(article).data,'html.parser');video=soup.select_one('video.cover-video')
        self.assertIsNotNone(video)
        for attr in ['autoplay','muted','loop','playsinline']:self.assertTrue(video.has_attr(attr))
        self.assertEqual(video['preload'],'none');self.assertNotIn('src',video.attrs);self.assertNotIn('controls',video.attrs)
        self.assertIn('q_auto:good,w_1280,c_limit,ac_none',video['data-src'])
        self.assertEqual(soup.select_one('.cover-poster')['src'],article.image)
        self.assertEqual(soup.select_one('meta[property="og:image"]')['content'],article.image)
        self.assertEqual(soup.select_one('meta[name="twitter:image"]')['content'],article.image)
        data=next(value for value in (json.loads(node.string) for node in soup.select('script[type="application/ld+json"]')) if value.get('@type')=='Article')
        self.assertEqual(data['@type'],'Article');self.assertNotIn('VideoObject',str(data))
        self.assertTrue(soup.select_one('link[rel=canonical]')['href'].endswith('/artigo/'+article.slug))
        article.image='';db.session.commit()
        self.assertIn('/static/img/image-fallback.svg',BeautifulSoup(self.public(article).data,'html.parser').select_one('.cover-poster')['src'])
        for path in ['/','/artigos']:
            page=app.test_client().get(path);self.assertEqual(page.status_code,200)
            self.assertFalse(BeautifulSoup(page.data,'html.parser').select('video.cover-video,[data-article-cover]'))

    def test_preview_blobs_are_allowed_without_weakening_script_policy(self):
        owner=self.member();article=self.article(owner);self.signin(owner.admin)
        response=self.client.get(f'/admin/artigos/{article.id}/editar')
        policy=response.headers['Content-Security-Policy']
        self.assertIn("img-src 'self' data: blob: https:",policy)
        self.assertIn("media-src 'self' blob: https:",policy)
        script=next(part.strip() for part in policy.split(';') if part.strip().startswith('script-src '))
        self.assertIn("'strict-dynamic'",script);self.assertNotIn('blob:',script)
        self.assertIn('script-src-attr \'none\'',policy)

    def test_invalid_modes_and_untrusted_video_urls_cannot_change_cover(self):
        owner=self.member();article=self.article(owner);self.signin(owner.admin)
        for mode,url in [('bad-class','javascript:alert(1)'),('video_animated','https://evil.test/test.mp4'),('video_animated','https://res.cloudinary.com/another/video/upload/test.mp4'),('video_animated','https://youtu.be/dQw4w9WgXcQ'),('video_controls','https://evil.test/new.mp4'),('video_animated','')]:
            self.assertEqual(self.edit(article,cover_mode=mode,cover_video=url).status_code,200)
            self.assertEqual(article.cover_mode,'auto');self.assertEqual(article.cover_video,'')
        self.assertFalse(owned_cloudinary_video(f'https://res.cloudinary.com/{CLOUD}/video/upload/../private/test.mp4'))
        self.assertFalse(owned_cloudinary_video(f'https://res.cloudinary.com.evil.test/{CLOUD}/video/upload/test.mp4'))
        article.cover_video='https://example.org/old.mp4';db.session.commit()
        self.assertEqual(self.edit(article,cover_mode='video_controls').status_code,302)
        self.assertEqual(self.edit(article,cover_mode='video_controls',cover_video='https://youtu.be/dQw4w9WgXcQ').status_code,302)

    def test_private_permissions_csrf_stale_version_and_approval_guard(self):
        owner=self.member();other=self.member();article=self.article(owner);self.signin(other.admin)
        with patch('admin.upload_article_video') as upload:
            self.assertEqual(self.edit(article,cover_mode='video_animated',cover_video=VIDEO).status_code,404);upload.assert_not_called()
        self.signin(owner.admin)
        self.assertEqual(self.client.post(f'/admin/artigos/{article.id}/editar',data={'cover_mode':'image'}).status_code,400)
        self.assertEqual(self.edit(article,cover_mode='video_animated',cover_video=VIDEO,version_token='old').status_code,409)
        flow=db.session.get(ArticleWorkflow,article.id);article.status=flow.stage='published';flow.approved_at=flow.reviewed_at=utcnow();db.session.commit();self.signin(self.primary)
        self.assertEqual(self.edit(article,cover_mode='video_animated',cover_video=VIDEO).status_code,409)
        self.assertEqual(article.cover_video,'')

    def test_history_autosave_and_scheduled_publication_preserve_cover(self):
        owner=self.member();article=self.article(owner);self.signin(self.primary)
        self.assertEqual(self.edit(article,cover_mode='video_animated',cover_video=VIDEO).status_code,302)
        revision=ArticleRevision.query.filter_by(article_id=article.id).order_by(ArticleRevision.number.desc()).first()
        self.assertEqual(revision.snapshot['cover_mode'],'video_animated')
        values={name:getattr(article,name) or '' for name in ('title','summary','body','references','keywords','doi')}
        values.update(body='Texto novo de rascunho. '*10,read_minutes=5,version_token=article.updated_at.isoformat(),cover_mode='image',cover_video='')
        self.assertEqual(self.post(f'/admin/artigos/{article.id}/rascunho',**values).status_code,200)
        self.assertEqual((article.cover_mode,article.cover_video),('video_animated',VIDEO))
        flow=db.session.get(ArticleWorkflow,article.id);flow.approved_at=flow.reviewed_at=utcnow();flow.stage='approved';db.session.commit()
        self.assertEqual(self.edit(article,status='scheduled',scheduled_at=(utcnow()+timedelta(days=2)).strftime('%Y-%m-%dT%H:%M')).status_code,302)
        self.assertEqual(self.public(article).status_code,404)
        article.scheduled_at=utcnow()-timedelta(minutes=2);db.session.commit();Article.publish_due_scheduled()
        self.assertEqual(article.cover_mode,'video_animated');self.assertIsNotNone(BeautifulSoup(self.public(article).data,'html.parser').select_one('video[autoplay]'))
        baseline=ArticleRevision.query.filter_by(article_id=article.id).order_by(ArticleRevision.number).first()
        old=dict(baseline.snapshot);old.pop('cover_mode',None);baseline.snapshot=old;db.session.commit()
        self.assertEqual(self.post(f'/admin/artigos/{article.id}/historico/{baseline.id}/recuperar',confirm='yes',version_token=article.updated_at.isoformat()).status_code,303)
        self.assertEqual(article.cover_format,'image');self.assertEqual(article.status,'draft')
        self.assertEqual(self.post(f'/admin/artigos/{article.id}/historico/{revision.id}/recuperar',confirm='yes',version_token=article.updated_at.isoformat()).status_code,303)
        self.assertEqual((article.cover_mode,article.cover_video),('video_animated',VIDEO))

    def test_cover_upload_decodes_video_through_existing_cloudinary_and_handles_failures(self):
        payload=(Path(__file__).parent/'fixtures/article-cover.mp4').read_bytes()
        def file():return FileStorage(stream=io.BytesIO(payload),filename='cover.mp4',content_type='video/mp4')
        with patch('storage.cloudinary.uploader.upload',return_value=self.result()) as upload:
            self.assertEqual(upload_article_video(file(),cover=True),VIDEO)
            self.assertEqual(upload.call_args.kwargs['resource_type'],'video');self.assertEqual(upload.call_args.kwargs['format'],'mp4')
            self.assertFalse(upload.call_args.kwargs['overwrite'])
        for response in [{},dict(secure_url=VIDEO,resource_type='video',width=0,height=0,duration=2),dict(secure_url=VIDEO,resource_type='image',width=160,height=80,duration=2)]:
            with patch('storage.cloudinary.uploader.upload',return_value=response),self.assertRaises(VideoUploadError):upload_article_video(file(),cover=True)
        for error in [CloudinaryError('provider rejected input'),TimeoutError('interrupted')]:
            with patch('storage.cloudinary.uploader.upload',side_effect=error),self.assertRaises(VideoUploadError):upload_article_video(file(),cover=True)
        with patch.dict(os.environ,{'CLOUDINARY_API_SECRET':''}),self.assertRaises(VideoUploadError):upload_article_video(file(),cover=True)

    def test_invalid_cover_files_rejected_before_cloudinary(self):
        for payload,name,mime in [(b'not-video','cover.mp4','video/mp4'),(b'ftypcode','cover.exe','video/mp4'),(b'\x00\x00\x00\x18ftypisom','cover.mp4','text/html'),(b'\x1a\x45\xdf\xa3video','cover.webm','video/mp4')]:
            with patch('storage.cloudinary.uploader.upload') as upload,self.assertRaises(VideoUploadError):
                upload_article_video(FileStorage(stream=io.BytesIO(payload),filename=name,content_type=mime),cover=True)
            upload.assert_not_called()
        with patch('storage.MAX_VIDEO_BYTES',8),patch('storage.cloudinary.uploader.upload') as upload,self.assertRaises(VideoUploadError):
            upload_article_video(FileStorage(stream=io.BytesIO(b'OggS12345'),filename='cover.ogg',content_type='video/ogg'),cover=True)
        upload.assert_not_called()

    def test_failed_upload_preserves_saved_article_and_retries_existing_form(self):
        owner=self.member();article=self.article(owner);article.cover_mode='video_controls';article.cover_video=VIDEO;db.session.commit();self.signin(owner.admin)
        with patch('admin.upload_article_video',side_effect=VideoUploadError('Não foi possível carregar o vídeo. Tente novamente.')):
            response=self.edit(article,cover_mode='video_animated',cover_video_file=(io.BytesIO(b'video'),'cover.mp4'))
        self.assertEqual(response.status_code,200);self.assertIn('Tente novamente',response.text)
        self.assertEqual((article.cover_mode,article.cover_video),('video_controls',VIDEO))
        result=self.result();result['secure_url']=OTHER
        payload=(Path(__file__).parent/'fixtures/article-cover.mp4').read_bytes()
        with patch('storage.cloudinary.uploader.upload',return_value=result) as upload:
            self.assertEqual(self.edit(article,cover_mode='video_animated',cover_video_file=(io.BytesIO(payload),'cover.mp4')).status_code,302)
            self.assertEqual(upload.call_args.kwargs['resource_type'],'video')
        self.assertEqual((article.cover_mode,article.cover_video),('video_animated',OTHER))
