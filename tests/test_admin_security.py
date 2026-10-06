import os
import secrets
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import atexit
database_file = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
database_file.close()
os.environ['DATABASE_URL'] = 'sqlite:///' + database_file.name
os.environ['SECRET_KEY'] = 'admin-security-test-secret'
atexit.register(lambda: Path(database_file.name).unlink(missing_ok=True))
from werkzeug.security import generate_password_hash
from app import app, seed_database
from admin import complete_admin_login, begin_two_factor_challenge, totp_code
from models import AdminUser, Journal, db
from extensions import limiter


class AdminSecurityTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        seed_database()
        app.config.update(TESTING=True)
        self.rate = patch.object(limiter, 'enabled', False)
        self.rate.start()
        token = secrets.token_hex(6)
        self.account = AdminUser(username='security-'+token, display_name='Security test',
                                 password_hash=generate_password_hash('test-password-long'),
                                 two_factor_enabled=True, totp_secret='JBSWY3DPEHPK3PXP')
        self.journal = Journal(title='Security draft', slug='security-'+token,
                               field='Biologia', description='Security fixture',
                               published=False, content_markdown='Private draft')
        db.session.add_all([self.account, self.journal])
        db.session.commit()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()
        self.rate.stop()

    def login(self):
        with app.test_request_context():
            complete_admin_login(self.account)
            from flask import session
            values = dict(session)
        with self.client.session_transaction() as session:
            session.clear()
            session.update(values)

    def challenge(self):
        with app.test_request_context():
            begin_two_factor_challenge(administrator=self.account)
            from flask import session
            values = dict(session)
        with self.client.session_transaction() as session:
            session.clear()
            session.update(values)
        return values['csrf_token']

    def test_old_session_rejected_after_password_change(self):
        self.login()
        self.assertEqual(self.client.get('/admin').status_code, 200)
        old = self.account.security_version
        self.account.password_hash = generate_password_hash('new-long-password')
        db.session.commit()
        self.assertGreater(self.account.security_version, old)
        response = self.client.get('/admin')
        self.assertIn('/admin/login', response.location)

    def test_demoted_superadmin_cannot_reuse_session_privileges(self):
        self.account.is_superadmin = True
        db.session.commit()
        self.login()
        self.account.is_superadmin = False
        db.session.commit()
        self.assertIn('/admin/login', self.client.get('/admin/administradores').location)
        self.login()
        with self.client.session_transaction() as session:
            session['admin_superuser'] = True
        self.assertEqual(self.client.get('/admin/administradores').status_code, 403)

    def test_all_preview_routes_require_enrollment(self):
        self.account.two_factor_enabled = False
        self.account.totp_secret = None
        db.session.commit()
        self.login()
        for suffix in ('previsualizar', 'baixar.pdf'):
            response = self.client.get(f'/admin/revistas/{self.journal.id}/{suffix}')
            self.assertIn('/admin/seguranca/2fa', response.location)
        response = self.client.post('/admin/revistas/previsualizar-markdown')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get('/admin/seguranca/2fa').status_code, 200)

    def test_expired_challenge_rejected_even_with_valid_totp(self):
        token = self.challenge()
        with self.client.session_transaction() as session:
            session['pending_2fa_expires_at'] = time.time()-1
        response = self.client.post('/admin/verificar-2fa', data={
            'csrf_token':token, 'code':totp_code(self.account.totp_secret)})
        self.assertIn('/admin/login', response.location)
        with self.client.session_transaction() as session:
            self.assertNotIn('pending_2fa_security_stamp', session)
            self.assertFalse(session.get('admin_authenticated'))

    def test_changed_credentials_reject_pending_challenge(self):
        token = self.challenge()
        self.account.password_hash = generate_password_hash('another-new-password')
        db.session.commit()
        response = self.client.post('/admin/verificar-2fa', data={
            'csrf_token':token, 'code':totp_code(self.account.totp_secret)})
        self.assertIn('/admin/login', response.location)

    def test_valid_challenge_cleared_after_success(self):
        token = self.challenge()
        response = self.client.post('/admin/verificar-2fa', data={
            'csrf_token':token, 'code':totp_code(self.account.totp_secret)})
        self.assertEqual(response.location, '/admin')
        with self.client.session_transaction() as session:
            self.assertTrue(session['admin_authenticated'])
            self.assertNotIn('pending_2fa_expires_at', session)

    def test_environment_credential_change_revokes_session(self):
        with patch.dict(os.environ, ADMIN_USERNAME='primary-test',
                        ADMIN_PASSWORD_HASH='test-hash', ADMIN_TOTP_SECRET='JBSWY3DPEHPK3PXP'):
            with app.test_request_context():
                complete_admin_login(username='primary-test', superuser=True)
                from flask import session
                values = dict(session)
            with self.client.session_transaction() as session:
                session.update(values)
            self.assertEqual(self.client.get('/admin').status_code, 200)
            os.environ['ADMIN_PASSWORD_HASH'] = 'changed-test-hash'
            self.assertIn('/admin/login', self.client.get('/admin').location)

    def test_pdf_cache_reuses_bytes_and_changes_key_on_edit(self):
        from pdf_cache import cached_pdf_response
        with tempfile.TemporaryDirectory() as folder, patch.object(app, 'instance_path', folder):
            with patch('app.build_journal_pdf', return_value=b'%PDF-test') as build:
                from app import render_journal_pdf
                self.assertEqual(render_journal_pdf(self.journal).data, b'%PDF-test')
                self.assertEqual(render_journal_pdf(self.journal).data, b'%PDF-test')
                self.assertEqual(build.call_count, 1)
                self.journal.content_markdown = 'Edited private draft'
                self.assertEqual(render_journal_pdf(self.journal).data, b'%PDF-test')
                self.assertEqual(build.call_count, 2)
            self.assertEqual(Path(folder, 'pdf-cache').stat().st_mode & 0o777, 0o700)

    def test_pdf_concurrent_generation_returns_retry_response(self):
        import fcntl
        from pdf_cache import cached_pdf_response
        with tempfile.TemporaryDirectory() as folder, patch.object(app, 'instance_path', folder):
            root = Path(folder)/'pdf-cache'
            root.mkdir()
            with open(root/'generation.lock','wb') as slot:
                fcntl.flock(slot, fcntl.LOCK_EX|fcntl.LOCK_NB)
                with patch('app.build_journal_pdf') as build:
                    result = cached_pdf_response(self.journal, build)
                    self.assertEqual(result.status_code, 503)
                    self.assertEqual(result.headers['Retry-After'], '5')
                    build.assert_not_called()

    def test_pdf_route_has_specific_request_limit(self):
        self.journal.published = True
        db.session.commit()
        limiter.reset()
        with patch.object(limiter, 'enabled', True), patch('app.render_journal_pdf', return_value=b'%PDF-test'):
            statuses = [self.client.get('/revistas/'+self.journal.slug+'/baixar.pdf').status_code
                        for _ in range(11)]
        limiter.reset()
        self.assertEqual(statuses[:10], [200]*10)
        self.assertEqual(statuses[10], 429)

    def test_forwarded_host_is_not_trusted_by_default(self):
        response = self.client.get('/healthz', headers={'X-Forwarded-Host':'sussurrosdosaber.com'})
        self.assertEqual(response.status_code, 200)
