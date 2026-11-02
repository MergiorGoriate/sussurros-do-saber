"""Exercise real ORM transactions and mock only the external HTTP transport."""
from datetime import timedelta
from unittest.mock import Mock, patch
import unittest
import requests
from flask import Flask
from models import Article, Author, Category, Journal, db, utcnow
from indexnow_service import ENDPOINT, KEY, IndexNowNotification, install_indexnow, process_pending
ORIGIN = 'https://www.sussurrosdosaber.com'

def article(status='draft', slug='artigo-teste'):
    author = Author.query.first()
    category = Category.query.first()
    if not author:
        author = Author(name='Autor', slug='autor')
        category = Category(name='Biologia', slug='biologia')
        db.session.add_all([author, category])
    item = Article(title='Título', slug=slug, summary='Resumo', body='Texto', status=status, author_rel=author, category_rel=category)
    db.session.add(item)
    return item

def urls():
    return [row.url for row in IndexNowNotification.query.order_by(IndexNowNotification.id)]

class IndexNowTests(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite://', INDEXNOW_ENABLED=True)
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        install_indexnow(self.app, ORIGIN)

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_publication_queued_transactionally_without_http(self):
        app = self.app
        with patch('indexnow_service.requests.post') as post:
            article('published')
            db.session.flush()
            assert urls() == []
            db.session.commit()
            assert urls() == [ORIGIN + '/artigo/artigo-teste']
            post.assert_not_called()

    def test_private_states_are_not_submitted_1(self):
        app = self.app
        status = 'draft'
        item = article(status)
        db.session.commit()
        item.body = 'Alteração privada'
        db.session.commit()
        assert urls() == []

    def test_private_states_are_not_submitted_2(self):
        app = self.app
        status = 'scheduled'
        item = article(status)
        db.session.commit()
        item.body = 'Alteração privada'
        db.session.commit()
        assert urls() == []

    def test_private_states_are_not_submitted_3(self):
        app = self.app
        status = 'approved'
        item = article(status)
        db.session.commit()
        item.body = 'Alteração privada'
        db.session.commit()
        assert urls() == []

    def test_private_states_are_not_submitted_4(self):
        app = self.app
        status = 'rejected'
        item = article(status)
        db.session.commit()
        item.body = 'Alteração privada'
        db.session.commit()
        assert urls() == []

    def test_scheduled_becoming_published_queues_once(self):
        app = self.app
        item = article('scheduled')
        db.session.commit()
        item.status = 'published'
        db.session.commit()
        assert len(urls()) == 1
        db.session.commit()
        assert len(urls()) == 1

    def test_intermediate_public_state_is_never_exposed(self):
        app = self.app
        item = article('draft')
        db.session.commit()
        item.status = 'published'
        db.session.flush()
        item.status = 'draft'
        db.session.commit()
        assert urls() == []

    def test_new_then_deleted_public_object_is_not_exposed(self):
        app = self.app
        item = article('published')
        db.session.flush()
        db.session.delete(item)
        db.session.commit()
        assert urls() == []

    def test_rollback_does_not_leak_or_send_notification(self):
        app = self.app
        article('published')
        db.session.flush()
        db.session.rollback()
        db.session.commit()
        assert urls() == []

    def test_updates_and_slug_changes_include_old_and_new_urls(self):
        app = self.app
        item = article('published')
        db.session.commit()
        item.slug = 'novo-titulo'
        item.body = 'Novo texto'
        db.session.commit()
        assert urls() == [ORIGIN + '/artigo/artigo-teste', ORIGIN + '/artigo/artigo-teste', ORIGIN + '/artigo/novo-titulo']

    def test_unpublish_then_delete_keeps_original_public_url(self):
        app = self.app
        item = article('published')
        db.session.commit()
        item.status = 'draft'
        item.slug = 'rascunho-privado'
        db.session.flush()
        db.session.delete(item)
        db.session.commit()
        assert urls() == [ORIGIN + '/artigo/artigo-teste'] * 2

    def test_technical_timestamp_change_does_not_notify(self):
        app = self.app
        item = article('published')
        db.session.commit()
        item.updated_at = utcnow() + timedelta(seconds=5)
        db.session.commit()
        assert len(urls()) == 1

    def test_public_journal_and_withdrawal(self):
        app = self.app
        item = Journal(title='Revista', slug='revista', field='Ciência', description='Texto')
        db.session.add(item)
        db.session.commit()
        assert urls() == []
        item.published = True
        db.session.commit()
        item.published = False
        db.session.commit()
        assert urls() == [ORIGIN + '/revistas/revista'] * 2

    def test_api_payload_uses_canonical_origin_and_deduplicates_1(self):
        app = self.app
        status = 200
        item = article('published')
        db.session.commit()
        item.body = 'Actualização'
        db.session.commit()
        with patch('indexnow_service.requests.post', return_value=Mock(status_code=status)) as post:
            assert process_pending(app) == 2
            post.assert_called_once_with(ENDPOINT, json={'host': 'www.sussurrosdosaber.com', 'key': KEY, 'keyLocation': ORIGIN + '/' + KEY + '.txt', 'urlList': [ORIGIN + '/artigo/artigo-teste']}, timeout=(3, 10), allow_redirects=False)
            assert process_pending(app) == 0
            assert post.call_count == 1
        assert all((row.sent_at and row.last_status == status for row in IndexNowNotification.query.all()))

    def test_api_payload_uses_canonical_origin_and_deduplicates_2(self):
        app = self.app
        status = 202
        item = article('published')
        db.session.commit()
        item.body = 'Actualização'
        db.session.commit()
        with patch('indexnow_service.requests.post', return_value=Mock(status_code=status)) as post:
            assert process_pending(app) == 2
            post.assert_called_once_with(ENDPOINT, json={'host': 'www.sussurrosdosaber.com', 'key': KEY, 'keyLocation': ORIGIN + '/' + KEY + '.txt', 'urlList': [ORIGIN + '/artigo/artigo-teste']}, timeout=(3, 10), allow_redirects=False)
            assert process_pending(app) == 0
            assert post.call_count == 1
        assert all((row.sent_at and row.last_status == status for row in IndexNowNotification.query.all()))

    def test_failures_are_persisted_and_retried_without_affecting_article_1(self):
        app = self.app
        failure = requests.Timeout()
        item = article('published')
        db.session.commit()
        kwargs = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': Mock(status_code=failure, headers={'Retry-After': '120'})}
        with patch('indexnow_service.requests.post', **kwargs):
            assert process_pending(app) == 0
        row = IndexNowNotification.query.one()
        assert row.sent_at is None and row.attempts == 1 and row.last_error
        assert row.next_attempt_at > utcnow()
        assert db.session.get(Article, item.id).status == 'published'
        row.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.session.commit()
        with patch('indexnow_service.requests.post', return_value=Mock(status_code=200)):
            assert process_pending(app) == 1
        assert row.attempts == 2 and row.sent_at is not None

    def test_failures_are_persisted_and_retried_without_affecting_article_2(self):
        app = self.app
        failure = 403
        item = article('published')
        db.session.commit()
        kwargs = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': Mock(status_code=failure, headers={'Retry-After': '120'})}
        with patch('indexnow_service.requests.post', **kwargs):
            assert process_pending(app) == 0
        row = IndexNowNotification.query.one()
        assert row.sent_at is None and row.attempts == 1 and row.last_error
        assert row.next_attempt_at > utcnow()
        assert db.session.get(Article, item.id).status == 'published'
        row.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.session.commit()
        with patch('indexnow_service.requests.post', return_value=Mock(status_code=200)):
            assert process_pending(app) == 1
        assert row.attempts == 2 and row.sent_at is not None

    def test_failures_are_persisted_and_retried_without_affecting_article_3(self):
        app = self.app
        failure = 429
        item = article('published')
        db.session.commit()
        kwargs = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': Mock(status_code=failure, headers={'Retry-After': '120'})}
        with patch('indexnow_service.requests.post', **kwargs):
            assert process_pending(app) == 0
        row = IndexNowNotification.query.one()
        assert row.sent_at is None and row.attempts == 1 and row.last_error
        assert row.next_attempt_at > utcnow()
        assert db.session.get(Article, item.id).status == 'published'
        row.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.session.commit()
        with patch('indexnow_service.requests.post', return_value=Mock(status_code=200)):
            assert process_pending(app) == 1
        assert row.attempts == 2 and row.sent_at is not None

    def test_failures_are_persisted_and_retried_without_affecting_article_4(self):
        app = self.app
        failure = 503
        item = article('published')
        db.session.commit()
        kwargs = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': Mock(status_code=failure, headers={'Retry-After': '120'})}
        with patch('indexnow_service.requests.post', **kwargs):
            assert process_pending(app) == 0
        row = IndexNowNotification.query.one()
        assert row.sent_at is None and row.attempts == 1 and row.last_error
        assert row.next_attempt_at > utcnow()
        assert db.session.get(Article, item.id).status == 'published'
        row.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.session.commit()
        with patch('indexnow_service.requests.post', return_value=Mock(status_code=200)):
            assert process_pending(app) == 1
        assert row.attempts == 2 and row.sent_at is not None

    def test_disable_switch_stops_collection_and_delivery(self):
        app = self.app
        app.config['INDEXNOW_ENABLED'] = False
        article('published')
        db.session.commit()
        assert urls() == []
        with patch('indexnow_service.requests.post') as post:
            assert process_pending(app) == 0
            post.assert_not_called()

    def test_foreign_host_cannot_be_sent(self):
        app = self.app
        db.session.add(IndexNowNotification(url='https://example.org/artigo/privado'))
        db.session.commit()
        with patch('indexnow_service.requests.post') as post:
            assert process_pending(app) == 0
            post.assert_not_called()
        assert IndexNowNotification.query.one().last_error

    def test_savepoint_rollback_does_not_lose_outer_changes(self):
        app = self.app
        item = article('draft')
        db.session.commit()
        item.status = 'published'
        nested = db.session.begin_nested()
        item.slug = 'nao-confirmado'
        db.session.flush()
        nested.rollback()
        db.session.commit()
        assert urls() == [ORIGIN + '/artigo/artigo-teste']

    def test_rolled_back_savepoint_publication_stays_private(self):
        app = self.app
        item = article('draft')
        db.session.commit()
        nested = db.session.begin_nested()
        item.status = 'published'
        db.session.flush()
        nested.rollback()
        db.session.commit()
        assert urls() == []

    def test_cli_drains_pending_outbox(self):
        app = self.app
        article('published')
        db.session.commit()
        with patch('indexnow_service.requests.post', return_value=Mock(status_code=200)):
            result = app.test_cli_runner().invoke(args=['processar-indexnow'])
        assert result.exit_code == 0, result.output
        assert '1 notificação' in result.output

    def test_worker_starts_only_after_commit(self):
        app = self.app
        with patch('indexnow_service.wake_worker') as wake:
            article('published')
            db.session.flush()
            wake.assert_not_called()
            db.session.commit()
            wake.assert_called_once_with(app)

    def test_migration_table_creation_is_idempotent(self):
        app = self.app
        IndexNowNotification.__table__.create(db.engine, checkfirst=True)
        IndexNowNotification.__table__.create(db.engine, checkfirst=True)
        assert IndexNowNotification.query.count() == 0
