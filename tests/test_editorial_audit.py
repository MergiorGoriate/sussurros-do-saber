"""Real login/2FA and editorial regressions, with synthetic isolated records."""
from datetime import date
import unittest
from werkzeug.security import generate_password_hash
from admin import totp_code
from app import app
from models import db
from governance import DEFAULT_ROLES, PERMISSIONS, has_permission, seed_roles
from governance_models import TeamRole, StaffPeerReview, StaffNotice
import test_permission_matrix as matrix


class EditorialAuditTests(unittest.TestCase):
    def setUp(self):
        matrix.PermissionMatrixTests.setUp(self)
        from extensions import limiter
        previous = limiter.enabled
        limiter.enabled = False
        self.addCleanup(setattr, limiter, 'enabled', previous)

    tearDown = matrix.PermissionMatrixTests.tearDown
    member = matrix.PermissionMatrixTests.member
    manuscript = matrix.PermissionMatrixTests.manuscript
    article = matrix.PermissionMatrixTests.article
    signin = matrix.PermissionMatrixTests.signin
    post = matrix.PermissionMatrixTests.post
    grant = matrix.PermissionMatrixTests.grant
    operation = matrix.PermissionMatrixTests.operation

    def login(self, account):
        account.password_hash = generate_password_hash('isolated-audit-password', method='pbkdf2:sha256:1000')
        db.session.commit()
        self.client.get('/admin/login')
        with self.client.session_transaction() as state:
            token = state['csrf_token']
        result = self.client.post('/admin/login', data={'csrf_token': token, 'username': account.username, 'password': 'isolated-audit-password'})
        self.assertIn('/admin/verificar-2fa', result.location)
        self.client.get(result.location)
        with self.client.session_transaction() as state:
            token = state['csrf_token']
        result = self.client.post('/admin/verificar-2fa', data={'csrf_token': token, 'code': totp_code(account.totp_secret)})
        self.assertEqual(result.status_code, 302)
        with self.client.session_transaction() as state:
            self.assertTrue(state['admin_2fa_verified'])
            self.assertEqual(state['admin_id'], account.id)
            self.csrf = state['csrf_token']

    def logout(self):
        result = self.client.post('/admin/logout', data={'csrf_token': self.csrf})
        self.assertEqual(result.status_code, 302)
        with self.client.session_transaction() as state:
            self.assertFalse(state.get('admin_authenticated'))

    def execute(self, path, data):
        return self.client.get(path) if data is None else self.client.post(path, data={'csrf_token': self.csrf, **data})

    def test_each_permission_survives_real_logout_login_and_revocation(self):
        for permission in PERMISSIONS:
            with self.subTest(permission=permission):
                member = self.grant(permission)
                role = member.appointments[0].role
                _, path, data, check = self.operation(permission, member)
                self.login(member.admin)
                self.logout()
                db.session.expire_all()
                seed_roles()
                self.login(member.admin)
                self.assertEqual(role.permissions, [permission])
                response = self.execute(path, data)
                self.assertIn(response.status_code, [200, 302])
                db.session.expire_all()
                self.assertTrue(check(), permission)
                # Use a fresh resource when the successful operation deleted one.
                _, path, data, _ = self.operation(permission, member)
                self.logout()
                outsider = self.grant(permission)
                outsider.appointments[0].role.permissions = []
                db.session.commit()
                self.login(outsider.admin)
                self.assertIn(self.execute(path, data).status_code, [403, 404])
                self.logout()
                self.login(member.admin)
                role.permissions = []
                db.session.commit()
                self.assertIn(self.execute(path, data).status_code, [403, 404])
                self.logout()

    def test_every_default_role_permissions_operations_and_role_change_after_login(self):
        for code, _, _, expected in DEFAULT_ROLES:
            with self.subTest(role=code):
                member = self.member(code)
                role = member.appointments[0].role
                saved = list(role.permissions)
                # Defaults may have been customised by another synthetic test.
                role.permissions = expected[:]
                db.session.commit()
                try:
                    self.login(member.admin)
                    self.logout()
                    self.login(member.admin)
                    with app.test_request_context('/admin/trabalho'):
                        from flask import session
                        session['admin_id'] = member.admin_id
                        for permission in PERMISSIONS:
                            self.assertEqual(has_permission(permission), permission in expected, (code, permission))
                    for permission in expected:
                        _, path, data, check = self.operation(permission, member)
                        self.assertIn(self.execute(path, data).status_code, [200, 302], (code, permission))
                        db.session.expire_all()
                        self.assertTrue(check(), (code, permission))
                    # Changing the mandate takes effect in an already open session.
                    replacement = TeamRole(code='empty_' + self.token + code, name='Sem poderes', permissions=[])
                    db.session.add(replacement)
                    member.appointments[0].role = replacement
                    db.session.commit()
                    for permission in expected:
                        _, path, data, _ = self.operation(permission, member)
                        self.assertIn(self.execute(path, data).status_code, [403, 404], (code, permission))
                    self.logout()
                finally:
                    role.permissions = saved
                    db.session.commit()

    def test_assigned_editor_receives_report_and_can_consult_without_assign_power(self):
        editor = self.member('associate_editor', self.journal.id)
        reviewer = self.member('reviewer', self.journal.id)
        item, _ = self.manuscript(editor)
        review = StaffPeerReview(manuscript_id=item.id, reviewer_id=reviewer.id, version_number=1, due_on=date.today())
        db.session.add(review); db.session.commit()
        self.signin(reviewer.admin)
        path = f'/admin/pareceres/{review.id}'
        self.assertEqual(self.post(path, action='accept', no_conflict='on').status_code, 302)
        report = 'Parecer confidencial fundamentado e associado ao manuscrito correcto. ' * 3
        self.assertEqual(self.post(path, action='submit', report=report, recommendation='minor_revision').status_code, 302)
        db.session.expire_all()
        self.assertEqual(review.report, report.strip())
        self.assertEqual(review.reviewer_id, reviewer.id)
        self.assertEqual(review.manuscript_id, item.id)
        self.assertIsNotNone(review.submitted_at)
        self.assertTrue(StaffNotice.query.filter_by(admin_id=editor.admin_id, resource_type='manuscript', resource_id=item.id).count())
        self.signin(editor.admin)
        listing = f'/admin/pareceres?manuscript_id={item.id}'
        response = self.client.get(listing)
        self.assertEqual(response.status_code, 200)
        self.assertIn(report.strip().encode(), response.data)
        self.assertNotIn(b'name="reviewer_id"', response.data)
        self.assertEqual(self.post('/admin/pareceres', manuscript_id=item.id, reviewer_id=reviewer.id, due_on=str(date.today())).status_code, 403)
        outsider = self.member('associate_editor', self.journal.id)
        self.signin(outsider.admin)
        self.assertEqual(self.client.get(listing).status_code, 403)
        self.signin(reviewer.admin)
        self.assertEqual(self.client.get(listing).status_code, 403)
        self.signin(editor.admin)
        editor.appointments[0].active = False; db.session.commit()
        self.assertEqual(self.client.get(listing).status_code, 403)

    def test_readonly_inventory_excludes_archived_member_even_with_live_mandate(self):
        from models import utcnow
        from scripts.audit_permissions import inspect_database
        member = self.grant('contacts.manage')
        member.removed_at = utcnow()
        db.session.commit()
        record = next(r for r in inspect_database(db.engine.url.render_as_string(hide_password=False))['members'] if r['member_id'] == member.id)
        self.assertTrue(record['removed'])
        self.assertEqual(record['effective_general'], [])
        self.assertFalse(has_permission('contacts.manage', member=member))

    def test_secretariat_custom_form_choices_survive_logout_seed_and_new_login(self):
        member = self.member('secretariat')
        role = member.appointments[0].role
        saved = list(role.permissions)
        choices = ['tasks.manage', 'article.write', 'reports.read', 'contacts.manage']
        try:
            self.signin(self.primary)
            self.assertEqual(self.post('/admin/funcoes', id=role.id, name=role.name,
                                       permissions=choices).status_code, 302)
            self.csrf = 'test'
            self.logout()
            seed_roles()
            db.session.expire_all()
            self.login(member.admin)
            self.assertEqual(set(role.permissions), set(choices))
            for permission in choices:
                _, path, data, check = self.operation(permission, member)
                self.assertIn(self.execute(path, data).status_code, [200, 302])
                db.session.expire_all()
                self.assertTrue(check())
            self.logout()
        finally:
            role.permissions = saved
            db.session.commit()

    def test_unlinked_collaborator_cannot_receive_electronic_editor_or_review_assignment(self):
        editor = self.member('associate_editor', self.journal.id)
        reviewer = self.member('reviewer', self.journal.id)
        unlinked_editor = self.member('associate_editor', self.journal.id)
        unlinked_reviewer = self.member('reviewer', self.journal.id)
        unlinked_editor.admin_id = unlinked_reviewer.admin_id = None
        item, _ = self.manuscript(editor)
        review = StaffPeerReview(manuscript_id=item.id, reviewer_id=reviewer.id, version_number=1, due_on=date.today())
        db.session.add(review); db.session.commit()
        self.signin(self.primary)
        page = self.client.get(f'/admin/pareceres?manuscript_id={item.id}')
        self.assertNotIn(f'value="{unlinked_reviewer.id}"'.encode(), page.data)
        self.assertEqual(self.post('/admin/pareceres', manuscript_id=item.id,
                                   reviewer_id=unlinked_reviewer.id, due_on=str(date.today())).status_code, 400)
        self.assertEqual(self.post(f'/admin/equipa/{editor.id}/responsabilidades', kind='editor',
                                   resource_id=item.id, target_id=unlinked_editor.id).status_code, 400)
        self.assertEqual(self.post(f'/admin/equipa/{reviewer.id}/responsabilidades', kind='review',
                                   resource_id=review.id, target_id=unlinked_reviewer.id).status_code, 400)
        db.session.expire_all()
        self.assertEqual(item.editor_id, editor.admin_id)
        self.assertEqual(review.status, 'invited')
