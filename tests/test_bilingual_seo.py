"""Regression checks for locale pagination, indexing and translation reads."""
import unittest
from unittest.mock import patch
from xml.etree import ElementTree
from bs4 import BeautifulSoup
from sqlalchemy import event
import test_platform
from app import app, SITE_URL
from extensions import limiter
from models import db, Article, Author, Category
from internationalization import published


class BilingualSEOTests(unittest.TestCase):
    def setUp(self):
        self.previous = limiter.enabled
        limiter.enabled = False
        self.client = app.test_client()
        with app.app_context():
            author = Author.query.first()
            category = Category.query.filter_by(name='Biologia').first()
            if category is None:
                category = Category(name='Biologia', slug='biologia')
                db.session.add(category)
            for number in range(26):
                db.session.add(Article(title=f'SEO fixture {number}', slug=f'seo-fixture-{number}',
                    summary='Resumo de ensaio.', body='Texto de ensaio.', status='published',
                    author_rel=author, category_rel=category))
            db.session.commit()
        # Other suites retain public articles and untranslated categories. Keep
        # this listing fixture independent without deleting their records.
        public_cards = Article.public_card_query
        cards = patch.object(Article, 'public_card_query', side_effect=lambda:
            public_cards().filter(Article.slug.like('seo-fixture-%')))
        cards.start()
        self.addCleanup(cards.stop)

    def tearDown(self):
        limiter.enabled = self.previous
        with app.app_context():
            Article.query.filter(Article.slug.like('seo-fixture-%')).delete()
            db.session.commit()

    def test_page_two_has_self_canonical_and_reciprocal_locale_urls(self):
        with patch('internationalization.interface_ready', return_value=True):
            for prefix in ('', '/en'):
                response = self.client.get(prefix + '/artigos?page=2&utm_source=fixture')
                self.assertEqual(response.status_code, 200)
                soup = BeautifulSoup(response.text, 'html.parser')
                expected = SITE_URL + prefix + '/artigos?page=2'
                self.assertEqual(soup.find('link', rel='canonical')['href'], expected)
                self.assertEqual(soup.find('meta', property='og:url')['content'], expected)
                self.assertEqual(soup.find('link', hreflang='pt-MZ')['href'], SITE_URL + '/artigos?page=2')
                self.assertEqual(soup.find('link', hreflang='en')['href'], SITE_URL + '/en/artigos?page=2')
                self.assertEqual(soup.find('link', hreflang='x-default')['href'], SITE_URL + '/artigos?page=2')
                self.assertNotIn('noindex', soup.find('meta', attrs={'name': 'robots'})['content'])
                self.assertNotIn('noindex', response.headers.get('X-Robots-Tag', ''))
                self.assertIn('2', soup.title.text)

    def test_search_and_category_are_noindex_in_both_locales(self):
        for prefix in ('', '/en'):
            for query in ('q=SEO', 'categoria=Biologia', 'original=missing'):
                response = self.client.get(prefix + '/artigos?' + query)
                soup = BeautifulSoup(response.text, 'html.parser')
                self.assertEqual(response.status_code, 200)
                self.assertIn('noindex', soup.find('meta', attrs={'name': 'robots'})['content'])
                self.assertEqual(response.headers['X-Robots-Tag'], 'noindex, follow')

    def test_empty_filters_tracking_and_invalid_page_do_not_create_canonicals(self):
        for query in ('page=1', 'q=&categoria=&utm_source=x', 'page=invalid', 'page=0'):
            for prefix in ('', '/en'):
                response = self.client.get(prefix + '/artigos?' + query)
                soup = BeautifulSoup(response.text, 'html.parser')
                self.assertEqual(soup.find('link', rel='canonical')['href'], SITE_URL + prefix + '/artigos')
                self.assertNotIn('noindex', soup.find('meta', attrs={'name': 'robots'})['content'])

    def test_filtered_canonical_and_alternates_preserve_content_parameters(self):
        with patch('internationalization.interface_ready', return_value=True):
            response = self.client.get('/artigos?q=SEO&page=2&utm_source=x')
            soup = BeautifulSoup(response.text, 'html.parser')
            self.assertEqual(soup.find('link', rel='canonical')['href'], SITE_URL + '/artigos?q=SEO&page=2')
            self.assertEqual(soup.find('link', hreflang='en')['href'], SITE_URL + '/en/artigos?q=SEO&page=2')

    def test_disabled_translation_does_not_advertise_english_urls(self):
        with patch.dict('os.environ', {'I18N_ENABLED': 'false'}):
            soup = BeautifulSoup(self.client.get('/artigos').text, 'html.parser')
            self.assertIsNone(soup.find('link', hreflang='en'))
            self.assertNotIn(b'<loc>https://www.sussurrosdosaber.com/en/', self.client.get('/sitemap.xml').data)
            self.assertEqual(self.client.get('/en/artigos').status_code, 404)

    def test_translation_cache_is_reset_for_each_request(self):
        with patch('internationalization.load_published', return_value=(None, None)) as load:
            for unused in range(2):
                with app.test_request_context('/en/artigos'):
                    app.preprocess_request()
                    published('article', 999999)
                    published('article', 999999)
            self.assertEqual(load.call_count, 2)

    def test_sitemap_loads_published_translation_links_together(self):
        from translation_models import ContentTranslation, TranslationVersion
        with app.app_context():
            article_ids = [
                Article.query.filter_by(slug=f'seo-fixture-{number}').one().id
                for number in range(2)
            ]
            items = [
                ContentTranslation(kind='article', source_id=ident, version=1, published_version=published_version)
                for ident, published_version in zip(article_ids, (1, None))
            ]
            db.session.add_all(items)
            db.session.flush()
            item_ids = [item.id for item in items]
            db.session.add_all([
                TranslationVersion(translation_id=item_id, number=1,
                    source_hash='fixture', source={}, content={'title': 'English fixture'}, report={})
                for item_id in item_ids
            ])
            db.session.commit()
            engine = db.engine

        translation_queries = []

        def collect_translation_queries(conn, cursor, statement, parameters, context, executemany):
            if 'FROM content_translation' in statement:
                translation_queries.append(statement)

        event.listen(engine, 'before_cursor_execute', collect_translation_queries)
        try:
            with patch('internationalization.interface_ready', return_value=True):
                response = self.client.get('/sitemap.xml')
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(translation_queries), 1)
            ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9', 'x': 'http://www.w3.org/1999/xhtml'}
            entries = {
                entry.findtext('s:loc', namespaces=ns): {
                    link.attrib['hreflang']: link.attrib['href'] for link in entry.findall('x:link', ns)
                }
                for entry in ElementTree.fromstring(response.data).findall('s:url', ns)
            }
            original = SITE_URL + '/artigo/seo-fixture-0'
            translated = SITE_URL + '/en/artigo/seo-fixture-0'
            self.assertEqual(entries[original]['en'], translated)
            self.assertEqual(entries[translated]['pt-MZ'], original)
            self.assertEqual(entries[SITE_URL + '/artigo/seo-fixture-1'], {})
            self.assertNotIn(SITE_URL + '/en/artigo/seo-fixture-1', entries)
        finally:
            event.remove(engine, 'before_cursor_execute', collect_translation_queries)
            with app.app_context():
                TranslationVersion.query.filter(TranslationVersion.translation_id.in_(item_ids)).delete()
                ContentTranslation.query.filter(ContentTranslation.id.in_(item_ids)).delete()
                db.session.commit()

    def test_english_cards_skip_full_source_hashing(self):
        from translation_models import ContentTranslation, TranslationVersion
        with app.app_context():
            article = Article.query.filter_by(slug='seo-fixture-0').one()
            item = ContentTranslation(kind='article', source_id=article.id, version=1, published_version=1)
            db.session.add(item)
            db.session.flush()
            item_id = item.id
            db.session.add(TranslationVersion(translation_id=item.id, number=1,
                source_hash='fixture', source={}, content={'title': 'English fixture', 'summary': 'English summary'}, report={}))
            db.session.commit()
        try:
            with patch('internationalization.stale') as stale:
                page = self.client.get('/en/artigos?q=SEO+fixture+0')
                self.assertEqual(page.status_code, 200)
                self.assertIn('English fixture', page.text)
                self.assertEqual(self.client.get('/en/').status_code, 200)
                stale.assert_not_called()
        finally:
            with app.app_context():
                TranslationVersion.query.filter_by(translation_id=item_id).delete()
                ContentTranslation.query.filter_by(id=item_id).delete()
                db.session.commit()

    def test_translated_category_is_not_reported_as_missing(self):
        from flask import g
        from internationalization import ui
        with app.test_request_context('/en/artigos'):
            app.preprocess_request()
            self.assertEqual(ui(ui('Biografia Científica')), 'Scientific Biography')
            self.assertFalse(getattr(g, 'i18n_missing', False))
            ui('Etiqueta de ensaio sem tradução no catálogo')
            self.assertTrue(g.i18n_missing)

    def test_all_shared_client_labels_have_english_translations(self):
        from i18n_client import KEYS
        from i18n_catalog import EN
        self.assertEqual([key for key in KEYS if not EN.get(key)], [])


if __name__ == '__main__':
    unittest.main()
