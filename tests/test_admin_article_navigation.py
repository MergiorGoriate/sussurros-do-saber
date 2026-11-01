"""Article navigation preserves filtering and staff visibility."""
import unittest
from bs4 import BeautifulSoup
import test_site_audit_regressions as fixtures
from models import db


class ArticleNavigationTests(unittest.TestCase):
    setUp = fixtures.SiteAuditRegressions.setUp
    tearDown = fixtures.SiteAuditRegressions.tearDown
    member = fixtures.SiteAuditRegressions.member
    article = fixtures.SiteAuditRegressions.article
    signin = fixtures.SiteAuditRegressions.signin

    def test_pagination_preserves_filters_and_bounds_pages(self):
        owner = self.member()
        for i in range(12):
            item = self.article(owner)
            item.title = 'Navegação ' + self.token + ' ' + str(i)
        db.session.commit()
        args = dict(q=self.token, status='draft', category_id=self.category.id, per_page=10)
        response = self.client.get('/admin/artigos', query_string=args)
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.data, 'html.parser')
        self.assertEqual(len(soup.select('tbody tr')), 10)
        next_link = soup.select_one('nav a[aria-label="Página 2"]')
        self.assertIn('status=draft', next_link['href'])
        self.assertIn('category_id=' + str(self.category.id), next_link['href'])
        second = BeautifulSoup(self.client.get(next_link['href']).data, 'html.parser')
        self.assertEqual(len(second.select('tbody tr')), 2)
        args['page'] = 99999
        last = BeautifulSoup(self.client.get('/admin/artigos', query_string=args).data, 'html.parser')
        self.assertEqual(last.select_one('[aria-current="page"]').text, '2')

    def test_search_author_and_status_and_invalid_parameters(self):
        owner = self.member()
        item = self.article(owner)
        item.title = 'Literal 100% ' + self.token
        db.session.commit()
        response = self.client.get('/admin/artigos', query_string=dict(q=owner.author.name, status='draft'))
        self.assertIn(item.title.encode(), response.data)
        response = self.client.get('/admin/artigos', query_string=dict(q=owner.author.name, status='published'))
        self.assertNotIn(item.title.encode(), response.data)
        response = self.client.get('/admin/artigos', query_string=dict(q='100%', category_id='9'*100, page='bad', per_page='bad'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(item.title.encode(), response.data)

    def test_author_cannot_find_another_authors_article(self):
        owner, other = self.member(), self.member()
        visible, hidden = self.article(owner), self.article(other)
        visible.title = 'Permitido ' + self.token
        hidden.title = 'Reservado ' + self.token
        db.session.commit()
        self.signin(owner.admin)
        response = self.client.get('/admin/artigos', query_string=dict(q=self.token, per_page=10))
        self.assertEqual(response.status_code, 200)
        self.assertIn(visible.title.encode(), response.data)
        self.assertNotIn(hidden.title.encode(), response.data)
        self.assertIn(b'1 de 1 artigos', response.data)
