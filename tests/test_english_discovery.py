"""Public discovery must not depend on unrelated translation queue entries."""
import hashlib
import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
import test_platform
import test_internationalization as fixtures
from app import app, SITE_URL
from models import Article, Category, db
from translation_models import InterfaceTranslation
from internationalization import interface_ready
from i18n_templates import SOURCES, TEMPLATE_SOURCES


class EnglishDiscoveryTests(unittest.TestCase):
    setUp_base = fixtures.InternationalizationTests.setUp
    tearDown = fixtures.InternationalizationTests.tearDown
    make = fixtures.InternationalizationTests.make

    def setUp(self):
        self.setUp_base()
        original_sources = set(SOURCES)
        self.addCleanup(lambda: SOURCES.intersection_update(original_sources | TEMPLATE_SOURCES))
        category = Category.query.filter_by(name='Biologia').first()
        if category is None:
            category = Category(name='Biologia', slug='biologia')
            db.session.add(category)
        self.article.category_rel = category
        db.session.commit()
        public_cards = Article.public_card_query
        selected_id = self.article.id
        cards = patch.object(Article, 'public_card_query', side_effect=lambda:
            public_cards().filter(Article.id == selected_id))
        cards.start()
        self.addCleanup(cards.stop)

    def interface_row(self, source, english='', published=False):
        row = InterfaceTranslation(key=hashlib.sha256(source.encode()).hexdigest(),
            source=source, english=english, published=published)
        db.session.add(row)
        db.session.commit()
        return row

    def english_article(self):
        return self.client.get('/en/artigo/' + self.article.slug)

    def assert_english_discoverable(self):
        response = self.english_article()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('noindex', response.headers.get('X-Robots-Tag', ''))
        soup = BeautifulSoup(response.text, 'html.parser')
        expected = SITE_URL + '/en/artigo/' + self.article.slug
        self.assertEqual(soup.find('link', hreflang='en')['href'], expected)
        self.assertIn('<loc>' + expected + '</loc>', self.client.get('/sitemap.xml').text)
        original = BeautifulSoup(self.client.get('/artigo/' + self.article.slug).text, 'html.parser')
        self.assertEqual(original.find('link', hreflang='en')['href'], expected)

    def test_pending_unrelated_dynamic_copy_does_not_hide_public_english(self):
        self.make(publish=True)
        source = 'Perfil ou curso ainda em revisão ' + self.article.slug
        self.interface_row(source)
        SOURCES.add(source)
        self.addCleanup(SOURCES.discard, source)
        self.assertNotIn(source, TEMPLATE_SOURCES)
        self.assert_english_discoverable()

    def test_unpublished_override_keeps_reviewed_bootstrap_translation(self):
        self.make(publish=True)
        self.interface_row('Biologia', english='Draft label', published=False)
        self.assert_english_discoverable()
        self.assertNotIn('Draft label', self.english_article().text)

    def test_custom_category_requires_publication_before_discovery(self):
        name = 'Categoria por traduzir ' + self.article.slug
        category = Category(name=name, slug='category-' + self.article.slug)
        self.article.category_rel = category
        db.session.commit()
        self.make(publish=True)
        row = self.interface_row(name)
        expected = SITE_URL + '/en/artigo/' + self.article.slug
        response = self.english_article()
        self.assertIn('noindex', response.headers.get('X-Robots-Tag', ''))
        self.assertIsNone(BeautifulSoup(response.text, 'html.parser').find('link', hreflang='en'))
        self.assertNotIn('<loc>' + expected + '</loc>', self.client.get('/sitemap.xml').text)
        row.english = 'Reviewed custom category'
        row.published = True
        db.session.commit()
        self.assert_english_discoverable()
        self.assertIn('Reviewed custom category', self.english_article().text)

    def test_missing_shared_template_label_still_blocks_indexing(self):
        self.make(publish=True)
        with patch.dict('internationalization.EN', {'Pesquisar': ''}):
            response = self.english_article()
            self.assertIn('noindex', response.headers.get('X-Robots-Tag', ''))
            self.assertNotIn('<loc>' + SITE_URL + '/en/', self.client.get('/sitemap.xml').text)

    def test_live_categories_have_reviewed_labels_without_source_edits(self):
        cases = {
            'Ciência e Universo': 'Science and the Universe',
            'Evolução': 'Evolution',
            'Ciência em África': 'Science in Africa',
            'Ambiente e Biodiversidade': 'Environment and Biodiversity',
            'Evolução e Origens': 'Evolution and Origins',
        }
        self.make(publish=True)
        for source, english in cases.items():
            category = Category.query.filter_by(name=source).first()
            if category is None:
                category = Category(name=source, slug='category-' + hashlib.sha256(source.encode()).hexdigest()[:12])
                db.session.add(category)
            self.article.category_rel = category
            db.session.commit()
            self.assert_english_discoverable()
            self.assertIn(english, self.english_article().text)
            self.assertEqual(self.article.category, source)

    def test_admin_collection_includes_custom_categories_without_global_block(self):
        from translation_admin import collect_interface
        name = 'Categoria para revisão ' + self.article.slug
        db.session.add(Category(name=name, slug='collect-' + self.article.slug))
        db.session.commit()
        collect_interface()
        row = InterfaceTranslation.query.filter_by(source=name).one()
        self.assertFalse(row.published)
        self.assertEqual(row.english, '')
        self.assertNotIn(name, TEMPLATE_SOURCES)
        with app.test_request_context('/sitemap.xml'):
            app.preprocess_request()
            self.assertTrue(interface_ready())


if __name__ == '__main__':
    unittest.main()
