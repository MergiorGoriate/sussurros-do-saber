"""Public and editorial integration tests for Science News."""
from datetime import date, timedelta
import secrets
import time
import unittest
from xml.etree import ElementTree

from bs4 import BeautifulSoup

import test_platform  # Set up the isolated application database before importing it.
from app import app, SITE_URL
from extensions import limiter
from governance_models import GovernanceAudit, TeamAppointment, TeamMember, TeamRole
from models import AdminUser, Article, Author, Category, db, utcnow
from news_models import NewsStory, NewsVersion
from security_test_support import authenticate_test_session


class ScienceNewsTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        self.previous_limiter = limiter.enabled
        limiter.enabled = False
        self.addCleanup(self.context.pop)
        self.addCleanup(setattr, limiter, 'enabled', self.previous_limiter)
        self.token = secrets.token_hex(4)
        self.author = Author(name='Autoria de ensaio', slug='autor-news-' + self.token)
        self.topic = Category.query.filter_by(name='Saúde').one()
        self.other_topic = Category.query.filter_by(name='Ambiente').one()
        db.session.add(self.author)
        db.session.commit()
        self.client = app.test_client()
        self.addCleanup(self.remove_stories)

    def remove_stories(self):
        db.session.rollback()
        NewsVersion.query.delete()
        NewsStory.query.delete()
        db.session.commit()

    def story(self, title, *, locale='pt', story=None, offset=0, status='published', featured=False, topic=None):
        if story is None:
            story = NewsStory()
            db.session.add(story)
            db.session.flush()
        item = NewsVersion(
            story_id=story.id, language=locale, title=title, slug='news-' + secrets.token_hex(5),
            summary='Test summary' if locale == 'en' else 'Resumo de ensaio',
            body='Text for the test story' if locale == 'en' else 'Texto da notícia de ensaio',
            author=self.author, category=topic or self.topic, status=status, featured=featured,
            sources=[{'label': 'Primary source', 'url': 'https://example.org/research'}],
            published_at=utcnow() + timedelta(days=offset) if status == 'published' else None,
        )
        db.session.add(item)
        db.session.commit()
        return story, item

    def soup(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        return BeautifulSoup(response.text, 'html.parser')

    def select_language(self, document, locale):
        language = 'pt-MZ' if locale == 'pt' else 'en'
        link = document.select_one(f'.language-selector a[lang="{language}"]')
        return self.client.get(link['href'], follow_redirects=True)

    def headings(self, soup, container):
        return [card.select_one('h2, h3').get_text(strip=True)
                for card in soup.select(container + ' .news-card')]

    def test_feature_home_visibility_order_and_theme_navigation(self):
        self.assertIsNone(self.soup('/').select_one('#home-news-title'))
        self.story('Notícia escolhida', offset=-4, featured=True)
        _, current = self.story('Notícia mais recente', offset=-1)
        self.story('Notícia intermédia', offset=-2)
        self.story('Notícia de outro tema', offset=-3, topic=self.other_topic)
        self.story('Notícia futura', offset=1)
        self.story('Rascunho privado', status='draft')
        self.story('English headline', locale='en', offset=-1)

        home = self.soup('/')
        self.assertEqual(self.headings(home, '[aria-labelledby="home-news-title"]'),
                         ['Notícia mais recente', 'Notícia intermédia', 'Notícia de outro tema'])
        for card in home.select('[aria-labelledby="home-news-title"] .news-card'):
            cover = card.select_one('a.news-cover-link')
            self.assertIsNotNone(cover)
            self.assertEqual(cover['href'], card.select_one('.news-card-copy h3 a')['href'])
        index = self.soup('/noticias')
        lead_cover = index.select_one('.news-lead a.news-cover-link')
        self.assertIsNotNone(lead_cover)
        self.assertEqual(lead_cover['href'], index.select_one('.news-lead h2 a')['href'])
        self.assertEqual(self.headings(index, '.news-lead'), ['Notícia escolhida'])
        self.assertEqual(self.headings(index, '.news-grid'),
                         ['Notícia mais recente', 'Notícia intermédia', 'Notícia de outro tema'])
        self.assertEqual(index.select_one('#mainNav [href="/noticias"]').text.strip(), 'Notícias')
        self.assertEqual(self.select_language(index, 'en').request.path, '/en/news')
        self.assertEqual(self.headings(self.soup('/en/'), '[aria-labelledby="home-news-title"]'),
                         ['English headline'])
        self.client = app.test_client()
        filtered = self.soup('/noticias?tema=' + self.topic.slug)
        self.assertIsNone(filtered.select_one('.news-lead'))
        self.assertEqual(self.headings(filtered, '.news-grid'),
                         ['Notícia mais recente', 'Notícia intermédia', 'Notícia escolhida'])
        detail = self.soup(filtered.find('a', string=current.title)['href'])
        self.assertEqual(detail.select_one('.news-back')['href'], '/noticias?tema=' + self.topic.slug)
        self.assertIsNotNone(self.soup('/noticias?tema=outro').select_one('.empty-state'))
        self.assertEqual(self.client.get('/noticias').headers['Cache-Control'], 'no-store')

    def test_filter_and_page_survive_language_switch_and_detail_links(self):
        for i in range(13):
            self.story(f'Notícia {i:02d}', offset=-i - 1)
            self.story(f'Story {i:02d}', locale='en', offset=-i - 1)
        path = '/noticias?tema=' + self.topic.slug
        page = self.soup(path)
        page_two = page.select_one('a[rel=next]')['href']
        self.assertEqual(page_two, path + '&page=2')
        page = self.soup(page_two)
        self.assertEqual(self.headings(page, '.news-grid'), ['Notícia 12'])
        visible = page.find('a', string='Notícia 12')
        self.assertEqual(self.soup(visible['href']).select_one('.news-back')['href'], page_two)
        english = self.select_language(page, 'en')
        self.assertEqual(english.request.full_path, '/en/news?tema=' + self.topic.slug + '&page=2')
        self.assertEqual(self.headings(BeautifulSoup(english.text, 'html.parser'), '.news-grid'), ['Story 12'])

    def test_direct_english_route_switch_and_private_versions_in_sitemap(self):
        story, pt = self.story('Notícia em português', offset=-2)
        _, en = self.story('Science story in English', locale='en', story=story, status='draft')
        en_path = '/en/news/' + en.slug
        pt_path = '/noticias/' + pt.slug
        self.assertEqual(self.client.get(en_path).status_code, 404)
        index = self.soup('/en/news')
        self.assertEqual(index.h1.text.strip(), 'Science News')
        self.assertEqual(index.select_one('#mainNav [href="/en/news"]').text.strip(), 'News')
        self.assertEqual(index.select_one('label[for="news-topic"]').text, 'Topic')
        self.assertNotIn(en.title, index.get_text())
        notice = self.select_language(self.soup(pt_path), 'en')
        self.assertEqual(notice.request.path, pt_path)
        page = BeautifulSoup(notice.text, 'html.parser')
        self.assertEqual(page.h1.text, pt.title)
        self.assertIn('This article is not yet available in English', page.select_one('.news-language-notice').text)
        self.assertNotIn(en_path, self.client.get('/sitemap.xml').text)

        en.status, en.published_at = 'published', utcnow()
        db.session.commit()
        response = self.select_language(self.soup(pt_path), 'en')
        self.assertEqual(response.request.path, en_path)
        page = BeautifulSoup(response.text, 'html.parser')
        self.assertEqual(page.h1.text, en.title)
        self.assertIn(en.summary, page.select_one('.article-summary').text)
        self.assertIn(en.body, page.select_one('.news-body').text)
        self.assertEqual(page.select_one('link[rel=canonical]')['href'], SITE_URL + en_path)
        self.assertEqual(page.select_one('link[hreflang=pt-MZ]')['href'], SITE_URL + pt_path)
        self.assertEqual(page.select_one('.news-sources a')['href'], en.sources[0]['url'])
        namespace = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        sitemap = ElementTree.fromstring(self.client.get('/sitemap.xml').data)
        urls = [node.text for node in sitemap.findall('s:url/s:loc', namespace)]
        self.assertIn(SITE_URL + en_path, urls)
        self.assertIn(SITE_URL + '/en/news', urls)
        self.assertEqual(self.select_language(page, 'pt').request.path, pt_path)

        pt.status = 'withdrawn'
        db.session.commit()
        response = self.select_language(self.soup(en_path), 'pt')
        self.assertEqual(response.request.path, en_path)
        page = BeautifulSoup(response.text, 'html.parser')
        link = page.select_one('.news-language-notice a')
        self.assertEqual(link.text, 'Ver Notícias de Ciência em português')
        self.assertEqual(self.client.get(link['href'], follow_redirects=True).request.path, '/noticias')
        self.assertEqual(self.client.get(pt_path).status_code, 404)
        self.assertNotIn(pt_path, self.client.get('/sitemap.xml').text)

    def test_related_article_requires_public_content_in_the_requested_language(self):
        story, pt = self.story('Notícia de ensaio')
        _, en = self.story('Test story', locale='en', story=story)
        related = Article.query.filter_by(status='published').first()
        pt.related_article_id = en.related_article_id = related.id
        db.session.commit()
        self.assertIsNotNone(self.soup('/noticias/' + pt.slug).select_one('.news-related a'))
        self.assertIsNone(self.soup('/en/news/' + en.slug).select_one('.news-related a'))

    def auth(self, role=None):
        account_id = None
        if role:
            username = 'news-' + secrets.token_hex(5)
            account = AdminUser(username=username, display_name=username, password_hash='fixture',
                                governance_managed=True, two_factor_enabled=True, totp_secret='JBSWY3DPEHPK3PXP')
            member = TeamMember(name=username, email=username + '@example.org', admin=account,
                                status='active', accepted_at=utcnow())
            db.session.add(TeamAppointment(member=member, role=TeamRole.query.filter_by(code=role).one(),
                                           starts_on=date.today()))
            db.session.commit()
            account_id = account.id
        with self.client.session_transaction() as state:
            state.clear()
            state.update(admin_authenticated=True, admin_id=account_id, admin_superuser=not role,
                         admin_last_activity_at=time.time(), admin_2fa_verified=True, csrf_token='news-csrf')
            authenticate_test_session(state)
        return member if role else None

    def form(self, locale='pt', **overrides):
        fields = dict(action='save', language=locale, title='Ensaio ' + self.token,
                      slug='editorial-' + self.token, author_id=self.author.id, category_id=self.topic.id,
                      summary='Resumo editorial', body='Texto com um facto de ensaio.',
                      image='https://example.org/cover.jpg', image_alt='Descrição da capa',
                      image_credit='Arquivo de ensaio', sources_text='Estudo original | https://example.org/research',
                      evidence='preprint', evidence_note='A revisão por pares está pendente.')
        return dict(fields, **overrides)

    def post(self, path, **fields):
        return self.client.post(path, data=dict(csrf_token='news-csrf', **fields))

    def action(self, item, action, **fields):
        db.session.refresh(item)
        return self.post('/admin/noticias/' + str(item.id), action=action, revision=item.revision, **fields)

    def test_editorial_roles_validation_feature_withdraw_and_revisions(self):
        self.assertEqual(self.client.get('/admin/noticias').status_code, 302)
        self.auth('secretariat')
        self.assertEqual(self.client.get('/admin/noticias').status_code, 403)
        self.assertEqual(self.post('/admin/noticias/nova', **self.form()).status_code, 403)

        reviewer = self.auth('portal_reviewer')
        self.auth('portal_editor')
        self.assertEqual(self.post('/admin/noticias/nova', **self.form(sources_text='http://example.org')).status_code, 400)
        self.assertEqual(self.post('/admin/noticias/nova', **self.form()).status_code, 303)
        item = NewsVersion.query.filter_by(title='Ensaio ' + self.token).one()
        self.assertEqual(self.client.get('/admin/noticias/' + str(item.id)).status_code, 200)
        self.assertEqual(self.action(item, 'assign', reviewer_id=reviewer.id).status_code, 303)
        reviewer_id = reviewer.admin_id
        with self.client.session_transaction() as state:
            state['admin_id'] = reviewer_id
            authenticate_test_session(state)
        self.assertEqual(self.action(item, 'reviewed', review_note='Fontes e atribuição verificadas.').status_code, 303)
        self.auth('portal_editor')
        self.assertEqual(self.action(item, 'approve').status_code, 303)
        self.assertEqual(self.action(item, 'publish').status_code, 403)
        self.auth('publisher')
        self.assertEqual(self.action(item, 'publish').status_code, 303)
        _, other = self.story('Outro destaque', offset=-2, featured=True)
        self.assertEqual(self.action(item, 'feature').status_code, 303)
        db.session.refresh(other)
        self.assertFalse(other.featured)
        self.assertEqual(self.headings(self.soup('/noticias'), '.news-lead'), [item.title])

        db.session.refresh(item)
        response = self.post('/admin/noticias/' + str(item.id), revision=item.revision,
                             **self.form(body='Texto actualizado após verificação.'))
        self.assertEqual(response.status_code, 303)
        article = self.soup('/noticias/' + item.slug)
        self.assertIn('Actualizado em', article.text)
        self.assertIn('Arquivo de ensaio', article.select_one('.news-figure figcaption').text)
        self.assertEqual(article.select_one('.news-figure img')['alt'], 'Descrição da capa')
        self.assertEqual(article.select_one('.news-author-credit a').text.strip(), item.author.name)
        self.assertEqual(article.select_one('.news-author-credit a')['href'],
                         '/autores/' + item.author.slug)
        self.assertEqual(article.select_one('.news-publication-details time')['datetime'],
                         item.published_date.isoformat())
        self.assertIsNone(article.select_one('.news-evidence'))
        self.assertEqual(self.action(item, 'withdraw').status_code, 303)
        self.assertEqual(self.client.get('/noticias/' + item.slug).status_code, 404)
        self.assertEqual(self.headings(self.soup('/noticias'), '.news-lead'), [other.title])
        self.assertTrue(GovernanceAudit.query.filter_by(action='news.withdraw', entity_id=item.id).count())

    def test_evidence_note_removed_from_editor_but_existing_note_is_preserved(self):
        self.auth()
        self.assertEqual(self.post('/admin/noticias/nova', **self.form()).status_code, 303)
        item = NewsVersion.query.filter_by(title='Ensaio ' + self.token).one()
        page = self.soup('/admin/noticias/' + str(item.id))
        self.assertIsNone(page.select_one('#news-evidence-note'))

        original_note = item.evidence_note
        form = self.form()
        form.pop('evidence_note')
        self.assertEqual(self.post('/admin/noticias/' + str(item.id),
                                   revision=item.revision, **form).status_code, 303)
        db.session.refresh(item)
        self.assertEqual(item.evidence_note, original_note)

        self.assertEqual(self.action(item, 'publish').status_code, 303)
        article = self.soup('/noticias/' + item.slug)
        self.assertIsNone(article.select_one('.news-evidence'))
        self.assertNotIn(original_note, article.select_one('.news-reading-main').get_text())

    def test_new_preliminary_news_does_not_require_removed_note(self):
        self.auth()
        form = self.form(evidence='preliminary')
        form.pop('evidence_note')
        self.assertEqual(self.post('/admin/noticias/nova', **form).status_code, 303)
        item = NewsVersion.query.filter_by(title='Ensaio ' + self.token).one()
        self.assertFalse(item.evidence_note)
        self.assertEqual(self.action(item, 'publish').status_code, 303)

    def test_independent_english_publication_and_version_conflicts(self):
        self.auth()
        response = self.post('/admin/noticias/nova', **self.form('en', title='English first', sources_text=''))
        self.assertEqual(response.status_code, 303)
        en = NewsVersion.query.filter_by(title='English first').one()
        self.assertEqual(self.action(en, 'publish').status_code, 400)
        self.assertEqual(self.post('/admin/noticias/' + str(en.id), revision='0', **self.form('en')).status_code, 409)
        self.assertEqual(self.action(en, 'feature').status_code, 409)
        group = '/admin/noticias/grupo/' + str(en.story_id) + '/nova'
        self.assertEqual(self.post(group, **self.form('en')).status_code, 409)
        self.assertEqual(self.post('/admin/noticias/' + str(en.id), revision=en.revision,
                                   **self.form('en', title='English first')).status_code, 303)
        self.assertEqual(self.action(en, 'publish').status_code, 303)
        self.assertIn('English first', self.soup('/en/news').text)
        self.assertEqual(self.post(group, **self.form()).status_code, 303)
        self.assertEqual(self.client.get('/noticias/' + en.slug).status_code, 404)
