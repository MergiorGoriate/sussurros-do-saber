"""Portal assignments require a usable linked administrator; synthetic data only."""
import unittest
import test_lifecycle_notifications as fixtures
from models import db
from governance_models import ArticleWorkflow, GovernanceAudit, StaffNotice


class PortalReviewerAccountTests(unittest.TestCase):
    setUp = fixtures.LifecycleNotificationTests.setUp
    tearDown = fixtures.LifecycleNotificationTests.tearDown
    member = fixtures.LifecycleNotificationTests.member
    signin = fixtures.LifecycleNotificationTests.signin
    post = fixtures.LifecycleNotificationTests.post
    article = fixtures.LifecycleNotificationTests.article
    notices = fixtures.LifecycleNotificationTests.notices

    def test_assignment_rejects_unlinked_and_inactive_accounts_without_side_effects(self):
        owner = self.member()
        editor = self.member('portal_editor')
        previous = self.member('portal_reviewer')
        article = self.article(owner)
        flow = db.session.get(ArticleWorkflow, article.id)
        flow.stage = 'review'
        flow.reviewer_id = previous.id
        db.session.commit()
        path = f'/admin/fluxo-artigos/{article.id}'
        for invalid in ('unlinked', 'inactive'):
            with self.subTest(account=invalid):
                candidate = self.member('portal_reviewer')
                if invalid == 'unlinked':
                    candidate.admin = None
                else:
                    candidate.admin.active = False
                db.session.commit()
                self.signin(editor.admin)
                page = self.client.get(path)
                self.assertEqual(page.status_code, 200)
                self.assertNotIn(f'value="{candidate.id}"'.encode(), page.data)
                before = StaffNotice.query.count()
                audits = GovernanceAudit.query.filter_by(action='article.assign', entity_id=article.id).count()
                self.assertEqual(self.post(path, action='assign', reviewer_id=candidate.id).status_code, 400)
                self.assertEqual(flow.reviewer_id, previous.id)
                self.assertEqual(flow.stage, 'review')
                self.assertEqual(StaffNotice.query.count(), before)
                self.assertEqual(GovernanceAudit.query.filter_by(action='article.assign', entity_id=article.id).count(), audits)

    def test_responsibility_reassignment_rejects_unlinked_portal_reviewers_and_editors(self):
        owner = self.member()
        previous = self.member('portal_reviewer')
        article = self.article(owner)
        flow = db.session.get(ArticleWorkflow, article.id)
        flow.reviewer_id = previous.id
        flow.stage = 'review'
        db.session.commit()
        self.signin(self.primary)
        path = f'/admin/equipa/{previous.id}/responsabilidades'
        for kind, role in [('portal_reviewer', 'portal_reviewer'), ('portal_editor', 'portal_editor')]:
            with self.subTest(kind=kind):
                candidate = self.member(role)
                candidate.admin = None
                db.session.commit()
                before = StaffNotice.query.count()
                self.assertEqual(self.post(path, kind=kind, resource_id=article.id, target_id=candidate.id).status_code, 400)
                self.assertEqual(flow.reviewer_id, previous.id)
                self.assertIsNone(flow.editor_id)
                self.assertEqual(StaffNotice.query.count(), before)

    def test_valid_reviewer_receives_opens_and_submits_then_revocation_blocks_access(self):
        owner = self.member()
        editor = self.member('portal_editor')
        reviewer = self.member('portal_reviewer')
        article = self.article(owner)
        path = f'/admin/fluxo-artigos/{article.id}'
        self.signin(editor.admin)
        self.assertEqual(self.post(path, action='assign', reviewer_id=reviewer.id).status_code, 302)
        notice = self.notices(reviewer, 'article', article.id)[0]
        self.signin(reviewer.admin)
        response = self.client.get(f'/admin/notificacoes/{notice.id}/abrir')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith(path))
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.post(path, action='reviewed', note='Parecer independente e fundamentado. ' * 3).status_code, 302)
        self.assertIsNotNone(db.session.get(ArticleWorkflow, article.id).reviewed_at)
        reviewer.appointments[0].active = False
        db.session.commit()
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.post(path, action='reviewed', note='Sem autorização').status_code, 404)
