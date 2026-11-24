"""Regression coverage for existing editorial labels and related stories."""
import secrets
import unittest
from datetime import datetime
from bs4 import BeautifulSoup

from app import app
from models import db, Article, Author, Category


class EditorialDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        token = secrets.token_hex(8)
        self.author = Author(name='Autor '+token, slug='discovery-author-'+token)
        self.category = Category(name='Tema '+token, slug='discovery-theme-'+token)
        self.other_category = Category(name='Outro '+token, slug='discovery-other-'+token)
        db.session.add_all([self.author, self.category, self.other_category])
        db.session.flush()
        self.rows = []
        self.selected = self.story('principal')
        db.session.commit()
        self.client = app.test_client()

    def story(self, label, *, same=True, day=1, status='published'):
        token = secrets.token_hex(8)
        row = Article(title=label+' '+token, slug='discovery-'+token,
            summary='Resumo científico de teste.', body='Conteúdo de teste para descoberta editorial.',
            author_rel=self.author, category_rel=self.category if same else self.other_category,
            status=status, published_at=datetime(2100, 1, day),
            scheduled_at=datetime(2101, 1, 1) if status=='scheduled' else None)
        db.session.add(row)
        self.rows.append(row)
        return row

    def tearDown(self):
        for row in self.rows:
            db.session.delete(row)
        db.session.flush()
        for row in [self.author, self.category, self.other_category]:
            db.session.delete(row)
        db.session.commit()
        db.session.remove()
        self.context.pop()

    def related(self):
        response = self.client.get('/artigo/'+self.selected.slug)
        self.assertEqual(response.status_code, 200)
        return [link['href'] for link in BeautifulSoup(response.data, 'html.parser')
                .select('.article-related-grid > a')]

    def test_same_category_precedes_newer_unrelated_stories(self):
        older = self.story('Relacionado antigo', day=2)
        newer = self.story('Relacionado recente', day=3)
        fallback = self.story('Outro tema', same=False, day=10)
        db.session.commit()
        self.assertEqual(self.related(), ['/artigo/'+row.slug for row in [newer, older, fallback]])

    def test_three_related_stories_need_no_unrelated_fallback(self):
        rows = [self.story('Mesmo tema', day=day) for day in [2, 3, 4, 5]]
        self.story('Outro tema mais recente', same=False, day=20)
        db.session.commit()
        self.assertEqual(self.related(), ['/artigo/'+row.slug for row in rows[:0:-1]])

    def test_fallback_is_recent_stable_unique_and_excludes_current_article(self):
        rows = [self.story('Outro tema', same=False, day=10) for _ in range(3)]
        db.session.commit()
        links = self.related()
        self.assertEqual(links, ['/artigo/'+row.slug for row in reversed(rows)])
        self.assertEqual(len(links), len(set(links)))
        self.assertNotIn('/artigo/'+self.selected.slug, links)

    def test_private_states_cannot_enter_related_stories(self):
        private = [self.story('Privado', day=20, status=status)
                   for status in ['draft', 'review', 'approved', 'scheduled']]
        public = self.story('Público', day=2)
        db.session.commit()
        links = self.related()
        self.assertEqual(links[0], '/artigo/'+public.slug)
        for row in private:
            self.assertNotIn('/artigo/'+row.slug, links)

    def test_home_labels_match_current_capabilities_and_preserve_signup(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.data, 'html.parser')
        self.assertIn('Artigos recentes', soup.get_text())
        self.assertNotIn('Mais lidos', soup.get_text())
        self.assertNotIn('Boletim semanal', soup.get_text())
        self.assertIn('Boletim científico', soup.get_text())
        self.assertIsNotNone(soup.select_one('#newsletterForm input[type="email"]'))
        self.assertEqual(soup.select_one('#newsletterForm button').get_text(), 'Subscrever')
        self.assertEqual(soup.select_one('.newsletter-signup')['class'][:3],
                         ['bg-science', 'text-white', 'newsletter-signup'])
        self.assertIsNotNone(soup.select_one('#newsletterForm input[type="email"]'))
        self.assertEqual(soup.select_one('#newsletterMessage')['role'], 'status')

