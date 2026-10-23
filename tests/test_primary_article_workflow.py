"""Primary-authored articles do not require a staff identity or staff mandate."""
import unittest
from unittest.mock import patch
import os
import time
from app import app
from models import db, Author, Article, utcnow
from governance_models import ArticleWorkflow, TeamMember, StaffNotice
import test_staff_governance as fixtures


class PrimaryArticleWorkflowTests(unittest.TestCase):
    def setUp(self):
        fixtures.StaffGovernanceTests.setUp(self)
        from extensions import limiter
        patcher = patch.object(limiter, 'enabled', False)
        patcher.start()
        self.addCleanup(patcher.stop)

    tearDown = fixtures.StaffGovernanceTests.tearDown
    signin = fixtures.StaffGovernanceTests.signin
    post = fixtures.StaffGovernanceTests.post
    member = fixtures.StaffGovernanceTests.member

    def unlinked_article(self, status='draft'):
        author = Author(name='Autor principal', slug='principal-'+self.token)
        db.session.add(author)
        db.session.flush()
        article = Article(title='Autoria sem mandato', slug='artigo-'+self.token,
                          summary='Resumo do artigo', body='Texto fundamentado. '*20,
                          author_rel=author, category_id=self.category.id, status=status)
        db.session.add(article)
        db.session.commit()
        return article, f'/admin/fluxo-artigos/{article.id}'

    def test_get_and_post_start_without_creating_team_member(self):
        article, path = self.unlinked_article()
        self.signin(self.primary)
        members = TeamMember.query.count()
        page = self.client.get(path)
        self.assertEqual(page.status_code, 200)
        self.assertIn('Autor principal', page.text)
        self.assertNotIn('Associação do autor', page.text)
        self.assertIsNone(db.session.get(ArticleWorkflow, article.id))
        self.assertEqual(self.client.post(path, data={'action':'submit'}).status_code, 400)
        self.assertEqual(self.post(path, action='submit').status_code, 302)
        flow = db.session.get(ArticleWorkflow, article.id)
        self.assertIsNone(flow.owner_id)
        self.assertTrue(flow.primary_owned)
        self.assertEqual(flow.stage, 'submitted')
        self.assertEqual(TeamMember.query.count(), members)

    def test_independent_review_approval_and_primary_notification(self):
        article, path = self.unlinked_article()
        reviewer = self.member('portal_reviewer')
        editor = self.member('portal_editor')
        self.signin(self.primary)
        self.assertEqual(self.post(path, action='assign', reviewer_id=reviewer.id).status_code, 302)
        self.signin(reviewer.admin)
        self.assertEqual(self.post(path, action='reviewed', note='Fontes verificadas e texto revisto.').status_code, 302)
        self.assertTrue(StaffNotice.query.filter_by(admin_id=self.primary.id, resource_type='article', resource_id=article.id).first())
        self.signin(self.primary)
        self.assertNotIn('value="approve"', self.client.get(path).text)
        self.assertEqual(self.post(path, action='approve').status_code, 403)
        self.signin(editor.admin)
        self.assertEqual(self.post(path, action='approve').status_code, 302)
        self.assertEqual(article.status, 'published')
        self.assertEqual(app.test_client().get('/artigo/'+article.slug).status_code, 200)

    def test_saving_primary_draft_creates_flow_and_renaming_author_resets_review(self):
        article, path = self.unlinked_article()
        self.signin(self.primary)
        def save(author):
            return self.post(f'/admin/artigos/{article.id}/editar', title=article.title,
                             summary=article.summary, body=article.body, status='draft',
                             author_id=author.id, category_id=self.category.id)
        self.assertEqual(save(article.author_rel).status_code, 302)
        flow = db.session.get(ArticleWorkflow, article.id)
        self.assertTrue(flow.primary_owned)
        flow.reviewed_at = flow.approved_at = utcnow()
        author = Author(name='Nova autoria', slug='nova-'+self.token)
        db.session.add(author); db.session.commit()
        self.assertEqual(save(author).status_code, 302)
        self.assertIsNone(flow.reviewed_at)
        self.assertIsNone(flow.approved_at)
        self.assertTrue(flow.primary_owned)

    def test_editor_does_not_receive_primary_exception_and_removed_owner_stays_blocked(self):
        article, path = self.unlinked_article()
        editor = self.member('portal_editor')
        self.signin(editor.admin)
        self.assertIn('Associação do autor', self.client.get(path).text)
        self.assertIsNone(db.session.get(ArticleWorkflow, article.id))
        removed = self.member()
        removed.author = article.author_rel
        removed.removed_at = utcnow()
        db.session.commit()
        self.signin(self.primary)
        self.assertIn('Associação do autor', self.client.get(path).text)

    def test_matching_author_email_cannot_be_assigned_for_independent_review(self):
        article, path = self.unlinked_article()
        reviewer = self.member('portal_reviewer')
        article.author_rel.email = reviewer.admin.email.upper()
        db.session.commit()
        self.signin(self.primary)
        self.assertEqual(self.post(path, action='assign', reviewer_id=reviewer.id).status_code, 400)
        self.assertIsNone(db.session.get(ArticleWorkflow, article.id))

    def test_environment_primary_without_database_account_can_start_workflow(self):
        from admin import admin_security_stamp
        article, path = self.unlinked_article('review')
        with patch.dict(os.environ, {'ADMIN_USERNAME':'primary-env', 'ADMIN_TOTP_SECRET':'JBSWY3DPEHPK3PXP'}):
            with app.test_request_context():
                stamp = admin_security_stamp()
            with self.client.session_transaction() as session:
                session.clear()
                session.update(admin_authenticated=True, admin_id=None, admin_username='primary-env',
                               admin_superuser=True, admin_security_stamp=stamp,
                               admin_2fa_verified=True, admin_last_activity_at=time.time(), csrf_token='test')
            self.assertEqual(self.client.get(path).status_code, 200)
            self.assertEqual(self.post(path, action='reopen').status_code, 302)
            flow = db.session.get(ArticleWorkflow, article.id)
            self.assertTrue(flow.primary_owned)
            self.assertIsNone(flow.owner_id)
            self.assertEqual(flow.stage, 'draft')
            self.assertFalse(TeamMember.query.filter_by(author_id=article.author_id).first())
