"""Commercial invariants and subscriber workflow tests; no live provider requests."""
import secrets
import unittest
from datetime import timedelta
from unittest.mock import patch
from sqlalchemy import create_engine, inspect, text
from bs4 import BeautifulSoup
import test_premium_learning as existing
from app import app
from models import db, utcnow
from premium_models import (PremiumPlan, PremiumSubscription, PremiumContent, PremiumResource,
    PremiumEnrollment, PremiumAccessHistory, PremiumServiceRequest, PremiumCertificate, PremiumLesson, PremiumProgress)
from premium_commercial import annual_price
from premium_members import in_grace, process_membership_notices
from billing_models import BillingOrder, BillingJournal
from billing_service import lock_account, post_receipt, post_refund
from governance_models import StaffNotice


class MemberTests(unittest.TestCase):
    admin=existing.PremiumLearningTests.admin
    login=existing.PremiumLearningTests.login
    grant=existing.PremiumLearningTests.grant
    csrf=existing.PremiumLearningTests.csrf
    make_resource=existing.PremiumLearningTests.make_resource

    def setUp(self):
        for_setup=existing.PremiumLearningTests.setUp
        for_setup(self)
        for model in (PremiumServiceRequest,PremiumEnrollment,PremiumAccessHistory):model.query.delete()
        db.session.commit()

    def tearDown(self):
        db.session.rollback()
        for model in (PremiumServiceRequest,PremiumEnrollment,PremiumAccessHistory):model.query.delete()
        db.session.commit()
        existing.PremiumLearningTests.tearDown(self)

    def save_plan(self,plan,**values):
        self.admin()
        data=dict(csrf_token='premium-csrf',version=str(plan.version),tier=plan.tier,name=plan.name,
                  interval=plan.interval,price=str(plan.price_minor/100),currency=plan.currency,active='on',benefits='Benefício aprovado')
        data.update(values)
        return self.client.post(f'/admin/premium/planos/{plan.id}',data=data)

    def paid_order(self):
        order=BillingOrder(id=secrets.token_hex(16),owner_id=self.account.id,plan_id=self.plan.id,
            snapshot=dict(name=self.plan.name,interval='monthly',price_minor=15000,currency='MZN'),
            amount_minor=15000,currency='MZN',method='mpesa',provider='clicpay',live=True,provider_ref='CPAY'+secrets.token_hex(12),
            expires_at=utcnow()+timedelta(days=1))
        db.session.add(order);db.session.flush()
        post_receipt(order,lock_account(self.account.id,live=True));db.session.commit()
        return order

    def test_annual_price_is_derived_and_republication_required_after_monthly_change(self):
        self.plan.tier='pro';db.session.commit()
        annual=PremiumPlan(tier='pro',name='Pró Anual',interval='annual',price_minor=0,currency='MZN',active=False)
        db.session.add(annual);db.session.commit()
        response=self.save_plan(annual,price='0')
        self.assertEqual(response.status_code,302,response.text)
        self.assertEqual(annual.price_minor,annual_price(self.plan.price_minor))
        self.assertTrue(annual.active)
        response=self.save_plan(self.plan,price='500.00')
        self.assertEqual(response.status_code,302,response.text)
        self.assertEqual(annual.price_minor,480000)
        self.assertFalse(annual.active)
        self.assertEqual(self.client.get(f'/premium/planos/{annual.id}/condicoes').status_code,404)
        self.assertEqual(annual_price(101),970)

    def test_products_keep_their_identity_and_duplicate_products_are_rejected(self):
        self.plan.tier='pro';db.session.commit()
        self.assertEqual(self.save_plan(self.plan,tier='legacy').status_code,400)
        self.assertEqual(self.plan.tier,'pro')
        response=self.client.post('/admin/premium/planos/novo',data=dict(csrf_token='premium-csrf',
            name='Duplicado',tier='pro',interval='monthly',price='100.00',currency='MZN',active='on'))
        self.assertEqual(response.status_code,400)

    def test_new_products_need_explicit_resource_eligibility(self):
        self.plan.tier='max';db.session.commit();self.grant();self.login()
        self.assertEqual(self.client.get(f'/premium/conteudos/{self.item.id}').status_code,403)
        self.make_resource(kind='course',plan_ids=[self.plan.id])
        self.assertEqual(self.client.get(f'/premium/conteudos/{self.item.id}').status_code,200)

    def test_panel_requires_membership_but_keeps_records_after_expiry(self):
        self.assertEqual(self.client.get('/premium/painel').status_code,302)
        self.login();self.assertEqual(self.client.get('/premium/painel').status_code,403)
        self.assertEqual(PremiumSubscription.query.count(),0)
        sub=self.grant()
        response=self.client.get('/premium/painel')
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('O meu Prémio',response.text)
        sub.ends_at=utcnow()-timedelta(days=2);sub.starts_at=utcnow()-timedelta(days=5);db.session.commit()
        self.assertEqual(self.client.get('/premium/painel').status_code,200)
        self.assertEqual(self.client.get(f'/premium/conteudos/{self.item.id}').status_code,403)

    def test_grace_allows_only_previous_resources_and_does_not_extend_itself(self):
        sub=self.grant(source='billing');self.login();self.csrf()
        resource=self.make_resource(kind='course')
        self.assertEqual(self.client.get(f'/premium/conteudos/{self.item.id}').status_code,200)
        history=db.session.get(PremiumAccessHistory,(self.account.id,self.item.id))
        start=history.first_access_at
        # Freeze the clock after the last confirmed payment period rather than modifying access evidence.
        expiry=utcnow()+timedelta(seconds=1);sub.ends_at=expiry;db.session.commit()
        after=expiry+timedelta(days=1)
        with patch('premium_members.utcnow',return_value=after),patch('premium.utcnow',return_value=after):
            self.assertTrue(in_grace(sub))
            self.assertEqual(self.client.get(f'/premium/conteudos/{self.item.id}').status_code,200)
            self.assertEqual(self.client.post(f'/premium/cursos/{self.item.id}/inscricao',data={'csrf_token':'premium-csrf'}).status_code,403)
            other=PremiumContent(title='Outro curso',summary='Público',kind='course',published=True,body='NOVA MATÉRIA')
            db.session.add(other);db.session.commit()
            response=self.client.get(f'/premium/conteudos/{other.id}')
            self.assertEqual(response.status_code,403)
            self.assertNotIn('NOVA MATÉRIA',response.text)
        self.assertEqual(history.first_access_at,start)
        boundary=expiry+timedelta(days=3)
        with patch('premium_members.utcnow',return_value=boundary),patch('premium.utcnow',return_value=boundary):
            self.assertFalse(in_grace(sub))
            self.assertEqual(self.client.get(f'/premium/conteudos/{self.item.id}').status_code,403)

    def test_grace_does_not_override_suspension_or_plan_permissions(self):
        sub=self.grant(source='billing',starts_at=utcnow()-timedelta(days=4),ends_at=utcnow()-timedelta(days=1))
        db.session.add(PremiumAccessHistory(owner_id=self.account.id,content_id=self.item.id,first_access_at=utcnow()-timedelta(days=2)))
        resource=self.make_resource(kind='course');self.login()
        sub.status='suspended';db.session.commit()
        self.assertEqual(self.client.get(f'/premium/conteudos/{self.item.id}').status_code,403)
        sub.status='active';resource.plan_ids=[2147483647];db.session.commit()
        self.assertEqual(self.client.get(f'/premium/conteudos/{self.item.id}').status_code,403)

    def test_enrollment_is_idempotent_and_quota_uses_contracted_snapshot(self):
        sub=self.grant();sub.plan_snapshot={**sub.plan_snapshot,'course_limit':1};db.session.commit()
        self.login();self.csrf();self.make_resource(kind='course',metadata_fields={'completion_days':30})
        path=f'/premium/cursos/{self.item.id}/inscricao'
        for _ in range(2):self.assertEqual(self.client.post(path,data={'csrf_token':'premium-csrf'}).status_code,302)
        row=PremiumEnrollment.query.one();self.assertIsNotNone(row.deadline)
        other=PremiumContent(title='Curso adicional',summary='Resumo',body='Privado',kind='course',published=True)
        db.session.add(other);db.session.flush()
        lesson=PremiumLesson(content_id=other.id,title='Primeira aula',body='SEGREDO-AULA',published=True)
        db.session.add(lesson);db.session.commit()
        self.assertEqual(self.client.get(f'/premium/aulas/{lesson.id}').status_code,403)
        self.assertEqual(PremiumEnrollment.query.count(),1)

    def test_deadline_is_checked_on_server_and_extension_is_audited(self):
        self.grant();self.login();self.csrf();self.make_resource(kind='course')
        self.client.post(f'/premium/cursos/{self.item.id}/inscricao',data={'csrf_token':'premium-csrf'})
        enrollment=PremiumEnrollment.query.one();enrollment.deadline=utcnow()-timedelta(days=1);db.session.commit()
        self.assertEqual(self.client.get(f'/premium/conteudos/{self.item.id}').status_code,403)
        response=self.client.post('/premium/pedidos',data=dict(csrf_token='premium-csrf',kind='extension',content_id=str(self.item.id),reason='Preciso de mais tempo para terminar o curso.'))
        self.assertEqual(response.status_code,302)
        row=PremiumServiceRequest.query.one();self.admin()
        from premium_resources import local_input
        until=utcnow()+timedelta(days=15)
        self.client.post(f'/admin/premium/pedidos/{row.id}',data=dict(csrf_token='premium-csrf',version=str(row.version),state='approved',decision='Prazo aprovado após análise do pedido.',extension_until=local_input(until)))
        self.assertEqual(row.state,'approved');self.assertGreater(enrollment.deadline,utcnow())
        self.assertEqual(self.client.get(f'/premium/conteudos/{self.item.id}').status_code,200)

    def test_refund_request_never_fabricates_a_refund_or_accepts_foreign_order(self):
        order=self.paid_order();self.login();self.csrf()
        response=self.client.post('/premium/pedidos',data=dict(csrf_token='premium-csrf',kind='refund',order_id=order.id,reason='Pedido para análise pela equipa financeira.'))
        self.assertEqual(response.status_code,302,response.text)
        row=PremiumServiceRequest.query.one();self.assertEqual(order.refund_minor,0)
        self.admin()
        response=self.client.post(f'/admin/premium/pedidos/{row.id}',data=dict(csrf_token='premium-csrf',version=str(row.version),state='approved',amount='50.00',decision='Montante aprovado para devolução pelo fornecedor.'))
        self.assertEqual(response.status_code,302);self.assertEqual(row.amount_minor,5000);self.assertEqual(order.refund_minor,0)
        self.client.post(f'/admin/premium/pedidos/{row.id}',data=dict(csrf_token='premium-csrf',version=str(row.version),state='fulfilled',decision='Tentativa de concluir sem confirmação financeira.'))
        self.assertEqual(row.state,'approved')
        post_refund(order,5000,{'source':'test-provider-confirmation'});db.session.commit()
        self.client.post(f'/admin/premium/pedidos/{row.id}',data=dict(csrf_token='premium-csrf',version=str(row.version),state='fulfilled',decision='Devolução confirmada no registo financeiro.'))
        self.assertEqual(row.state,'fulfilled')
        from billing import payment_state
        self.assertEqual(payment_state(order),'partially_refunded')
        from billing import filtered_orders
        with app.test_request_context('/?state=partially_refunded'):
            query,_=filtered_orders()
            self.assertIn(order.id,[r.id for r in query.all()])
        with app.test_request_context('/?state=paid'):
            query,_=filtered_orders()
            self.assertNotIn(order.id,[r.id for r in query.all()])

    def test_another_reader_cannot_request_refund_of_a_foreign_payment(self):
        from submission_models import Researcher
        order=self.paid_order()
        other=Researcher(name='Outro participante',email=secrets.token_hex(8)+'@example.test',password_hash='unused',token_nonce='other-only',active=True,verified=True)
        db.session.add(other);db.session.commit();self.login(other);self.csrf()
        response=self.client.post('/premium/pedidos',data=dict(csrf_token='premium-csrf',kind='refund',order_id=order.id,reason='Tentativa de usar um pagamento de outra conta.'))
        self.assertEqual(response.status_code,404)
        self.assertEqual(PremiumServiceRequest.query.filter_by(owner_id=other.id).count(),0)
        self.assertNotIn(order.id,self.client.get('/premium/pedidos').text)

    def test_requests_enforce_csrf_permissions_and_optimistic_version(self):
        self.login();self.assertEqual(self.client.post('/premium/pedidos',data={}).status_code,400)
        self.csrf();self.client.post('/premium/pedidos',data=dict(csrf_token='premium-csrf',kind='assistance',reason='Necessito de apoio para utilizar a biblioteca.'))
        row=PremiumServiceRequest.query.one();self.admin(primary=False)
        self.assertEqual(self.client.get('/admin/premium/pedidos').status_code,403)
        with self.client.session_transaction() as session:session.pop('admin_id',None)
        self.admin()
        self.assertEqual(self.client.post(f'/admin/premium/pedidos/{row.id}',data=dict(csrf_token='premium-csrf',version='0',state='review',decision='Iniciar a análise administrativa.')).status_code,409)
        self.assertEqual(row.state,'pending')

    def test_certificate_verification_discloses_no_personal_name(self):
        row=PremiumCertificate(id=secrets.token_hex(16),owner_id=self.account.id,content_id=self.item.id,content_version=1,
            snapshot=dict(name='NOME PESSOAL CONFIDENCIAL',title='Curso de investigação',lessons=1))
        db.session.add(row);db.session.commit()
        response=self.client.get('/premium/certificados/verificar/'+row.id)
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('Certificado registado',response.text)
        self.assertNotIn('NOME PESSOAL CONFIDENCIAL',response.text)
        self.assertEqual(self.client.get('/premium/certificados/'+row.id+'.pdf').status_code,403)
        self.assertIn('noindex',response.headers['X-Robots-Tag'])

    def test_access_history_prevents_destructive_content_removal(self):
        self.grant();self.login();self.csrf();self.make_resource(kind='course')
        db.session.add(PremiumAccessHistory(owner_id=self.account.id,content_id=self.item.id,first_access_at=utcnow()))
        db.session.commit();self.admin()
        response=self.client.post(f'/admin/premium/conteudos/{self.item.id}/estado',data=dict(
            csrf_token='premium-csrf',version=str(self.item.version),action='delete',confirm='on'))
        self.assertEqual(response.status_code,409)
        self.assertIsNotNone(db.session.get(PremiumContent,self.item.id))

    def test_lifecycle_notices_are_deduplicated_without_extending_access(self):
        sub=self.grant(source='billing');before=sub.ends_at
        now=sub.ends_at+timedelta(hours=1)
        with patch('premium_members.utcnow',return_value=now):
            process_membership_notices();db.session.commit()
            count=StaffNotice.query.filter_by(researcher_id=self.account.id).count()
            process_membership_notices();db.session.commit()
            self.assertEqual(StaffNotice.query.filter_by(researcher_id=self.account.id).count(),count)
            self.assertTrue(any('tolerância' in n.subject for n in StaffNotice.query.filter_by(researcher_id=self.account.id)))
        self.assertEqual(sub.ends_at,before)


class CommercialMigrationTests(unittest.TestCase):
    def test_additive_upgrade_preserves_legacy_prices_and_backfills_access_once(self):
        from premium_commercial_schema import upgrade_commercial_schema
        engine=create_engine('sqlite://')
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE researcher (id INTEGER PRIMARY KEY)')
            connection.exec_driver_sql('CREATE TABLE premium_content (id INTEGER PRIMARY KEY)')
            connection.exec_driver_sql('CREATE TABLE premium_progress (owner_id INTEGER,content_id INTEGER,updated_at DATETIME)')
            connection.exec_driver_sql("CREATE TABLE premium_plan (id INTEGER PRIMARY KEY,name VARCHAR(100),interval VARCHAR(10),price_minor INTEGER,currency VARCHAR(3),description TEXT,benefits JSON,active BOOLEAN,version INTEGER)")
            connection.exec_driver_sql("INSERT INTO premium_plan VALUES (1,'Contrato anterior','monthly',12345,'MZN','Original','[\"Benefício anterior\"]',1,7)")
            connection.exec_driver_sql("INSERT INTO premium_progress VALUES (1,1,'2026-10-01 10:00:00')")
            upgrade_commercial_schema(connection);upgrade_commercial_schema(connection)
            self.assertEqual(connection.execute(text('SELECT name,price_minor,version,tier FROM premium_plan WHERE id=1')).one(),('Contrato anterior',12345,7,'legacy'))
            self.assertEqual(connection.scalar(text("SELECT count(*) FROM premium_plan WHERE tier IN ('pro','max') AND active=0 AND price_minor=0")),4)
            self.assertEqual(connection.scalar(text('SELECT count(*) FROM premium_access_history')),1)
            self.assertIn('premium_service_request',inspect(connection).get_table_names())
        engine.dispose()
