import secrets
import unittest
from datetime import timedelta
from app import app, seed_database
from models import db, Journal, Article, utcnow
from submission_models import Researcher
from reader_accounts import ReaderJournal, ReaderArticle
from werkzeug.security import generate_password_hash


class ReaderAccountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        with app.app_context():
            seed_database()

    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        token = secrets.token_hex(8)
        self.account = Researcher(name='Leitor', email=token+'@example.org',
            password_hash=generate_password_hash('secure-reader-password'),
            token_nonce=token, verified=True)
        self.journal = Journal(title='Artigo '+token, article_title='Artigo de leitura '+token,
            slug='reader-'+token, field='Biologia', description='Teste', published=True)
        db.session.add_all([self.account, self.journal])
        db.session.commit()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def sign_in(self, client=None):
        client = client or self.client
        with client.session_transaction() as session:
            session['researcher_id'] = self.account.id
            session['researcher_nonce'] = self.account.token_nonce
            session['csrf_token'] = 'reader-csrf'

    def update(self, action='saved', enabled='true'):
        return self.client.post('/conta/revistas/'+self.journal.slug,
            data={'csrf_token':'reader-csrf','action':action,'enabled':enabled})

    def test_authentication_csrf_and_account_isolation(self):
        self.assertEqual(self.update().status_code,401)
        self.sign_in()
        self.assertEqual(self.client.post('/conta/revistas/'+self.journal.slug,
            data={'action':'saved','enabled':'true'}).status_code,400)
        self.assertEqual(self.update().status_code,200)
        self.assertTrue(ReaderJournal.query.filter_by(owner_id=self.account.id).one().saved)
        second = app.test_client()
        self.sign_in(second)
        self.assertTrue(second.get('/conta/revistas/'+self.journal.slug).json['saved'])
        other = Researcher(name='Outro leitor',email=secrets.token_hex(8)+'@example.org',
            password_hash='unused',token_nonce='other-reader',verified=True)
        db.session.add(other)
        db.session.commit()
        with second.session_transaction() as session:
            session['researcher_id'] = other.id
            session['researcher_nonce'] = other.token_nonce
        self.assertFalse(second.get('/conta/revistas/'+self.journal.slug).json['saved'])
        with second.session_transaction() as session:
            session['researcher_nonce'] = 'invalid'
        self.assertEqual(second.get('/conta/revistas/'+self.journal.slug).status_code,401)
        self.assertEqual(self.update(enabled='false').status_code,200)
        self.assertFalse(self.client.get('/conta/revistas/'+self.journal.slug).json['saved'])

    def test_verified_follow_and_notifications(self):
        self.sign_in()
        self.account.verified = False
        db.session.commit()
        self.assertEqual(self.update('following').status_code,403)
        self.assertEqual(self.update('saved').status_code,200)
        self.account.verified = True
        db.session.commit()
        self.assertEqual(self.update('following').status_code,200)
        row = ReaderJournal.query.filter_by(owner_id=self.account.id).one()
        followed_at = row.followed_at
        self.assertEqual(self.update('following').status_code,200)
        self.assertEqual(row.followed_at,followed_at)
        row.followed_at = utcnow()-timedelta(days=1)
        self.journal.updated_at = utcnow()
        db.session.commit()
        response = self.client.get('/conta/notificacoes')
        self.assertIn(self.journal.article_title.encode(),response.data)
        self.assertEqual(self.client.get('/conta/sessao').json['notification_count'], 1)
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.update('following','false')
        self.assertEqual(self.client.get('/conta/sessao').json['notification_count'], 0)
        self.assertNotIn(self.journal.article_title.encode(),self.client.get('/conta/notificacoes').data)

    def test_login_rotates_csrf_and_registration_validation(self):
        state = self.client.get('/conta/sessao').json
        self.assertFalse(state['authenticated'])
        self.assertEqual(state['notification_count'], 0)
        response = self.client.post('/conta/entrar', data={'csrf_token':state['csrf'],
            'email':self.account.email,'password':'secure-reader-password'})
        self.assertTrue(response.json['ok'])
        self.assertNotEqual(response.json['csrf'],state['csrf'])
        self.assertEqual(self.client.post('/conta/criar-conta', data={
            'csrf_token':response.json['csrf'],'name':'Leitor','email':'bad','password':'short'}).status_code,400)

    def test_private_journals_cannot_be_saved(self):
        self.sign_in()
        self.journal.published = False
        db.session.commit()
        self.assertEqual(self.update().status_code,404)

    def test_saved_article_is_listed_once_and_removed_across_sessions(self):
        self.sign_in()
        article = Article.public_query().first()
        endpoint = '/conta/artigos/' + str(article.id)
        fields = {'csrf_token': 'reader-csrf', 'enabled': 'true'}
        for _ in range(2):
            self.assertEqual(self.client.post(endpoint, data=fields).status_code, 200)
        self.assertEqual(ReaderArticle.query.filter_by(owner_id=self.account.id, article_id=article.id).count(), 1)
        second = app.test_client(); self.sign_in(second)
        html = second.get('/conta/biblioteca').data
        self.assertIn(article.title.encode(), html)
        self.assertIn(('data-reader-remove-article="' + str(article.id) + '"').encode(), html)
        self.assertIn(article.id, second.get('/conta/sessao').json['saved_articles'])
        fields['enabled'] = 'false'
        self.assertEqual(second.post(endpoint, data=fields).status_code, 200)
        self.assertNotIn(article.title.encode(), self.client.get('/conta/biblioteca').data)
        self.assertNotIn(article.id, self.client.get('/conta/sessao').json['saved_articles'])

    def test_notification_counter_excludes_private_content_and_other_accounts(self):
        self.sign_in(); self.update('following')
        row = ReaderJournal.query.filter_by(owner_id=self.account.id).one()
        row.followed_at = utcnow() - timedelta(days=1)
        self.journal.updated_at = utcnow(); db.session.commit()
        self.assertEqual(self.client.get('/conta/sessao').json['notification_count'], 1)
        self.assertEqual(app.test_client().get('/conta/sessao').json['notification_count'], 0)
        self.journal.published = False; db.session.commit()
        self.assertEqual(self.client.get('/conta/sessao').json['notification_count'], 0)
        self.assertNotIn(self.journal.article_title.encode(), self.client.get('/conta/notificacoes').data)
        self.journal.published = True; self.account.verified = False; db.session.commit()
        self.assertEqual(self.client.get('/conta/sessao').json['notification_count'], 0)

    def test_notifications_acknowledge_only_the_seen_revision(self):
        self.sign_in(); self.update('following')
        self.assertIn(b'Sem novas', self.client.get('/conta/notificacoes').data)
        row = ReaderJournal.query.filter_by(owner_id=self.account.id).one()
        row.followed_at = utcnow() - timedelta(days=2)
        seen = utcnow() - timedelta(days=1)
        self.journal.updated_at = seen; db.session.commit()
        self.assertEqual(self.client.get('/conta/sessao').json['notification_count'], 1)
        self.assertIn(b'data-reader-mark-read', self.client.get('/conta/notificacoes').data)
        fields = {'csrf_token': 'reader-csrf', 'action': 'read', 'enabled': 'true', 'revision': seen.isoformat()}
        endpoint = '/conta/revistas/' + self.journal.slug
        self.journal.updated_at = utcnow(); db.session.commit()
        self.assertEqual(self.client.post(endpoint, data=fields).status_code, 200)
        self.assertEqual(self.client.get('/conta/sessao').json['notification_count'], 1)
        fields['revision'] = self.journal.updated_at.isoformat()
        for _ in range(2):
            self.assertEqual(self.client.post(endpoint, data=fields).status_code, 200)
        self.assertTrue(row.following)
        self.assertEqual(self.client.get('/conta/sessao').json['notification_count'], 0)
        fields['revision'] = (utcnow() + timedelta(days=1)).isoformat()
        self.assertEqual(self.client.post(endpoint, data=fields).status_code, 400)
        self.account.verified = False; db.session.commit()
        self.assertEqual(self.update('following', 'false').status_code, 200)

    def test_library_uses_legacy_article_heading(self):
        self.sign_in()
        self.journal.article_title = ''
        self.journal.content_markdown = '# Título do artigo antigo\n\nConteúdo.'
        db.session.commit()
        self.assertEqual(self.update().status_code,200)
        self.assertIn('Título do artigo antigo'.encode(),
                      self.client.get('/conta/biblioteca').data)
