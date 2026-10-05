import json
import secrets
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import crypt, jwt
from google.auth.exceptions import TransportError
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from app import app
from extensions import limiter
from google_auth import GoogleIdentity
from models import Article, Journal, db
from reader_accounts import ReaderArticle, ReaderJournal
from submission_models import Researcher

CLIENT = 'test-client.apps.googleusercontent.com'


class GoogleAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption())
        cls.public_key = key.public_key().public_bytes(serialization.Encoding.PEM,
                                                      serialization.PublicFormat.SubjectPublicKeyInfo)
        cls.signer = crypt.RSASigner.from_string(private, key_id='fixture-key')

    def setUp(self):
        self.context = app.app_context(); self.context.push()
        self.client = app.test_client()
        self.settings = patch.dict(app.config, {'TESTING': True, 'GOOGLE_CLIENT_ID': CLIENT})
        self.settings.start()
        self.limit = patch.object(limiter, 'enabled', False); self.limit.start()
        self.subject = secrets.token_hex(12)
        self.email = self.subject + '@gmail.com'

    def tearDown(self):
        db.session.remove(); self.limit.stop(); self.settings.stop(); self.context.pop()

    def challenge(self):
        self.csrf = self.client.get('/conta/sessao').json['csrf']
        response = self.client.post('/conta/google/preparar', data={'csrf_token': self.csrf})
        self.nonce = response.json['nonce']
        return response

    def claims(self, **overrides):
        values = dict(sub=self.subject, email=self.email, email_verified=True, name='Leitor Google',
                      aud=CLIENT, iss='https://accounts.google.com', nonce=self.nonce,
                      exp=int(time.time()) + 300, iat=int(time.time()) - 1)
        values.update(overrides)
        return values

    def signed_login(self, **overrides):
        token = jwt.encode(self.signer, self.claims(**overrides)).decode()
        class Certificates:
            status = 200
            data = json.dumps({'fixture-key': self.public_key.decode()}).encode()
        with patch('google_auth.google_transport', return_value=lambda *a, **k: Certificates()):
            return self.client.post('/conta/google/entrar', data={'csrf_token': self.csrf, 'credential': token})

    def existing(self, email=None, verified=True):
        account = Researcher(name='Conta existente', email=email or self.email, verified=verified,
                             password_hash=generate_password_hash('old-secure-password'), token_nonce=secrets.token_hex(24))
        db.session.add(account); db.session.commit(); return account

    def sign_in(self, account, client=None):
        with (client or self.client).session_transaction() as state:
            state['researcher_id'] = account.id; state['researcher_nonce'] = account.token_nonce

    def test_real_signature_creates_passwordless_account_and_rotates_session(self):
        self.challenge(); previous = self.csrf
        result = self.signed_login()
        self.assertEqual(result.status_code, 200)
        self.assertNotEqual(result.json['csrf'], previous)
        account = Researcher.query.filter_by(email=self.email).one()
        self.assertEqual(account.password_hash, '')
        self.assertTrue(account.verified)
        self.assertEqual(db.session.get(GoogleIdentity, self.subject).owner_id, account.id)
        with self.client.session_transaction() as state:
            self.assertEqual(state['researcher_id'], account.id)
            self.assertNotIn('credential', state); self.assertNotIn('google_nonce', state)
        self.assertIn('no-store', self.client.get('/conta/sessao').headers['Cache-Control'])

    def test_signature_audience_issuer_expiry_nonce_and_verified_email(self):
        cases = [{'aud': 'other.apps.googleusercontent.com'}, {'iss': 'https://evil.invalid'},
                 {'exp': int(time.time()) - 20}, {'nonce': 'another-browser'}, {'email_verified': False}, {'sub': ''}]
        for values in cases:
            with self.subTest(values=values):
                self.challenge(); self.assertEqual(self.signed_login(**values).status_code, 401)
        self.challenge()
        class Certificates:
            status = 200
            data = b'{"fixture-key":"invalid-public-key"}'
        with patch('google_auth.google_transport', return_value=lambda *a, **k: Certificates()):
            token = jwt.encode(self.signer, self.claims()).decode()
            response = self.client.post('/conta/google/entrar', data={'csrf_token': self.csrf, 'credential': token})
        self.assertEqual(response.status_code, 401)
        self.assertIsNone(Researcher.query.filter_by(email=self.email).first())

    def test_invalid_signature_and_consumed_challenge(self):
        self.challenge()
        token = jwt.encode(self.signer, self.claims()).decode()
        parts = token.split('.')
        parts[2] = ('A' if parts[2][0] != 'A' else 'B') + parts[2][1:]
        class Certificates:
            status = 200
            data = json.dumps({'fixture-key': self.public_key.decode()}).encode()
        with patch('google_auth.google_transport', return_value=lambda *a, **k: Certificates()):
            response = self.client.post('/conta/google/entrar', data={
                'csrf_token': self.csrf, 'credential': '.'.join(parts)})
        self.assertEqual(response.status_code, 401)
        response = self.client.post('/conta/google/entrar', data={
            'csrf_token': self.csrf, 'credential': token})
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(Researcher.query.filter_by(email=self.email).first())

    def test_csrf_and_missing_expired_challenge(self):
        self.challenge()
        self.assertEqual(self.client.post('/conta/google/entrar', data={'credential': 'token'}).status_code, 400)
        with self.client.session_transaction() as state:
            state['google_nonce_until'] = 0
        with patch('google_auth.id_token.verify_oauth2_token') as verify:
            self.assertEqual(self.client.post('/conta/google/entrar', data={'csrf_token': self.csrf, 'credential': 'token'}).status_code, 400)
            verify.assert_not_called()

    def test_disabled_and_transport_failure_do_not_block_public_content(self):
        self.challenge()
        with patch('google_auth.id_token.verify_oauth2_token', side_effect=TransportError('offline')):
            self.assertEqual(self.client.post('/conta/google/entrar', data={'csrf_token': self.csrf, 'credential': 'token'}).status_code, 503)
        with patch.dict(app.config, {'GOOGLE_CLIENT_ID': ''}):
            self.assertEqual(self.client.post('/conta/google/preparar', data={'csrf_token': self.csrf}).status_code, 503)
            home = self.client.get('/')
            self.assertEqual(home.status_code, 200)
            self.assertIn(b'data-reader-open', home.data)
            self.assertNotIn(b'https://accounts.google.com/gsi/client', home.data)

    def test_returning_identity_and_verified_gmail_keep_existing_preferences(self):
        account = self.existing()
        journal = Journal.query.filter_by(published=True).first()
        row = ReaderJournal(owner_id=account.id, journal_id=journal.id, saved=True, following=True)
        db.session.add(row); db.session.commit()
        self.challenge(); self.assertEqual(self.signed_login().status_code, 200)
        self.assertEqual(Researcher.query.filter_by(email=self.email).count(), 1)
        self.assertTrue(row.saved); self.assertTrue(row.following)
        self.challenge(); self.assertEqual(self.signed_login(email='changed@gmail.com').status_code, 200)
        self.assertEqual(GoogleIdentity.query.filter_by(subject=self.subject).count(), 1)
        self.assertTrue(self.client.get('/conta/sessao').json['authenticated'])

    def test_external_email_and_unverified_existing_account_require_explicit_link(self):
        for email, verified in [(self.subject + '@example.org', True), (self.email, False)]:
            with self.subTest(email=email):
                account = self.existing(email=email, verified=verified)
                self.challenge(); self.assertEqual(self.signed_login(email=email).status_code, 409)
                self.sign_in(account); self.challenge()
                self.assertEqual(self.signed_login(email=email).status_code, 200)
                self.client = app.test_client(); self.subject = secrets.token_hex(12)

    def test_inactive_account_and_cross_account_link_are_rejected(self):
        account = self.existing(); account.active = False; db.session.commit()
        self.challenge(); self.assertEqual(self.signed_login().status_code, 403)
        account.active = True; db.session.commit()
        other = self.existing(email=self.subject+'@example.org'); self.sign_in(other)
        self.challenge(); self.assertEqual(self.signed_login().status_code, 403)

    def test_google_only_account_has_no_password_login_or_recovery(self):
        self.challenge(); self.assertEqual(self.signed_login().status_code, 200)
        csrf = self.client.get('/conta/sessao').json['csrf']
        self.assertEqual(self.client.post('/conta/entrar', data={'csrf_token': csrf, 'email': self.email, 'password': 'any-password'}).status_code, 400)
        with patch('submissions.notify') as notify:
            self.client.post('/submissoes/recuperar', data={'csrf_token': csrf, 'email': self.email})
            notify.assert_not_called()

    def test_unified_favorites_idempotence_isolation_and_publication(self):
        account = self.existing(); self.sign_in(account)
        article = Article.query.filter_by(status='published').first()
        self.assertIsNotNone(article)
        csrf = self.client.get('/conta/sessao').json['csrf']
        path = '/conta/artigos/' + str(article.id)
        data = {'csrf_token': csrf, 'enabled': 'true'}
        self.assertEqual(self.client.post(path, data=data).status_code, 200)
        self.assertEqual(self.client.post(path, data=data).status_code, 200)
        self.assertEqual(ReaderArticle.query.filter_by(owner_id=account.id, article_id=article.id).count(), 1)
        self.assertIn(article.title.encode(), self.client.get('/conta/biblioteca').data)
        self.assertEqual(self.client.get('/favoritos').location, '/conta/biblioteca')
        other = app.test_client()
        self.assertEqual(other.post(path, data=data).status_code, 401)
        self.assertEqual(other.get('/conta/sessao').json['saved_articles'], [])
        self.assertEqual(self.client.post('/conta/artigos/99999999999999999999', data=data).status_code, 404)
        self.assertEqual(self.client.post(path, data={'csrf_token': csrf, 'enabled': 'false'}).status_code, 200)
        self.assertEqual(ReaderArticle.query.filter_by(owner_id=account.id).count(), 0)

    def test_import_merges_browser_favorites_without_duplicates(self):
        account = self.existing(); self.sign_in(account)
        article = Article.query.filter_by(status='published').first()
        journal = Journal.query.filter_by(published=True).first()
        csrf = self.client.get('/conta/sessao').json['csrf']
        data = {'csrf_token': csrf, 'article_ids': [str(article.id)]*2,
                'journal_slugs': [journal.slug]*2}
        for _ in range(2):
            self.assertEqual(self.client.post('/conta/importar-favoritos', data=data).status_code, 200)
        self.assertEqual(ReaderArticle.query.filter_by(owner_id=account.id).count(), 1)
        self.assertEqual(ReaderJournal.query.filter_by(owner_id=account.id).count(), 1)
        self.assertEqual(self.client.post('/conta/importar-favoritos', data={
            'csrf_token': csrf, 'article_ids': ['1']*101}).status_code, 400)

    def test_logout_suppresses_auto_prompt_and_migration_is_repeatable(self):
        account = self.existing(); self.sign_in(account)
        csrf = self.client.get('/conta/sessao').json['csrf']
        self.client.post('/submissoes/sair', data={'csrf_token': csrf})
        state = self.client.get('/conta/sessao').json
        self.assertFalse(state['authenticated']); self.assertTrue(state['google_prompt_suppressed'])
        for _ in range(2):
            result = app.test_cli_runner().invoke(args=['migrar-login-google'])
            self.assertEqual(result.exit_code, 0, result.output)
        self.assertIsNotNone(db.session.get(Researcher, account.id))
