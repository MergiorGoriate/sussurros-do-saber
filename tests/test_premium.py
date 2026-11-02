"""Real HTTP and database coverage of the additive, no-payment Premium phase."""
from datetime import timedelta
import unittest
from unittest.mock import patch
import tempfile
import os
from pathlib import Path
import test_platform  # isolated SQLite and current application startup
from app import app
from extensions import limiter
from models import db, utcnow, Article, Journal, AdminUser
from submission_models import Researcher
from premium_models import (PremiumPlan, PremiumContent, PremiumSubscription, PremiumAudit,
    PremiumServiceRequest, PremiumEnrollment, PremiumAccessHistory)
from premium import entitled
from security_test_support import authenticate_test_session


class PremiumTests(unittest.TestCase):
    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        self.old_limiter = limiter.enabled
        limiter.enabled = False
        for model in (PremiumServiceRequest, PremiumEnrollment, PremiumAccessHistory, PremiumAudit, PremiumSubscription, PremiumContent, PremiumPlan):
            model.query.delete()
        self.account = Researcher.query.filter_by(email='premium@example.test').first()
        if self.account is None:
            self.account = Researcher(name='Leitor Premium', email='premium@example.test', password_hash='unused', token_nonce='test-nonce')
            db.session.add(self.account)
        self.account.active, self.account.verified = True, True
        self.plan = PremiumPlan(name='Premium Mensal', interval='monthly', price_minor=15000, currency='MZN', active=True)
        self.item = PremiumContent(title='Curso de métodos', summary='Descrição pública.', body='SEGREDO-PREMIUM\n\n**Aprender** <script>alert(1)</script>', kind='course', published=True)
        db.session.add_all([self.plan, self.item]); db.session.commit()
        self.client = app.test_client()

    def tearDown(self):
        db.session.rollback()
        limiter.enabled = self.old_limiter
        self.context.pop()

    def login(self, account=None):
        account = account or self.account
        with self.client.session_transaction() as session:
            session['researcher_id'] = account.id
            session['researcher_nonce'] = account.token_nonce

    def admin(self, primary=True):
        import time
        with self.client.session_transaction() as session:
            session['admin_authenticated'] = True
            session['admin_superuser'] = primary
            session['admin_last_activity_at'] = time.time()
            session['csrf_token'] = 'premium-csrf'
            authenticate_test_session(session)

    def grant(self, **changes):
        values = dict(owner_id=self.account.id, plan_id=self.plan.id, status='active', starts_at=utcnow()-timedelta(days=1),
                      ends_at=utcnow()+timedelta(days=30), source='complimentary', reason='Oferta para avaliação',
                      plan_snapshot=dict(name=self.plan.name, interval='monthly', price_minor=15000, currency='MZN'))
        values.update(changes)
        record = PremiumSubscription(**values); db.session.add(record); db.session.commit()
        return record

    def path(self):
        return f'/premium/conteudos/{self.item.id}'

    def test_public_pages_never_return_exclusive_body(self):
        for path in ['/premium', '/premium/', '/premium/biblioteca', self.path()]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 403 if path == self.path() else 200)
            self.assertNotIn(b'SEGREDO-PREMIUM', response.data)
            self.assertIn('no-store', response.headers['Cache-Control'])
            self.assertIn('Cookie', response.headers['Vary'])
        self.assertIn('noindex', self.client.get(self.path()).headers['X-Robots-Tag'])

    def test_free_reader_and_forged_membership_flags_are_denied(self):
        self.login()
        with self.client.session_transaction() as session:
            session['premium'] = True
            session['subscription_status'] = 'active'
        response = self.client.get(self.path()+'?premium=true')
        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b'SEGREDO-PREMIUM', response.data)

    def test_active_subscriber_receives_sanitized_content(self):
        self.grant(); self.login()
        response = self.client.get(self.path())
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'SEGREDO-PREMIUM', response.data)
        self.assertNotIn(b'<script>alert(1)</script>', response.data)
        self.assertIn('private', response.headers['Cache-Control'])
        self.assertIn('noarchive', response.headers['X-Robots-Tag'])

    def test_expired_future_cancelled_and_suspended_are_denied(self):
        sub = self.grant(); self.login()
        for state, start, end in [
            ('active', utcnow()-timedelta(days=2), utcnow()-timedelta(days=1)),
            ('active', utcnow()+timedelta(days=1), utcnow()+timedelta(days=2)),
            ('cancelled', utcnow()-timedelta(days=1), utcnow()+timedelta(days=1)),
            ('suspended', utcnow()-timedelta(days=1), utcnow()+timedelta(days=1))]:
            sub.status, sub.starts_at, sub.ends_at = state, start, end; db.session.commit()
            self.assertEqual(self.client.get(self.path()).status_code, 403)

    def test_expiry_boundary_is_exclusive_and_start_inclusive(self):
        sub = self.grant()
        self.assertTrue(entitled(sub, sub.starts_at))
        self.assertFalse(entitled(sub, sub.ends_at))

    def test_account_revocation_verification_and_nonce_revalidated(self):
        self.grant(); self.login()
        for field, invalid, valid in [('active',False,True), ('verified',False,True), ('token_nonce','changed','test-nonce')]:
            setattr(self.account, field, invalid); db.session.commit()
            self.assertEqual(self.client.get(self.path()).status_code, 403)
            setattr(self.account, field, valid); db.session.commit()

    def test_other_account_cannot_use_subscription(self):
        self.grant()
        other = Researcher(name='Outra conta', email='other-premium@example.test', password_hash='unused', verified=True,
                           active=True, token_nonce='other-nonce')
        old = Researcher.query.filter_by(email=other.email).first()
        if old: other = old
        else: db.session.add(other); db.session.commit()
        self.login(other)
        self.assertEqual(self.client.get(self.path()).status_code, 403)

    def test_draft_and_unknown_content_return_404_even_to_subscriber(self):
        self.grant(); self.login()
        self.item.published = False; db.session.commit()
        for path in [self.path(), '/premium/conteudos/2147483647']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn(b'SEGREDO-PREMIUM', response.data)
            self.assertIn('no-store', response.headers['Cache-Control'])

    def test_catalogue_filters_and_pagination_validate_inputs(self):
        self.assertIn(b'Curso de m', self.client.get('/premium/biblioteca?tipo=course').data)
        self.assertNotIn(b'Curso de m', self.client.get('/premium/biblioteca?tipo=event').data)
        for query in ['tipo=article', 'page=-1', 'page=9999999999999999999']:
            self.assertEqual(self.client.get('/premium/biblioteca?'+query).status_code, 400)

    def test_all_premium_admin_routes_require_primary_administrator(self):
        paths = ['/admin/premium', '/admin/premium/planos/novo', '/admin/premium/conteudos/novo',
                 '/admin/premium/assinaturas/nova', f'/admin/premium/planos/{self.plan.id}']
        for path in paths: self.assertEqual(self.client.get(path).status_code, 302)
        self.admin(False)
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.client.post(path, data={'csrf_token':'premium-csrf'}).status_code, 405 if path == '/admin/premium' else 403)

    def test_admin_pages_render_and_account_lookup_is_private(self):
        self.admin()
        for path in ['/admin/premium','/admin/premium/planos/novo','/admin/premium/conteudos/novo',
                     '/admin/premium/assinaturas/nova?q=premium@example.test']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertIn(b'premium@example.test', response.data)

    def test_mutations_require_csrf(self):
        self.admin()
        before = PremiumPlan.query.count()
        response = self.client.post('/admin/premium/planos/novo', data={'name':'Ataque'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PremiumPlan.query.count(), before)
        self.assertEqual(PremiumAudit.query.count(), 0)

    def plan_form(self, **changes):
        data = dict(name='Novo plano anual', interval='annual', price='1000.15', currency='MZN', active='on',
                    description='Conteúdos adicionais', csrf_token='premium-csrf')
        data.update(changes); return data

    def test_plan_creation_exact_money_and_audit(self):
        self.admin()
        self.assertEqual(self.client.post('/admin/premium/planos/novo', data=self.plan_form()).status_code, 302)
        plan = PremiumPlan.query.filter_by(name='Novo plano anual').one()
        self.assertEqual(plan.price_minor, 100015)
        self.assertEqual(PremiumAudit.query.one().action, 'plan.save')

    def test_invalid_prices_intervals_and_currencies_rejected_atomically(self):
        self.admin()
        for fields in [dict(price='NaN'),dict(price='Infinity'),dict(price='-1'),dict(price='2.345'),dict(price='0'),
                       dict(price='1e100000'),dict(interval='daily'),dict(currency='XXX')]:
            self.assertEqual(self.client.post('/admin/premium/planos/novo',data=self.plan_form(**fields)).status_code,400)
        self.assertEqual(PremiumPlan.query.count(), 1)
        self.assertEqual(PremiumAudit.query.count(), 0)

    def test_plan_edits_preserve_assigned_terms_and_access(self):
        sub = self.grant(); self.login(); self.admin()
        response = self.client.post(f'/admin/premium/planos/{self.plan.id}', data=self.plan_form(
            version=str(self.plan.version), price='2000.00', active=''))
        self.assertEqual(response.status_code,302)
        db.session.refresh(sub)
        self.assertEqual(sub.plan_snapshot['price_minor'],15000)
        self.assertTrue(entitled(sub))
        self.assertEqual(self.client.get(self.path()).status_code,200)

    def grant_form(self, **changes):
        data = dict(owner_id=str(self.account.id), plan_id=str(self.plan.id), starts_at=(utcnow()-timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
                    ends_at=(utcnow()+timedelta(days=30)).strftime('%Y-%m-%dT%H:%M'), reason='Oferta para avaliação',
                    complimentary='on', csrf_token='premium-csrf')
        data.update(changes);return data

    def test_grant_requires_confirmation_verified_account_and_valid_dates(self):
        self.admin()
        for changes in [dict(complimentary=''),dict(owner_id='9999999999999'),dict(ends_at='2020-01-01T00:00'),
                        dict(starts_at='invalid'),dict(reason='curto')]:
            self.assertEqual(self.client.post('/admin/premium/assinaturas/nova',data=self.grant_form(**changes)).status_code,400)
        self.account.verified=False;db.session.commit()
        self.assertEqual(self.client.post('/admin/premium/assinaturas/nova',data=self.grant_form()).status_code,400)
        self.assertEqual(PremiumSubscription.query.count(),0)

    def test_grant_is_complimentary_audited_and_cannot_be_duplicated(self):
        self.plan.benefits=['Benefício de oferta'];db.session.commit()
        self.admin()
        self.assertEqual(self.client.post('/admin/premium/assinaturas/nova',data=self.grant_form()).status_code,302)
        self.assertEqual(self.client.post('/admin/premium/assinaturas/nova',data=self.grant_form()).status_code,400)
        sub = PremiumSubscription.query.one()
        self.assertEqual(sub.source,'complimentary')
        self.assertEqual(sub.plan_snapshot['benefits'],['Benefício de oferta'])
        self.assertEqual(PremiumAudit.query.one().action,'subscription.grant')
        self.login();self.assertEqual(self.client.get(self.path()).status_code,200)

    def test_cancellation_revoke_and_renewal_take_effect_next_request(self):
        sub=self.grant();self.login();self.admin()
        for status, expected in [('cancelled',403),('active',200),('suspended',403)]:
            form=self.grant_form(status=status,version=str(sub.version))
            response=self.client.post(f'/admin/premium/assinaturas/{sub.id}',data=form)
            self.assertEqual(response.status_code,302)
            self.assertEqual(self.client.get(self.path()).status_code,expected)
            db.session.refresh(sub)
        self.assertEqual(PremiumAudit.query.count(),3)

    def test_stale_edits_rejected_without_overwriting(self):
        self.admin()
        response=self.client.post(f'/admin/premium/planos/{self.plan.id}',data=self.plan_form(version='0'))
        self.assertEqual(response.status_code,409)
        db.session.refresh(self.plan);self.assertEqual(self.plan.price_minor,15000)

    def test_content_admin_restricts_types_and_can_publish_unpublish(self):
        self.admin()
        form=dict(title='Nova entrevista',kind='article',summary='Descrição',body='Corpo exclusivo',published='on',csrf_token='premium-csrf')
        self.assertEqual(self.client.post('/admin/premium/conteudos/novo',data=form).status_code,400)
        form['kind']='interview'
        self.assertEqual(self.client.post('/admin/premium/conteudos/novo',data=form).status_code,302)
        item=PremiumContent.query.filter_by(title='Nova entrevista').one()
        self.assertTrue(item.published)
        form.update(version=str(item.version),published='')
        self.assertEqual(self.client.post(f'/admin/premium/conteudos/{item.id}',data=form).status_code,302)
        self.assertEqual(self.client.get(f'/premium/conteudos/{item.id}').status_code,404)

    def test_existing_portal_and_journal_articles_remain_free(self):
        article=Article.public_query().first()
        journal=Journal.query.filter_by(published=True).first()
        self.assertIsNotNone(article);self.assertIsNotNone(journal)
        for authenticated in [False,True]:
            if authenticated:self.login()
            for path in [f'/artigo/{article.slug}',f'/revistas/{journal.slug}','/artigos','/revistas','/feed.xml','/sitemap.xml']:
                response=self.client.get(path)
                self.assertEqual(response.status_code,200,path)
                self.assertNotIn(b'SEGREDO-PREMIUM',response.data)
        self.assertNotIn('premium',Article.__table__.columns)
        self.assertNotIn('premium',Journal.__table__.columns)

    def test_no_checkout_or_webhook_can_grant_access(self):
        self.login()
        for path in ['/premium/checkout','/premium/webhook','/premium/subscribe']:
            self.assertEqual(self.client.post(path,json={'paid':True,'plan_id':self.plan.id}).status_code,404)
        self.assertEqual(PremiumSubscription.query.count(),0)


class PremiumMigrationTests(unittest.TestCase):
    def test_upgrade_from_previous_head_is_additive_and_repeatable(self):
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, inspect, text
        with tempfile.TemporaryDirectory() as folder:
            url='sqlite:///'+str(Path(folder)/'premium.db')
            config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
            with patch.dict(os.environ,{'DATABASE_URL':url}):
                command.upgrade(config,'20261022_09')
                engine=create_engine(url)
                with engine.begin() as connection:
                    connection.execute(text("INSERT INTO category (id,name,slug) VALUES (123,'Preservada','preservada')"))
                    before_columns=inspect(connection).get_columns('article')
                command.upgrade(config,'head');command.upgrade(config,'head')
                with engine.connect() as connection:
                    self.assertEqual(connection.scalar(text('SELECT name FROM category WHERE id=123')),'Preservada')
                    self.assertEqual([c['name'] for c in before_columns],[c['name'] for c in inspect(connection).get_columns('article')])
                    self.assertEqual(connection.scalar(text('SELECT count(*) FROM premium_plan')),6)
                    self.assertEqual(connection.scalar(text('SELECT count(*) FROM premium_plan WHERE active')),0)
                    self.assertEqual(connection.scalar(text('SELECT version_num FROM alembic_version')),'20261102_20')
                    for table in ['premium_content','premium_subscription','premium_audit']:
                        self.assertIn(table,inspect(connection).get_table_names())
                engine.dispose()

