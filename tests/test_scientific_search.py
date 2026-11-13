"""Public scientific discovery must not expose private publications."""
import json
import secrets
import unittest
from datetime import date, timedelta
from bs4 import BeautifulSoup

from app import app
from models import db, Article, Author, Category, Journal, utcnow
from scientific_search import doi_url


class ScientificSearchTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        token = secrets.token_hex(6)
        self.author = Author(name='Autora '+token, slug='search-author-'+token,
                             orcid='0000-0002-1825-0097')
        self.category = Category(name='Categoria '+token, slug='search-category-'+token)
        self.article = Article(title='Artigo '+token, slug='search-article-'+token,
            summary='Resumo de investigação', body='Texto completo de ciência.',
            keywords='metadadopesquisavel', doi='10.12345/search.'+token,
            author_rel=self.author, category_rel=self.category,
            status='published', published_at=utcnow())
        self.private = Article(title='Privado '+token, slug='private-search-'+token,
            summary=self.article.summary, body=self.article.body,
            doi=self.article.doi, author_rel=self.author, category_rel=self.category,
            status='draft')
        self.journal = Journal(title='Revista '+token, article_title='Pesquisa '+token,
            slug='search-journal-'+token, field='Biologia', description='Descrição',
            keywords='metadadopesquisavel', doi='https://doi.org/10.12345/journal.'+token,
            authors_data=json.dumps([{'name':'Coautora '+token,
                'orcid':'https://orcid.org/0000-0001-5109-3700','description':'Instituição'}]),
            published=True, publication_date=date(2026, 1, 1))
        self.hidden = Journal(title=self.journal.title, article_title=self.journal.article_title,
            slug='hidden-journal-'+token, field='Biologia', description='Descrição',
            doi=self.journal.doi, authors_data=self.journal.authors_data, published=False)
        db.session.add_all([self.article, self.private, self.journal, self.hidden])
        db.session.commit()
        self.client = app.test_client()

    def tearDown(self):
        for item in [self.article, self.private, self.journal, self.hidden]:
            db.session.delete(item)
        db.session.flush()
        db.session.delete(self.author)
        db.session.delete(self.category)
        db.session.commit()
        db.session.remove()
        self.context.pop()

    def test_articles_and_api_find_identifiers_and_keep_drafts_private(self):
        for term in [self.article.title, self.author.name, self.article.doi,
                     'https://doi.org/'+self.article.doi.upper(),
                     self.author.orcid, 'https://orcid.org/'+self.author.orcid,
                     'metadadopesquisavel', 'investigacao', 'INVESTIGACAO']:
            with self.subTest(term=term):
                response = self.client.get('/artigos', query_string={'q':term})
                self.assertEqual(response.status_code, 200)
                soup = BeautifulSoup(response.data, 'html.parser')
                self.assertIsNotNone(soup.select_one('a[href="/artigo/'+self.article.slug+'"]'))
                self.assertIsNone(soup.select_one('a[href="/artigo/'+self.private.slug+'"]'))
                response = self.client.get('/api/artigos', query_string={'q':term})
                self.assertEqual(response.status_code, 200)
                ids = [row['id'] for row in response.json]
                self.assertIn(self.article.id, ids)
                self.assertNotIn(self.private.id, ids)

    def test_journal_search_includes_coauthors_identifiers_and_legacy_authors(self):
        name = json.loads(self.journal.authors_data)[0]['name']
        for term in [self.journal.article_title, name, '0000-0001-5109-3700',
                     'https://orcid.org/0000-0001-5109-3700',
                     self.journal.doi, self.journal.doi.removeprefix('https://doi.org/'),
                     'metadadopesquisavel', 'descricao', 'DESCRICAO']:
            with self.subTest(term=term):
                response = self.client.get('/revistas', query_string={'q':term})
                self.assertEqual(response.status_code, 200)
                soup = BeautifulSoup(response.data, 'html.parser')
                self.assertIsNotNone(soup.select_one('article[id="'+self.journal.slug+'"]'))
                self.assertIsNone(soup.select_one('article[id="'+self.hidden.slug+'"]'))
                self.assertEqual(soup.select_one('#journalSearch')['value'], term)
        self.journal.authors_data = ''
        self.journal.authors_orcid = 'Autora Legada Pesquisável'
        db.session.commit()
        response = self.client.get('/revistas', query_string={'q':'Legada Pesquisável'})
        self.assertIn(self.journal.slug, response.get_data(as_text=True))

    def test_empty_results_and_literal_wildcards(self):
        for term in ['nao-existe-'+secrets.token_hex(12), '%', '_', "' OR 1=1 --"]:
            self.assertEqual(self.client.get('/api/artigos', query_string={'q':term}).json, [])
        response = self.client.get('/revistas', query_string={'q':'nao-existe-'+secrets.token_hex(12)})
        soup = BeautifulSoup(response.data, 'html.parser')
        self.assertNotIn('hidden', soup.select_one('#journalEmpty').get('class', []))
        self.assertIsNotNone(soup.select_one('form[role="search"][method="get"]'))

    def test_existing_category_filter_and_pagination_are_preserved(self):
        response = self.client.get('/artigos', query_string={'q':self.article.doi,
                                                           'categoria':self.category.name})
        self.assertIn('/artigo/'+self.article.slug, response.get_data(as_text=True))
        response = self.client.get('/artigos', query_string={'q':self.article.doi,'page':2})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('/artigo/'+self.article.slug, response.get_data(as_text=True))
        self.assertEqual(self.client.get('/api/artigos', query_string={
            'q':self.article.doi,'ids':str(self.private.id)}).json, [])

    def test_typo_search_uses_all_words_and_keeps_filters_and_drafts_private(self):
        token = self.article.slug.removeprefix('search-article-')
        self.article.title = 'Cérebro e imunologia '+token
        self.private.title = self.article.title
        self.article.keywords = 'neuroplasticidade'
        db.session.commit()
        for term in ['imunlogia '+token, 'imunologia cerebro '+token,
                     'cerebro imunolgia '+token, 'Autroa '+token,
                     'neuroplaticidade '+token]:
            with self.subTest(term=term):
                page = self.client.get('/artigos', query_string={'q':term})
                self.assertEqual(page.status_code, 200)
                soup = BeautifulSoup(page.data, 'html.parser')
                self.assertIsNotNone(soup.select_one('a[href="/artigo/'+self.article.slug+'"]'))
                self.assertIsNone(soup.select_one('a[href="/artigo/'+self.private.slug+'"]'))
                rows = self.client.get('/api/artigos', query_string={'q':term}).json
                self.assertIn(self.article.id, [row['id'] for row in rows])
                self.assertNotIn(self.private.id, [row['id'] for row in rows])
        self.assertEqual(self.client.get('/api/artigos', query_string={
            'q':'imunlogia '+token, 'ids':str(self.private.id)}).json, [])
        excluded = self.client.get('/artigos', query_string={
            'q':'imunlogia '+token, 'categoria':'categoria-inexistente'})
        self.assertNotIn('/artigo/'+self.article.slug, excluded.text)
        self.assertEqual(self.client.get('/api/artigos', query_string={
            'q':'imunlogia oceanografia '+token}).json, [])

    def test_relevance_precedes_recency_and_pagination_in_html_and_api(self):
        token = self.article.slug.removeprefix('search-article-')
        self.article.title = 'Imunologia cérebro '+token
        self.article.published_at = utcnow()-timedelta(days=365)
        extras = [Article(title='Imunologia e cérebro '+token,
            slug='search-rank-'+token+'-'+str(i), summary='Fixture', body='',
            author_rel=self.author, category_rel=self.category, status='published',
            published_at=utcnow()) for i in range(14)]
        db.session.add_all(extras)
        db.session.commit()
        try:
            term = 'imunologia cerebro '+token
            api = self.client.get('/api/artigos', query_string={'q':term, 'limit':1})
            self.assertEqual([row['id'] for row in api.json], [self.article.id])
            pages = []
            for page in (1, 2):
                response = self.client.get('/artigos', query_string={'q':term, 'page':page})
                self.assertEqual(response.status_code, 200)
                soup = BeautifulSoup(response.data, 'html.parser')
                pages.append([link['href'] for link in soup.select('article.story-card > a')])
            self.assertEqual(pages[0][0], '/artigo/'+self.article.slug)
            self.assertEqual(len(pages[0]), 12)
            self.assertEqual(len(pages[1]), 3)
            self.assertFalse(set(pages[0]) & set(pages[1]))
        finally:
            for item in extras:
                db.session.delete(item)
            db.session.commit()

    def test_english_search_uses_only_published_translation_version(self):
        from translation_models import ContentTranslation, TranslationVersion
        from translation_service import source, digest
        token = self.article.slug.removeprefix('search-article-')
        translation = ContentTranslation(kind='article', source_id=self.article.id,
            language='en', state='review', version=2, published_version=1)
        db.session.add(translation)
        db.session.flush()
        original = source('article', self.article.id)
        versions = [TranslationVersion(translation_id=translation.id, number=number,
            source_hash=digest(original), source=original, report={},
            content=dict(original, title=title, summary='Published discovery'))
            for number, title in [(1, 'Memory and neuroplasticity '+token),
                                  (2, 'Unpublishedsecret '+token)]]
        db.session.add_all(versions)
        db.session.commit()
        try:
            for path in ['/en/artigos', '/api/artigos']:
                # API locale is selected by its normal language cookie.
                self.client.set_cookie('sds_language', 'en')
                response = self.client.get(path, query_string={'q':'memroy '+token})
                self.assertEqual(response.status_code, 200)
                if response.is_json:
                    self.assertIn(self.article.id, [row['id'] for row in response.json])
                else:
                    self.assertIn('Memory and neuroplasticity', response.text)
            response = self.client.get('/en/artigos', query_string={'q':'unpublishedsecret '+token})
            self.assertNotIn('/en/artigo/'+self.article.slug, response.text)
            self.assertEqual(self.client.get('/api/artigos',
                query_string={'q':'unpublishedsecret '+token}).json, [])
        finally:
            self.client.delete_cookie('sds_language')
            for item in versions:
                db.session.delete(item)
            db.session.delete(translation)
            db.session.commit()

    def test_doi_links_resolve_without_duplicate_prefixes(self):
        for record, path in [(self.journal, '/revistas/'+self.journal.slug),
                             (self.article, '/artigo/'+self.article.slug)]:
            record.doi = 'https://doi.org/10.12345/Resolver.Test'
            db.session.commit()
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            soup = BeautifulSoup(response.data, 'html.parser')
            self.assertIsNotNone(soup.select_one('a[href="https://doi.org/10.12345/Resolver.Test"]'))
            self.assertNotIn('https://doi.org/https://', response.get_data(as_text=True))
            record.doi = 'javascript:alert(1)'
            db.session.commit()
            soup = BeautifulSoup(self.client.get(path).data, 'html.parser')
            self.assertIsNone(soup.select_one('a[href^="javascript:"]'))
            self.assertIn(record.doi, soup.get_text())


class DoiResolverTests(unittest.TestCase):
    def test_supported_forms_and_encoded_suffix(self):
        for value in ['10.12345/Test', 'doi:10.12345/Test',
                      'HTTPS://DOI.ORG/10.12345/Test', 'http://dx.doi.org/10.12345/Test']:
            self.assertEqual(doi_url(value), 'https://doi.org/10.12345/Test')
        self.assertEqual(doi_url('10.12345/a#b'), 'https://doi.org/10.12345/a%23b')

    def test_invalid_values_do_not_become_links(self):
        for value in ['', None, 'javascript:alert(1)', 'https://evil.test/10.12345/Test',
                      '10.123/Test', '10.12345/with space', '10.12345/<script>']:
            self.assertEqual(doi_url(value), '')

