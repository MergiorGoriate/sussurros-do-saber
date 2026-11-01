"""Protect article attribution and author ordering during admin edits."""
import unittest
from bs4 import BeautifulSoup
import test_site_audit_regressions as fixtures
from models import db, Author


class AdminEditorFixTests(unittest.TestCase):
    setUp = fixtures.SiteAuditRegressions.setUp
    tearDown = fixtures.SiteAuditRegressions.tearDown
    member = fixtures.SiteAuditRegressions.member
    article = fixtures.SiteAuditRegressions.article
    signin = fixtures.SiteAuditRegressions.signin
    post = fixtures.SiteAuditRegressions.post
    fields = fixtures.SiteAuditRegressions.fields

    def test_hidden_current_author_remains_selected_after_get_and_validation_error(self):
        owner = self.member()
        article = self.article(owner)
        owner.author.active = False
        db.session.commit()
        path = f'/admin/artigos/{article.id}/editar'
        responses = [self.client.get(path), self.post(path, **self.fields(article, title='x'))]
        for response in responses:
            self.assertEqual(response.status_code, 200)
            soup = BeautifulSoup(response.data, 'html.parser')
            selected = soup.select_one('select[name="author_id"] option[selected]')
            self.assertIsNotNone(selected)
            self.assertEqual(selected['value'], str(owner.author_id))
        db.session.refresh(article)
        self.assertEqual(article.author_id, owner.author_id)

    def test_zero_author_order_is_persisted(self):
        author = self.member().author
        response = self.post('/admin/autores', author_id=author.id, name=author.name,
                             slug=author.slug, display_order='0')
        self.assertEqual(response.status_code, 302)
        db.session.refresh(author)
        self.assertEqual(author.display_order, 0)

    def test_other_hidden_authors_are_not_offered_as_replacements(self):
        article = self.article(self.member())
        other = self.member().author
        other.active = False
        db.session.commit()
        response = self.client.get(f'/admin/artigos/{article.id}/editar')
        soup = BeautifulSoup(response.data, 'html.parser')
        values = [option['value'] for option in soup.select('select[name="author_id"] option')]
        self.assertIn(str(article.author_id), values)
        self.assertNotIn(str(other.id), values)
