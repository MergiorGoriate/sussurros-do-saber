"""Removal revokes access without losing editorial provenance."""
import unittest
import test_staff_governance as fixtures
from app import app
from models import db, AdminUser
from governance_models import GovernanceAudit, TeamMember

class SecondaryAdminRemovalTests(unittest.TestCase):
    setUp = fixtures.StaffGovernanceTests.setUp
    tearDown = fixtures.StaffGovernanceTests.tearDown
    member = fixtures.StaffGovernanceTests.member
    signin = fixtures.StaffGovernanceTests.signin
    post = fixtures.StaffGovernanceTests.post
    article = fixtures.StaffGovernanceTests.article
    manuscript = fixtures.StaffGovernanceTests.manuscript

    def test_confirmation_history_session_revocation_and_no_reactivation(self):
        member = self.member('chief_editor', self.journal.id)
        article = self.article(member)
        manuscript, file = self.manuscript(member)
        account = member.admin
        self.signin(account)
        cookie = self.client.get_cookie('session').value
        self.signin(self.primary)
        path = f'/admin/administradores/{account.id}/eliminar'
        page = self.client.get('/admin/administradores').text
        self.assertIn(f'href="{path}"', page)
        self.assertIn('Cancelar', self.client.get(path).text)
        self.assertTrue(account.active)
        self.assertEqual(self.post(path).status_code, 400)
        self.assertEqual(self.client.post(path, data={'confirm':'yes'}).status_code, 400)
        self.assertEqual(self.post(path, confirm='yes').status_code, 303)
        self.assertFalse(account.active)
        self.assertIsNotNone(member.removed_at)
        self.assertFalse(member.appointments[0].active)
        self.assertIsNotNone(db.session.get(AdminUser, account.id))
        self.assertEqual(manuscript.editor_id, account.id)
        self.assertEqual(file.payload, b'SECRETO!')
        self.assertEqual(article.author_id, member.author_id)
        self.assertNotIn(f'href="{path}"', self.client.get('/admin/administradores').text)
        self.assertIn(member.name, self.client.get('/admin/historico-remocoes').text)
        other = app.test_client(); other.set_cookie('session', cookie)
        self.assertEqual(other.get('/admin/api/notificacoes').status_code, 401)
        self.assertEqual(self.post(f'/admin/administradores/{account.id}/editar', active='on').status_code, 409)
        self.assertEqual(self.post(path, confirm='yes').status_code, 303)
        self.assertEqual(GovernanceAudit.query.filter_by(action='account.removed',entity_id=account.id).count(),1)

    def test_founder_self_and_secondary_actor_cannot_remove(self):
        member = self.member('direction')
        self.signin(member.admin)
        path = f'/admin/administradores/{self.primary.id}/eliminar'
        self.assertEqual(self.client.get(path).status_code,403)
        self.assertEqual(self.post(path,confirm='yes').status_code,403)
        self.signin(self.primary)
        self.assertEqual(self.post(path,confirm='yes').status_code,403)
        self.assertTrue(self.primary.active)

    def test_legacy_account_without_member_is_archived(self):
        account = AdminUser(username='legacy-'+self.token,display_name='Legacy',password_hash='unused')
        db.session.add(account);db.session.commit()
        self.signin(self.primary)
        self.assertEqual(self.post(f'/admin/administradores/{account.id}/eliminar',confirm='yes').status_code,303)
        member = TeamMember.query.filter_by(admin_id=account.id).one()
        self.assertIsNotNone(member.removed_at)
        self.assertFalse(account.active)
