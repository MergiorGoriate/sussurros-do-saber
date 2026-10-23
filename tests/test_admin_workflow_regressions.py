"""Regression checks for founder identity and changes of article ownership."""
import os
import time
import unittest
from unittest.mock import patch
import test_staff_governance as fixtures
from admin import admin_security_stamp
from governance_models import TeamMember, ArticleWorkflow, PortalReview
from models import db, Author, utcnow


class AdminWorkflowRegressions(unittest.TestCase):
    setUp = fixtures.StaffGovernanceTests.setUp
    tearDown = fixtures.StaffGovernanceTests.tearDown
    member = fixtures.StaffGovernanceTests.member
    article = fixtures.StaffGovernanceTests.article
    signin = fixtures.StaffGovernanceTests.signin
    post = fixtures.StaffGovernanceTests.post

    def test_environment_founder_can_remove_member_without_account(self):
        member = TeamMember(name='Colaborador sem conta', email=self.token+'@example.org', status='invited')
        db.session.add(member)
        db.session.commit()
        with patch.dict(os.environ, ADMIN_USERNAME='environment-founder', ADMIN_TOTP_SECRET='JBSWY3DPEHPK3PXP'):
            with self.client.session_transaction() as state:
                state.clear()
                state.update(admin_authenticated=True, admin_superuser=True, admin_2fa_verified=True,
                             admin_security_stamp=admin_security_stamp(), admin_last_activity_at=time.time(), csrf_token='test')
            path=f'/admin/remover/member/{member.id}'
            self.assertEqual(self.client.get(path).status_code, 200)
            self.assertEqual(self.post(path, confirm='yes').status_code, 303)
        db.session.refresh(member)
        self.assertIsNotNone(member.removed_at)
        self.assertEqual(member.status, 'ended')

    def change_author(self, article, author_id):
        return self.post(f'/admin/artigos/{article.id}/editar', title=article.title,
                         summary=article.summary, body=article.body, status='draft',
                         author_id=author_id, category_id=self.category.id)

    def test_change_author_resets_workflow_and_prevents_self_review(self):
        owner=self.member()
        reviewer=self.member('portal_reviewer')
        article=self.article(owner)
        flow=db.session.get(ArticleWorkflow, article.id)
        flow.reviewer=reviewer
        flow.editor=self.member('portal_editor')
        flow.stage=article.status='approved'
        flow.reviewed_at=flow.approved_at=utcnow()
        history=PortalReview(article_id=article.id, reviewer_id=reviewer.id, action='reviewed', report='Parecer anterior')
        db.session.add(history)
        db.session.commit()
        self.signin(self.primary)
        self.assertEqual(self.change_author(article, reviewer.author_id).status_code, 302)
        db.session.refresh(flow)
        self.assertEqual(flow.owner_id, reviewer.id)
        self.assertIsNone(flow.reviewer_id)
        self.assertIsNone(flow.editor_id)
        self.assertIsNone(flow.reviewed_at)
        self.assertIsNone(flow.approved_at)
        self.assertEqual(flow.stage, 'draft')
        self.assertIsNotNone(db.session.get(PortalReview, history.id))
        response=self.post(f'/admin/fluxo-artigos/{article.id}', action='assign', reviewer_id=reviewer.id)
        self.assertEqual(response.status_code, 400)

    def test_primary_can_select_any_author_without_reactivating_removed_member(self):
        owner=self.member()
        article=self.article(owner)
        unlinked=Author(name='Autor sem colaborador', slug='unlinked-'+self.token)
        db.session.add(unlinked)
        db.session.commit()
        self.signin(self.primary)
        self.assertEqual(self.change_author(article, unlinked.id).status_code, 302)
        db.session.refresh(article)
        self.assertEqual(article.author_id, unlinked.id)
        flow=db.session.get(ArticleWorkflow, article.id)
        self.assertIsNone(flow.owner_id)
        self.assertTrue(flow.primary_owned)
        removed=self.member()
        removed.removed_at=utcnow()
        db.session.commit()
        self.assertEqual(self.change_author(article, removed.author_id).status_code, 302)
        db.session.refresh(article)
        self.assertEqual(article.author_id, removed.author_id)
        self.assertIsNotNone(removed.removed_at)

    def test_ordinary_editor_still_requires_linked_nonremoved_author(self):
        owner=self.member()
        editor=self.member('portal_editor')
        article=self.article(owner)
        unlinked=Author(name='Autor sem colaborador', slug='editor-unlinked-'+self.token)
        db.session.add(unlinked)
        db.session.commit()
        self.signin(editor.admin)
        self.assertEqual(self.change_author(article, unlinked.id).status_code, 409)
        db.session.refresh(article)
        self.assertEqual(article.author_id, owner.author_id)

