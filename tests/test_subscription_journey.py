"""Subscription extensions on isolated SQLite; provider calls are forbidden/mocked."""
import os
import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash
import test_premium_billing as fixtures
from app import app
from models import db
from premium_models import PremiumPlan, PremiumSubscription
from submission_models import Researcher
from billing_models import BillingOrder, BillingJournal
from billing_service import post_receipt, lock_account, reconcile_clicpay, audit_finance


class SubscriptionJourneyTests(unittest.TestCase):
    setUp=fixtures.BillingTests.setUp
    tearDown=fixtures.BillingTests.tearDown
    order=fixtures.BillingTests.order
    quote=fixtures.BillingTests.quote
    purchase_form=fixtures.BillingTests.purchase_form
    admin=fixtures.BillingTests.admin

    def test_monthly_and_annual_selection_survive_existing_login(self):
        self.owner.password_hash=generate_password_hash('Synthetic-password-123!')
        annual=PremiumPlan(name='Synthetic annual',interval='annual',price_minor=123456,currency='MZN',active=True)
        db.session.add(annual);db.session.commit()
        for plan in (self.plan,annual):
            with self.client.session_transaction() as session:session.clear()
            response=self.client.get('/premium/aderir/'+str(plan.id))
            self.assertIn('/submissoes/entrar',response.location)
            login=self.client.get(response.location)
            soup=BeautifulSoup(login.data,'html.parser')
            response=self.client.post('/submissoes/entrar',data=dict(email=self.owner.email,password='Synthetic-password-123!',
                csrf_token=soup.select_one('[name=csrf_token]')['value'],premium_return=soup.select_one('[name=premium_return]')['value']))
            self.assertEqual(response.location,'/premium/aderir/'+str(plan.id))
            self.assertIn(b'Confirmar subscri',self.client.get(response.location).data)

    def test_invalid_intent_cannot_redirect_to_external_url(self):
        with self.client.session_transaction() as session:
            session.clear();session['premium_return']='https://attacker.invalid'
        response=self.client.get('/submissoes/entrar?premium_return=https://attacker.invalid')
        self.assertEqual(response.status_code,200)
        self.assertNotIn(b'name="premium_return"',response.data)

    def test_disabled_checkout_cannot_create_order(self):
        with patch.dict(os.environ,{'PREMIUM_PAYMENTS_ENABLED':'false'}):
            response=self.client.get('/premium/aderir/'+str(self.plan.id))
            self.assertNotIn(b'Continuar para pagamento',response.data)
            self.assertEqual(BillingOrder.query.filter_by(owner_id=self.owner.id).count(),0)

    def test_receipt_requires_ownership_and_confirmed_ledger(self):
        order=self.order(live=False)
        path='/premium/pagamentos/'+order.id+'/comprovativo.pdf'
        self.assertEqual(self.client.get(path).status_code,404)
        post_receipt(order,lock_account(self.owner.id,live=False));db.session.commit()
        response=self.client.get(path)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.mimetype,'application/pdf')
        self.assertTrue(response.data.startswith(b'%PDF'))
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertIsNone(PremiumSubscription.query.filter_by(owner_id=self.owner.id).first())
        other=Researcher(name='Other receipt reader',email=order.id+'@other.example.test',password_hash='unused',token_nonce='other-nonce',active=True,verified=True)
        db.session.add(other);db.session.commit()
        with self.client.session_transaction() as session:
            session['researcher_id']=other.id;session['researcher_nonce']=other.token_nonce
        self.assertEqual(self.client.get(path).status_code,404)
        self.assertFalse(audit_finance()['errors'])

    def test_cancelled_evidence_distinct_from_refusal_and_filterable(self):
        order=self.order()
        with patch('billing_service.clicpay_status',return_value={'clicpay_reference':order.provider_ref,'status':'CANCELLED'}):
            reconcile_clicpay(order);db.session.commit()
        response=self.client.get('/premium/pagamentos/'+order.id)
        self.assertIn(b'Cancelado',response.data)
        self.admin()
        response=self.client.get('/admin/premium/financeiro?state=cancelled&q='+order.id)
        self.assertEqual(response.status_code,200)
        self.assertIn(order.id.encode(),response.data)
        response=self.client.get('/admin/premium/financeiro?state=failed&q='+order.id)
        soup=BeautifulSoup(response.data,'html.parser')
        self.assertEqual(len(soup.select('.premium-finance-order')),0)
        self.assertEqual(order.state,'failed')

    def test_finance_filters_export_only_matching_immutable_entries(self):
        first=self.order(live=False);second=self.order(live=True)
        post_receipt(first,lock_account(self.owner.id,live=False));post_receipt(second,lock_account(self.owner.id,live=True));db.session.commit()
        self.admin()
        response=self.client.get('/admin/premium/financeiro/exportar.csv?mode=test&q='+first.id)
        self.assertEqual(response.status_code,200)
        self.assertIn(first.id.encode(),response.data);self.assertNotIn(second.id.encode(),response.data)
        self.assertEqual(self.client.get('/admin/premium/financeiro?from=bad').status_code,400)
        self.assertEqual(self.client.get('/admin/premium/financeiro?state=unknown').status_code,400)
        self.assertEqual(self.client.get('/admin/premium/financeiro?from=2026-12-01&to=2026-01-01').status_code,400)
        self.assertFalse(audit_finance()['errors'])

    def test_active_plan_change_is_blocked_before_provider(self):
        order=self.order();post_receipt(order,lock_account(self.owner.id));db.session.commit()
        annual=PremiumPlan(name='Synthetic annual switch',interval='annual',price_minor=123456,currency='MZN',active=True)
        db.session.add(annual);db.session.commit();self.plan=annual
        form=self.purchase_form()
        with patch('billing.create_clicpay') as provider:
            response=self.client.post('/premium/aderir/'+str(annual.id),data=form)
        self.assertEqual(response.status_code,400);provider.assert_not_called()
