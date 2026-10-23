"""Provider contracts are mocked; real database/HTTP, no live financial side effects."""
import hashlib
import hmac
import json
import os
import secrets
import time
import unittest
from datetime import timedelta
from unittest.mock import Mock, patch
from bs4 import BeautifulSoup
import test_platform
from app import app
from models import db, utcnow, Article, Journal
from submission_models import Researcher
from premium_models import PremiumPlan, PremiumSubscription
from billing_models import BillingAccount, BillingOrder, BillingGrant, BillingJournal, BillingEvent
from billing_providers import ProviderError, available_methods, create_clicpay, create_stripe, stripe_api
from billing_service import (lock_account,next_period,reconcile_clicpay,reconcile_invoice,post_refund,audit_finance,sync_cancellation)
from security_test_support import authenticate_test_session
from extensions import limiter


class BillingTests(unittest.TestCase):
    def setUp(self):
        self.ctx=app.app_context();self.ctx.push()
        self.env=patch.dict(os.environ,{'PREMIUM_PAYMENTS_ENABLED':'true','PREMIUM_PAYMENTS_MODE':'live',
            'PREMIUM_LIVE_APPROVED':'true','CLICPAY_TOKEN':'fixture-token','CLICPAY_MPESA_WALLET':'123',
            'CLICPAY_EMOLA_WALLET':'456','STRIPE_MERCHANT_APPROVED':'true','STRIPE_SECRET_KEY':'sk_live_fixture',
            'STRIPE_WEBHOOK_SECRET':'whsec_fixture','STRIPE_PORTAL_CONFIGURATION':'bpc_fixture'});self.env.start()
        self.network=patch('billing_providers.requests.request',side_effect=AssertionError('Live network forbidden in tests'));self.network.start()
        self.previous_limiter=limiter.enabled;limiter.enabled=False
        token=secrets.token_hex(6)
        self.owner=Researcher(name='Leitor financeiro',email=token+'@example.test',password_hash='unused',token_nonce=token,active=True,verified=True)
        self.plan=PremiumPlan(name='Mensal financeiro '+token,interval='monthly',price_minor=50000,currency='MZN',active=True)
        db.session.add_all([self.owner,self.plan]);db.session.commit()
        self.client=app.test_client()
        with self.client.session_transaction() as session:
            session['researcher_id']=self.owner.id;session['researcher_nonce']=token;session['csrf_token']='billing-csrf'
        self.csrf='billing-csrf'

    def tearDown(self):
        db.session.rollback();limiter.enabled=self.previous_limiter;self.network.stop();self.env.stop();self.ctx.pop()

    def order(self,**changes):
        values=dict(owner_id=self.owner.id,plan_id=self.plan.id,snapshot={k:getattr(self.plan,k) for k in
            ('name','interval','price_minor','currency','version')},amount_minor=self.plan.price_minor,currency='MZN',
            method='mpesa',provider='clicpay',live=True,state='pending',provider_ref='CPAY'+secrets.token_hex(10),expires_at=utcnow()+timedelta(days=1))
        values.update(changes);record=BillingOrder(**values);db.session.add(record);db.session.commit();return record

    def quote(self):
        response=self.client.get('/premium/aderir/'+str(self.plan.id))
        self.assertEqual(response.status_code,200)
        return BeautifulSoup(response.data,'html.parser').select_one('input[name=quote]')['value']

    def purchase_form(self,**changes):
        form=dict(quote=self.quote(),csrf_token=self.csrf,method='mpesa',phone='841234567',consent='on')
        form.update(changes);return form

    def admin(self,primary=True):
        with self.client.session_transaction() as session:
            session.pop('admin_id',None);session['admin_authenticated']=True;session['admin_superuser']=primary;session['admin_last_activity_at']=time.time()
            authenticate_test_session(session)

    def test_disabled_by_default_or_missing_live_ack_does_not_offer_checkout(self):
        with patch.dict(os.environ,{'PREMIUM_PAYMENTS_ENABLED':'false'}):self.assertEqual(available_methods(),{})
        with patch.dict(os.environ,{'PREMIUM_LIVE_APPROVED':'false'}):self.assertEqual(available_methods(),{})
        with patch.dict(os.environ,{'STRIPE_MERCHANT_APPROVED':'false'}):self.assertNotIn('stripe',available_methods())
        self.assertNotIn('mpesa',available_methods('USD'))
        self.assertIn('mpesa',available_methods('MZN'));self.assertIn('emola',available_methods('MZN'))

    def test_quote_requires_verified_authenticated_owner(self):
        self.owner.verified=False;db.session.commit()
        self.assertEqual(self.client.get('/premium/aderir/'+str(self.plan.id)).status_code,403)
        with self.client.session_transaction() as session:session.clear()
        self.assertEqual(self.client.get('/premium/pagamentos').status_code,302)

    def test_checkout_requires_csrf_consent_and_unchanged_price(self):
        path='/premium/aderir/'+str(self.plan.id)
        form=self.purchase_form();form.pop('csrf_token')
        self.assertEqual(self.client.post(path,data=form).status_code,400)
        form=self.purchase_form(consent='')
        self.assertEqual(self.client.post(path,data=form).status_code,400)
        form=self.purchase_form();self.plan.price_minor+=100;db.session.commit()
        self.assertEqual(self.client.post(path,data=form).status_code,400)
        self.assertEqual(BillingOrder.query.filter_by(owner_id=self.owner.id).count(),0)

    def test_local_initiation_snapshots_and_duplicate_submission_do_not_charge_twice(self):
        self.plan.benefits=['Condição contratada'];db.session.commit()
        form=self.purchase_form();path='/premium/aderir/'+str(self.plan.id)
        with patch('billing.create_clicpay',return_value={'clicpay_reference':'CPAY'+secrets.token_hex(10),'status':'pending'}) as api:
            first=self.client.post(path,data=form);second=self.client.post(path,data=form)
            self.assertEqual(first.status_code,302);self.assertEqual(first.location,second.location);self.assertEqual(api.call_count,1)
        order=BillingOrder.query.filter_by(owner_id=self.owner.id).one()
        self.assertEqual(order.amount_minor,50000);self.assertEqual(order.state,'pending')
        self.assertNotIn('phone',order.snapshot)
        self.assertEqual(order.snapshot['benefits'],['Condição contratada'])
        self.plan.benefits=['Novas condições'];db.session.commit()
        self.assertEqual(order.snapshot['benefits'],['Condição contratada'])
        self.assertIsNone(PremiumSubscription.query.filter_by(owner_id=self.owner.id).first())

    def test_uncertain_initiation_reserves_slot_without_automatic_retry(self):
        form=self.purchase_form();path='/premium/aderir/'+str(self.plan.id)
        with patch('billing.create_clicpay',side_effect=ProviderError('timeout')) as api:
            self.assertEqual(self.client.post(path,data=form).status_code,302)
            next_form=self.purchase_form()
            self.assertEqual(self.client.post(path,data=next_form).status_code,302)
            self.assertEqual(api.call_count,1)
        order=BillingOrder.query.filter_by(owner_id=self.owner.id).one()
        self.assertEqual(order.state,'review');self.assertEqual(db.session.get(BillingAccount,(self.owner.id,True)).open_order_id,order.id)

    def test_card_requires_specific_recurring_consent(self):
        form=self.purchase_form(method='stripe')
        self.assertEqual(self.client.post('/premium/aderir/'+str(self.plan.id),data=form).status_code,400)
        self.assertEqual(BillingOrder.query.filter_by(owner_id=self.owner.id).count(),0)

    def test_clicpay_adapter_uses_integer_derived_amount_fixed_host_and_idempotency(self):
        order=self.order(method='emola')
        response=Mock(status_code=200);response.json.return_value={'clicpay_reference':order.provider_ref}
        wallet=Mock(status_code=200);wallet.json.return_value={'data':{'id':456,'environment':'production','is_active':True,'allow_c2b':True,'currency':'MZN','payment_method':{'slug':'emola'}}}
        with patch('billing_providers.requests.request',side_effect=[wallet,response]) as api:
            create_clicpay(order,'+258 84 123 4567')
            args,kwargs=api.call_args
            self.assertEqual(args[1],'https://clicpay.co.mz/api/v2/wallets/456/c2b/emola')
            self.assertEqual(kwargs['headers']['Idempotency-Key'],order.id)
            self.assertEqual(kwargs['json']['amount'],'500.00');self.assertEqual(kwargs['json']['msisdn'],'841234567')
            self.assertFalse(kwargs['allow_redirects'])

    def test_confirmed_mobile_receipt_grants_one_calendar_period_once(self):
        order=self.order()
        with patch('billing_service.clicpay_status',return_value={'clicpay_reference':order.provider_ref,'status':'SUCCESSFUL'}):
            reconcile_clicpay(order);db.session.commit();reconcile_clicpay(order);db.session.commit()
        self.assertEqual(BillingJournal.query.filter_by(order_id=order.id).count(),1)
        self.assertEqual(BillingGrant.query.filter_by(order_id=order.id).count(),1)
        sub=PremiumSubscription.query.filter_by(owner_id=self.owner.id).one()
        self.assertEqual(sub.source,'billing');self.assertEqual(sub.ends_at,next_period(sub.starts_at,'monthly'))
        self.assertEqual(audit_finance()['errors'],[])

    def test_pending_refused_and_unknown_status_never_grant_access(self):
        for state in ['PENDING','PROCESSING','REJECTED','FAILED','CANCELLED','AWAITING_ACTION']:
            order=self.order()
            with patch('billing_service.clicpay_status',return_value={'clicpay_reference':order.provider_ref,'status':state}):
                reconcile_clicpay(order);db.session.commit()
            self.assertEqual(BillingJournal.query.filter_by(order_id=order.id).count(),0)
            self.assertIsNone(db.session.get(BillingGrant,order.id))
        self.assertIsNone(PremiumSubscription.query.filter_by(owner_id=self.owner.id).first())

    def test_pending_deadline_is_review_not_false_failure_or_released_slot(self):
        order=self.order(expires_at=utcnow()-timedelta(days=1))
        account=lock_account(self.owner.id);account.open_order_id=order.id;db.session.commit()
        with patch('billing_service.clicpay_status',return_value={'clicpay_reference':order.provider_ref,'status':'PROCESSING'}):
            reconcile_clicpay(order);db.session.commit()
        self.assertEqual(order.state,'review');self.assertEqual(account.open_order_id,order.id)

    def test_mobile_reference_amount_currency_and_environment_mismatch_rejected(self):
        order=self.order()
        for fields in [dict(clicpay_reference='wrong',status='SUCCESSFUL'),dict(clicpay_reference=order.provider_ref,status='SUCCESSFUL',amount=1),
                       dict(clicpay_reference=order.provider_ref,status='SUCCESSFUL',currency='USD')]:
            with patch('billing_service.clicpay_status',return_value=fields):
                with self.assertRaises(ProviderError):reconcile_clicpay(order)
                db.session.rollback()
        with patch.dict(os.environ,{'PREMIUM_PAYMENTS_MODE':'test'}):
            with self.assertRaises(ProviderError):reconcile_clicpay(order)
        self.assertEqual(BillingJournal.query.filter_by(order_id=order.id).count(),0)

    def test_test_mode_never_activates_real_entitlement(self):
        order=self.order(live=False)
        with patch.dict(os.environ,{'PREMIUM_PAYMENTS_MODE':'test'}),patch('billing_service.clicpay_status',return_value={'clicpay_reference':order.provider_ref,'status':'SUCCESSFUL'}):
            reconcile_clicpay(order);db.session.commit()
        self.assertEqual(order.state,'paid');self.assertIsNone(db.session.get(BillingGrant,order.id))
        self.assertIsNone(PremiumSubscription.query.filter_by(owner_id=self.owner.id).first())

    def test_annual_calendar_including_leap_day(self):
        from datetime import datetime
        self.assertEqual(next_period(datetime(2024,2,29),'annual'),datetime(2025,2,28))
        self.assertEqual(next_period(datetime(2026,1,31),'monthly'),datetime(2026,2,28))

    def test_renewal_extends_paid_time_instead_of_restarting_today(self):
        first=self.order();second=self.order()
        for order in [first,second]:
            with patch('billing_service.clicpay_status',return_value={'clicpay_reference':order.provider_ref,'status':'SUCCESSFUL'}):
                reconcile_clicpay(order);db.session.commit()
        a=db.session.get(BillingGrant,first.id);b=db.session.get(BillingGrant,second.id)
        self.assertEqual(a.ends_at,b.starts_at)
        self.assertEqual(PremiumSubscription.query.filter_by(owner_id=self.owner.id).one().ends_at,b.ends_at)

    def test_journal_and_events_are_database_immutable(self):
        from sqlalchemy import text
        order=self.order()
        with patch('billing_service.clicpay_status',return_value={'clicpay_reference':order.provider_ref,'status':'SUCCESSFUL'}):
            reconcile_clicpay(order);db.session.commit()
        for sql in ['UPDATE billing_journal SET amount_minor=1 WHERE order_id=:id','DELETE FROM billing_journal WHERE order_id=:id',
                    'UPDATE billing_event SET digest=\'changed\'']:
            with self.assertRaises(Exception):db.session.execute(text(sql),{'id':order.id});db.session.commit()
            db.session.rollback()
        self.assertEqual(BillingJournal.query.filter_by(order_id=order.id).one().amount_minor,50000)

    def test_original_quote_amount_is_immutable(self):
        order=self.order();order.amount_minor=1
        with self.assertRaises(ValueError):db.session.flush()
        db.session.rollback()

    def test_partial_full_and_duplicate_refunds_preserve_ledger(self):
        order=self.order()
        with patch('billing_service.clicpay_status',return_value={'clicpay_reference':order.provider_ref,'status':'SUCCESSFUL'}):
            reconcile_clicpay(order);db.session.commit()
        post_refund(order,10000,{'ref':'verified'});db.session.commit()
        self.assertFalse(db.session.get(BillingGrant,order.id).revoked)
        post_refund(order,50000,{'ref':'verified'});db.session.commit()
        post_refund(order,50000,{'ref':'verified'});db.session.commit()
        self.assertTrue(db.session.get(BillingGrant,order.id).revoked)
        self.assertEqual(order.state,'refunded')
        self.assertEqual(BillingJournal.query.filter_by(order_id=order.id,kind='refund').count(),2)
        self.assertEqual(audit_finance()['errors'],[])

    def test_refund_cannot_exceed_payment(self):
        order=self.order()
        with self.assertRaises(ProviderError):post_refund(order,50001,{})
        db.session.rollback()

    def stripe_fixture(self,root=None,invoice_id=None,days_offset=0,status='paid'):
        root=root or self.order(method='stripe',provider='stripe',provider_ref='cs_'+secrets.token_hex(6),record_kind='checkout',recurring=True)
        account=lock_account(self.owner.id);account.stripe_root=root.id;db.session.commit()
        invoice_id=invoice_id or 'in_'+secrets.token_hex(6);subid='sub_'+root.id
        start=utcnow()+timedelta(days=days_offset);end=next_period(start,root.snapshot['interval'])
        piid='pi_'+invoice_id
        sub={'id':subid,'livemode':True,'customer':'cus_fixture','metadata':{'billing_order':root.id},'status':'active','latest_invoice':invoice_id,
             'items':{'data':[{'quantity':1,'price':{'unit_amount':50000,'currency':'mzn','recurring':{'interval':'month' if root.snapshot['interval']=='monthly' else 'year','interval_count':1}}}]}}
        invoice={'id':invoice_id,'livemode':True,'parent':{'subscription_details':{'subscription':subid}},'customer':'cus_fixture','status':status,
            'amount_paid':50000 if status=='paid' else 0,'amount_due':50000,'total':50000,'currency':'mzn','collection_method':'charge_automatically',
            'lines':{'data':[{'period':{'start':int(start.replace(tzinfo=__import__('datetime').timezone.utc).timestamp()),
                                      'end':int(end.replace(tzinfo=__import__('datetime').timezone.utc).timestamp())}}],'has_more':False}}
        rows={'data':[{'invoice':invoice_id,'status':'paid','livemode':True,'currency':'mzn','amount_paid':50000,
                         'payment':{'type':'payment_intent','payment_intent':piid}}],'has_more':False}
        intent={'id':piid,'status':'succeeded','livemode':True,'currency':'mzn','amount_received':50000,'customer':'cus_fixture'}
        def api(method,path,data=None,key=None):
            if path=='/invoices/'+invoice_id:return invoice
            if path=='/subscriptions/'+subid:return sub
            if path=='/invoice_payments':return rows
            if path=='/payment_intents/'+piid:return intent
            raise AssertionError(path)
        return root,invoice,sub,rows,intent,api

    def test_stripe_confirmed_invoice_and_duplicate_events_post_once(self):
        root,invoice,sub,rows,intent,api=self.stripe_fixture()
        with patch('billing_service.stripe_api',side_effect=api):
            first=reconcile_invoice(invoice['id']);db.session.commit()
            second=reconcile_invoice(invoice['id']);db.session.commit()
        self.assertEqual(first.id,second.id)
        self.assertEqual(BillingJournal.query.filter_by(order_id=first.id,kind='receipt').count(),1)
        self.assertEqual(audit_finance()['errors'],[])

    def test_stripe_renewal_has_separate_financial_period(self):
        root,invoice,sub,rows,intent,api=self.stripe_fixture()
        with patch('billing_service.stripe_api',side_effect=api):first=reconcile_invoice(invoice['id']);db.session.commit()
        _,next_invoice,_,_,_,api2=self.stripe_fixture(root=root,days_offset=31)
        with patch('billing_service.stripe_api',side_effect=api2):second=reconcile_invoice(next_invoice['id']);db.session.commit()
        self.assertNotEqual(first.id,second.id)
        self.assertEqual(BillingOrder.query.filter_by(owner_id=self.owner.id,record_kind='payment',state='paid').count(),2)

    def test_unpaid_stripe_invoice_never_activates(self):
        root,invoice,sub,rows,intent,api=self.stripe_fixture(status='open')
        with patch('billing_service.stripe_api',side_effect=api):
            child=reconcile_invoice(invoice['id']);db.session.commit()
        self.assertEqual(child.state,'pending');self.assertIsNone(db.session.get(BillingGrant,child.id))

    def test_stripe_currency_amount_or_capture_mismatch_never_posts(self):
        for mutation in ['amount','currency','capture','manual']:
            root,invoice,sub,rows,intent,api=self.stripe_fixture()
            if mutation=='amount':invoice['amount_paid']=1
            if mutation=='currency':invoice['currency']='usd'
            if mutation=='capture':intent['status']='requires_capture'
            if mutation=='manual':invoice['paid_out_of_band']=True
            with patch('billing_service.stripe_api',side_effect=api):
                with self.assertRaises(ProviderError):reconcile_invoice(invoice['id'])
            db.session.rollback()
        self.assertEqual(BillingJournal.query.join(BillingOrder).filter(BillingOrder.owner_id==self.owner.id).count(),0)

    def signed_webhook(self,event,stamp=None):
        raw=json.dumps(event).encode();stamp=int(time.time()) if stamp is None else stamp
        sig=hmac.new(b'whsec_fixture',str(stamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
        return raw,{'Stripe-Signature':f't={stamp},v1={sig}','Content-Type':'application/json'}

    def test_invalid_signature_and_replay_timestamp_rejected(self):
        event={'id':'evt_'+secrets.token_hex(6),'type':'invoice.paid','livemode':True,'data':{'object':{'id':'in_fixture'}}}
        raw,headers=self.signed_webhook(event,stamp=int(time.time())-1000)
        self.assertEqual(self.client.post('/premium/webhooks/stripe',data=raw,headers=headers).status_code,400)
        raw,headers=self.signed_webhook(event);headers['Stripe-Signature']='t=1,v1=forged'
        self.assertEqual(self.client.post('/premium/webhooks/stripe',data=raw,headers=headers).status_code,400)

    def test_signed_webhook_is_idempotent_and_does_not_store_raw_payload(self):
        root,invoice,sub,rows,intent,api=self.stripe_fixture()
        event={'id':'evt_'+secrets.token_hex(6),'type':'invoice.paid','livemode':True,'data':{'object':{'id':invoice['id'],'card_number':'sensitive-do-not-store'}}}
        raw,headers=self.signed_webhook(event)
        with patch('billing_service.stripe_api',side_effect=api):
            self.assertEqual(self.client.post('/premium/webhooks/stripe',data=raw,headers=headers).status_code,200)
            self.assertEqual(self.client.post('/premium/webhooks/stripe',data=raw,headers=headers).status_code,200)
        row=BillingEvent.query.filter_by(event_key='stripe:'+event['id']).one()
        self.assertEqual(len(row.digest),64);self.assertNotIn('sensitive',str(row.__dict__))

    def test_webhook_provider_timeout_rolls_back_for_retry(self):
        event={'id':'evt_'+secrets.token_hex(6),'type':'invoice.paid','livemode':True,'data':{'object':{'id':'in_fixture'}}}
        raw,headers=self.signed_webhook(event)
        with patch('billing_service.stripe_api',side_effect=ProviderError('timeout')):
            self.assertEqual(self.client.post('/premium/webhooks/stripe',data=raw,headers=headers).status_code,503)
        self.assertIsNone(BillingEvent.query.filter_by(event_key='stripe:'+event['id']).first())

    def test_return_url_never_confirms_payment_and_other_account_cannot_see_order(self):
        order=self.order()
        response=self.client.get('/premium/pagamentos/'+order.id+'?paid=true')
        self.assertEqual(response.status_code,200);self.assertEqual(order.state,'pending')
        with self.client.session_transaction() as session:session['researcher_id']=999999
        self.assertEqual(self.client.get('/premium/pagamentos/'+order.id).status_code,302)

    def test_payment_refresh_requires_csrf(self):
        order=self.order()
        self.assertEqual(self.client.post('/premium/pagamentos/'+order.id+'/verificar').status_code,400)

    def test_cancellation_is_simple_durable_and_preserves_paid_access(self):
        root,invoice,sub,rows,intent,api=self.stripe_fixture()
        with patch('billing_service.stripe_api',side_effect=api):reconcile_invoice(invoice['id']);db.session.commit()
        before=PremiumSubscription.query.filter_by(owner_id=self.owner.id).one().ends_at
        with patch('billing_service.stripe_api',return_value={'cancel_at_period_end':True,'status':'active'}) as provider:
            response=self.client.post('/premium/pagamentos/cancelar-renovacao',data={'csrf_token':self.csrf})
            self.assertEqual(response.status_code,302)
            self.assertEqual(provider.call_args.args[:2],('POST','/subscriptions/'+sub['id']))
        account=db.session.get(BillingAccount,(self.owner.id,True))
        self.assertTrue(account.cancel_requested);self.assertTrue(account.cancel_confirmed)
        self.assertEqual(PremiumSubscription.query.filter_by(owner_id=self.owner.id).one().ends_at,before)

    def test_cancellation_failure_is_not_falsely_reported_as_confirmed(self):
        root,invoice,sub,rows,intent,api=self.stripe_fixture()
        account=db.session.get(BillingAccount,(self.owner.id,True));account.stripe_subscription=sub['id'];db.session.commit()
        with patch('billing_service.stripe_api',side_effect=ProviderError('timeout')):
            self.client.post('/premium/pagamentos/cancelar-renovacao',data={'csrf_token':self.csrf})
        db.session.refresh(account);self.assertTrue(account.cancel_requested);self.assertFalse(account.cancel_confirmed)

    def test_financial_pages_export_require_primary_admin(self):
        self.admin(False)
        for path in ['/admin/premium/financeiro','/admin/premium/financeiro/exportar.csv']:
            self.assertEqual(self.client.get(path).status_code,403)
        self.admin(True)
        self.assertEqual(self.client.get('/admin/premium/financeiro').status_code,200)
        response=self.client.get('/admin/premium/financeiro/exportar.csv')
        self.assertEqual(response.status_code,200);self.assertIn('no-store',response.headers['Cache-Control'])

    def test_open_access_articles_never_require_payment(self):
        article=Article.public_query().first();journal=Journal.query.filter_by(published=True).first()
        anonymous=app.test_client()
        for path in ['/artigo/'+article.slug,'/revistas/'+journal.slug]:self.assertEqual(anonymous.get(path).status_code,200)

    def test_financial_audit_cli_passes_for_consistent_journal(self):
        result=app.test_cli_runner().invoke(args=['premium-auditar-financas'])
        self.assertEqual(result.exit_code,0,result.output)


    def test_production_wallet_is_never_charged_in_test_mode(self):
        order=self.order(live=False)
        response=Mock(status_code=200)
        response.json.return_value={'data':{'id':123,'environment':'production','is_active':True,'allow_c2b':True,'currency':'MZN','payment_method':{'slug':'mpesa'}}}
        with patch('billing_providers.requests.request',return_value=response) as api:
            with self.assertRaises(ProviderError):create_clicpay(order,'841234567')
            self.assertEqual(api.call_count,1);self.assertEqual(api.call_args.args[0],'GET')

    def test_authoritative_stripe_expiry_releases_unpaid_checkout(self):
        from billing_service import reconcile_stripe_checkout
        root=self.order(method='stripe',provider='stripe',provider_ref='cs_'+secrets.token_hex(5),record_kind='checkout',recurring=True)
        account=lock_account(self.owner.id);account.open_order_id=root.id;account.stripe_root=root.id;db.session.commit()
        result={'id':root.provider_ref,'livemode':True,'client_reference_id':root.id,'status':'expired','subscription':None,'invoice':None}
        with patch('billing_service.stripe_api',return_value=result):reconcile_stripe_checkout(root);db.session.commit()
        self.assertEqual(root.state,'expired');self.assertIsNone(account.open_order_id)
        self.assertTrue(account.agreement_closed)
        self.assertEqual(BillingJournal.query.filter_by(order_id=root.id).count(),0)

    def test_invoice_annual_period(self):
        self.plan.interval='annual';db.session.commit()
        root,invoice,sub,rows,intent,api=self.stripe_fixture()
        with patch('billing_service.stripe_api',side_effect=api):
            order=reconcile_invoice(invoice['id']);db.session.commit()
        grant=db.session.get(BillingGrant,order.id)
        self.assertIn((grant.ends_at-grant.starts_at).days,[365,366])

    def test_refund_before_invoice_event_is_recovered_from_current_charge(self):
        root,invoice,sub,rows,intent,base_api=self.stripe_fixture()
        intent['latest_charge']='ch_'+secrets.token_hex(5)
        charge={'id':intent['latest_charge'],'livemode':True,'payment_intent':intent['id'],'amount':50000,'amount_refunded':50000}
        def api(method,path,data=None,key=None):
            return charge if path=='/charges/'+charge['id'] else base_api(method,path,data,key)
        with patch('billing_service.stripe_api',side_effect=api):order=reconcile_invoice(invoice['id']);db.session.commit()
        self.assertEqual(order.state,'refunded');self.assertTrue(db.session.get(BillingGrant,order.id).revoked)
        self.assertEqual(audit_finance()['errors'],[])

    def test_dispute_hold_and_verified_win_are_reflected_in_access(self):
        from billing_service import record_dispute
        from premium import subscription_for
        root,invoice,sub,rows,intent,api=self.stripe_fixture()
        with patch('billing_service.stripe_api',side_effect=api):order=reconcile_invoice(invoice['id']);db.session.commit()
        dispute={'id':'dp_'+secrets.token_hex(5),'livemode':True,'payment_intent':intent['id'],'status':'needs_response'}
        record_dispute(order,dispute);db.session.commit()
        self.assertIsNone(subscription_for(self.owner))
        dispute['status']='won';record_dispute(order,dispute);db.session.commit()
        self.assertIsNotNone(subscription_for(self.owner))

    def test_active_different_reader_gets_404_for_private_payment(self):
        order=self.order()
        other=Researcher(name='Outra pessoa',email=secrets.token_hex(8)+'@example.test',password_hash='unused',token_nonce='other',active=True,verified=True)
        db.session.add(other);db.session.commit()
        with self.client.session_transaction() as session:session['researcher_id']=other.id;session['researcher_nonce']='other'
        self.assertEqual(self.client.get('/premium/pagamentos/'+order.id).status_code,404)

    def test_financial_integrity_checker_detects_quote_corruption(self):
        from sqlalchemy import text
        order=self.order()
        with patch('billing_service.clicpay_status',return_value={'clicpay_reference':order.provider_ref,'status':'SUCCESSFUL'}):reconcile_clicpay(order);db.session.commit()
        db.session.execute(text('UPDATE billing_order SET amount_minor=amount_minor+1 WHERE id=:id'),{'id':order.id})
        db.session.expire_all()
        self.assertIn(order.id+':receipt',audit_finance()['errors'])
        db.session.rollback()

    def test_competing_account_updates_are_rejected(self):
        from sqlalchemy.orm import Session
        from sqlalchemy.orm.exc import StaleDataError
        account=lock_account(self.owner.id);db.session.commit()
        with Session(db.engine) as second:
            stale=second.get(BillingAccount,(self.owner.id,True))
            account.suspended=True;db.session.commit()
            stale.suspended=True
            with self.assertRaises(StaleDataError):second.commit()

    def test_paid_subscription_cannot_be_rewritten_as_manual_offer(self):
        order=self.order()
        with patch('billing_service.clicpay_status',return_value={'clicpay_reference':order.provider_ref,'status':'SUCCESSFUL'}):reconcile_clicpay(order);db.session.commit()
        sub=PremiumSubscription.query.filter_by(owner_id=self.owner.id).one();end=sub.ends_at
        self.admin(True)
        response=self.client.post('/admin/premium/assinaturas/'+str(sub.id),data={'csrf_token':self.csrf,'status':'active'})
        self.assertEqual(response.status_code,302);self.assertIn('/financeiro',response.location)
        self.assertEqual(sub.ends_at,end)


    def test_netshop_hosted_checkout_never_sends_card_fields(self):
        from billing_providers import netshop_checkout_url
        order=self.order(method='netshop')
        wallet=Mock(status_code=200);wallet.json.return_value={'data':{'id':789,'environment':'production','is_active':True,'allow_c2b':True,'currency':'MZN','payment_method':{'slug':'netshop'}}}
        response=Mock(status_code=201);response.json.return_value={'clicpay_reference':order.provider_ref,'checkout_url':'https://secure.netshop.test/checkout/test'}
        with patch.dict(os.environ,{'CLICPAY_NETSHOP_WALLET':'789','CLICPAY_CHECKOUT_HOSTS':'secure.netshop.test'}),patch('billing_providers.requests.request',side_effect=[wallet,response]) as api:
            result=create_clicpay(order,'',origin='https://www.sussurrosdosaber.com')
            payload=api.call_args.kwargs['json']
            self.assertNotIn('card_number',payload);self.assertNotIn('cvv',payload);self.assertNotIn('pan',payload)
            self.assertTrue(api.call_args.args[1].endswith('/card-payment'))
            self.assertEqual(netshop_checkout_url(result['checkout_url']),result['checkout_url'])
            with self.assertRaises(ProviderError):netshop_checkout_url('https://evil.example/card')

    def test_obligatory_open_access_content_remains_free(self):
        from premium_models import PremiumContent
        content=PremiumContent(title='Curso financiado para acesso aberto',kind='course',summary='Resumo aberto',body='TEXTO-ABERTO-SEM-PAGAMENTO',published=True,open_access_required=True)
        db.session.add(content);db.session.commit()
        response=app.test_client().get('/premium/conteudos/'+str(content.id))
        self.assertEqual(response.status_code,200);self.assertIn(b'TEXTO-ABERTO-SEM-PAGAMENTO',response.data)

    def test_local_partial_refund_requires_document_and_provider_confirmation(self):
        order=self.order()
        with patch('billing_service.clicpay_status',return_value={'clicpay_reference':order.provider_ref,'status':'SUCCESSFUL'}):reconcile_clicpay(order);db.session.commit()
        result={'clicpay_reference':order.provider_ref,'status':'PARTIALLY_REFUNDED'}
        with patch('billing_providers.clicpay_status',return_value=result):
            output=app.test_cli_runner().invoke(args=['premium-confirmar-reembolso-local','--pedido',order.id,'--total-minor','10000','--documento','Relatorio-Fornecedor-123','--motivo','Conferido pelo responsável financeiro'])
        self.assertEqual(output.exit_code,0,output.output)
        db.session.refresh(order);self.assertEqual(order.refund_minor,10000)
        self.assertEqual(audit_finance()['errors'],[])

    def test_stripe_pending_checkout_safe_host_and_idempotency(self):
        root=self.order(method='stripe',provider='stripe',record_kind='checkout',provider_ref=None,recurring=True)
        payload={'id':'cs_fixture','url':'https://checkout.stripe.com/c/pay/test','livemode':True,'client_reference_id':root.id}
        with patch('billing_providers.stripe_api',return_value=payload) as api:
            result=create_stripe(root,'https://www.sussurrosdosaber.com')
            self.assertEqual(result['id'],'cs_fixture');self.assertEqual(api.call_args.kwargs['key'],root.id)
            self.assertEqual(api.call_args.args[2]['mode'],'subscription')
        payload['url']='https://evil.example/pay'
        with patch('billing_providers.stripe_api',return_value=payload):
            with self.assertRaises(ProviderError):create_stripe(root,'https://www.sussurrosdosaber.com')


    def test_card_management_portal_uses_verified_customer_and_safe_destination(self):
        root,invoice,sub,rows,intent,api=self.stripe_fixture()
        account=db.session.get(BillingAccount,(self.owner.id,True));account.stripe_subscription=sub['id'];db.session.commit()
        result={'url':'https://billing.stripe.com/p/session/test','livemode':True}
        with patch('billing.stripe_api',side_effect=[sub,result]) as provider:
            response=self.client.post('/premium/pagamentos/gerir-cartao',data={'csrf_token':self.csrf})
            self.assertEqual(response.status_code,303)
            self.assertEqual(provider.call_args.args[2]['customer'],'cus_fixture')
        result['url']='https://evil.example/card'
        with patch('billing.stripe_api',side_effect=[sub,result]):
            response=self.client.post('/premium/pagamentos/gerir-cartao',data={'csrf_token':self.csrf})
            self.assertIn('/premium/pagamentos',response.location)

    def test_card_management_requires_csrf_and_cannot_take_customer_from_client(self):
        self.assertEqual(self.client.post('/premium/pagamentos/gerir-cartao',data={'customer':'cus_other'}).status_code,400)


    def test_test_and_live_accounts_have_separate_agreements_and_holds(self):
        live=lock_account(self.owner.id,live=True);live.stripe_root='real-agreement';db.session.commit()
        sandbox=lock_account(self.owner.id,live=False);sandbox.stripe_root='test-agreement';sandbox.risk_hold=True;db.session.commit()
        self.assertNotEqual(live.live,sandbox.live)
        self.assertEqual(db.session.get(BillingAccount,(self.owner.id,True)).stripe_root,'real-agreement')
        self.assertFalse(db.session.get(BillingAccount,(self.owner.id,True)).risk_hold)


    def test_sandbox_dispute_does_not_block_live_payment_access(self):
        from billing_service import record_dispute
        sandbox=self.order(live=False,method='stripe',provider='stripe',payment_ref='pi_test_'+secrets.token_hex(5))
        record_dispute(sandbox,{'id':'dp_test_'+secrets.token_hex(5),'livemode':False,'payment_intent':sandbox.payment_ref,'status':'needs_response'});db.session.commit()
        real=self.order(method='stripe',provider='stripe',payment_ref='pi_live_'+secrets.token_hex(5))
        record_dispute(real,{'id':'dp_live_'+secrets.token_hex(5),'livemode':True,'payment_intent':real.payment_ref,'status':'won'});db.session.commit()
        self.assertFalse(db.session.get(BillingAccount,(self.owner.id,True)).risk_hold)
        self.assertTrue(db.session.get(BillingAccount,(self.owner.id,False)).risk_hold)
