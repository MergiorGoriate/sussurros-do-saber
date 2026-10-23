"""Provider reconciliation and atomic, idempotent posting of Premium payments."""
import calendar
import hashlib
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from models import db, utcnow
from submission_models import Researcher
from premium_models import PremiumPlan, PremiumSubscription
from billing_models import BillingAccount, BillingOrder, BillingGrant, BillingJournal, BillingEvent, BillingRisk
from billing_providers import ProviderError, stripe_api, clicpay_status, live_mode, UnmanagedPayment

FINAL={'paid','failed','expired','refunded'}


def next_period(start, interval):
    months=1 if interval=='monthly' else 12
    index=start.year*12+start.month-1+months
    year, month=divmod(index,12);month+=1
    return start.replace(year=year,month=month,day=min(start.day,calendar.monthrange(year,month)[1]))


def lock_account(owner_id, *, live=None):
    mode=live_mode() if live is None else live
    # The real identity row serializes initial account creation on PostgreSQL.
    db.session.execute(db.select(Researcher.id).where(Researcher.id==owner_id).with_for_update()).scalar_one()
    account=db.session.execute(db.select(BillingAccount).where(BillingAccount.owner_id==owner_id,BillingAccount.live==mode).with_for_update()).scalar_one_or_none()
    if account is None:
        account=BillingAccount(owner_id=owner_id,live=mode)
        db.session.add(account);db.session.flush()
    # Optimistic concurrency also detects competing writers on SQLite.
    account.version+=1
    return account


def note(order, state, text):
    from internal_notices import emit
    mode='' if order.live else '[TESTE] '
    emit(None,mode+'Premium: '+state,text,researcher_id=order.owner_id,
         key='billing:'+order.id+':'+state)


def event_record(key, kind, ref, payload):
    if BillingEvent.query.filter_by(event_key=key).first(): return False
    db.session.add(BillingEvent(event_key=key,kind=kind[:80],object_ref=ref[:120],
        digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()))
    return True


def change_state(order, state, *, cancelled=False):
    if order.state==state or order.state in {'paid','refunded'}:return
    order.state=state
    if state in {'failed','expired'}:
        account=lock_account(order.owner_id,live=order.live)
        if account.open_order_id==order.id:account.open_order_id=None
        note(order,'pagamento cancelado' if cancelled else {'failed':'pagamento recusado','expired':'pedido expirado'}[state],'O pagamento não foi confirmado. Não foi concedido um novo período de acesso.')


def recompute_access(owner_id):
    grants=BillingGrant.query.filter_by(owner_id=owner_id,revoked=False).order_by(BillingGrant.starts_at).all()
    sub=PremiumSubscription.query.filter_by(owner_id=owner_id).first()
    if sub and sub.source=='complimentary':
        # Sales are blocked while a complimentary grant is active. Preserve historical offers.
        if sub.ends_at>utcnow() and sub.status=='active':return
    merged=[]
    for grant in grants:
        if merged and grant.starts_at<=merged[-1][1]:
            if grant.ends_at>merged[-1][1]:merged[-1]=(merged[-1][0],grant.ends_at,grant.order_id)
        else:merged.append((grant.starts_at,grant.ends_at,grant.order_id))
    if not merged:
        if sub and sub.source=='billing':sub.status='cancelled'
        return
    now=utcnow()
    chosen=next((r for r in merged if r[0]<=now<r[1]),None)
    chosen=chosen or next((r for r in merged if r[0]>now),None) or merged[-1]
    order=db.session.get(BillingOrder,chosen[2])
    if sub is None:
        sub=PremiumSubscription(owner_id=owner_id);db.session.add(sub)
    sub.plan_id=order.plan_id;sub.plan_snapshot=order.snapshot
    sub.starts_at,sub.ends_at=chosen[:2]
    sub.source='billing';sub.reason='Acesso derivado de pagamentos confirmados.';sub.status='active'


def post_receipt(order, account, start=None, end=None):
    key='receipt:'+order.id
    if BillingJournal.query.filter_by(event_key=key).first():return False
    if order.record_kind!='payment':raise ProviderError('Quote cannot be posted as receipt')
    db.session.add(BillingJournal(event_key=key,order_id=order.id,kind='receipt',debit='gateway_clearing',
        credit='premium_deferred',amount_minor=order.amount_minor,currency=order.currency,live=order.live))
    order.state='paid'
    if account.open_order_id in {order.id,order.root_id}:account.open_order_id=None
    if order.live:
        if start is None:
            latest=db.session.scalar(db.select(func.max(BillingGrant.ends_at)).where(
                BillingGrant.owner_id==order.owner_id,BillingGrant.revoked.is_(False)))
            start=max(utcnow(),latest) if latest else utcnow()
            end=next_period(start,order.snapshot['interval'])
        db.session.add(BillingGrant(order_id=order.id,owner_id=order.owner_id,starts_at=start,ends_at=end))
        db.session.flush();recompute_access(order.owner_id)
    note(order,'pagamento confirmado',f'Pedido {order.id}: {order.amount_minor/100:.2f} {order.currency}. '+
         ('Consulte a validade do acesso na sua conta.' if order.live else 'Ensaio sem activação de acesso real.'))
    return True


def post_refund(order, total_minor, evidence):
    account=lock_account(order.owner_id,live=order.live)
    receipt=BillingJournal.query.filter_by(event_key='receipt:'+order.id).first()
    if not receipt or type(total_minor) is not int or not order.refund_minor<=total_minor<=order.amount_minor:
        raise ProviderError('Refund needs a confirmed matching receipt')
    delta=total_minor-order.refund_minor
    if not delta:return
    db.session.add(BillingJournal(event_key='refund:'+order.id+':'+str(total_minor),order_id=order.id,kind='refund',
        debit='premium_deferred',credit='gateway_clearing',amount_minor=delta,currency=order.currency,live=order.live))
    order.refund_minor=total_minor
    if total_minor==order.amount_minor:
        order.state='refunded'
        grant=db.session.get(BillingGrant,order.id)
        if grant:grant.revoked=True;db.session.flush();recompute_access(order.owner_id)
    event_record('refund-evidence:'+order.id+':'+str(total_minor),'refund',order.payment_ref or order.provider_ref,evidence)
    note(order,'reembolso '+str(total_minor),f'Reembolso acumulado: {total_minor/100:.2f} {order.currency}.')


def reconcile_clicpay(order):
    if order.provider!='clicpay' or not order.provider_ref:raise ProviderError('Transaction reference missing; manual reconciliation required')
    if order.live!=live_mode():raise ProviderError('Payment environment mismatch')
    result=clicpay_status(order.provider_ref)
    if result.get('clicpay_reference')!=order.provider_ref:raise ProviderError('Reference mismatch')
    account=lock_account(order.owner_id,live=order.live)
    # Amount/currency are bound to this authenticated initiation reference; never accept a client reference.
    if 'amount' in result:
        from decimal import Decimal
        if Decimal(str(result['amount']))*100!=order.amount_minor:raise ProviderError('Amount mismatch')
    if 'currency' in result and result['currency'].upper()!=order.currency:raise ProviderError('Currency mismatch')
    state=result.get('status','').upper()
    order.checked_at=utcnow()
    event_record('poll:'+order.id+':'+state,'clicpay.'+state,order.provider_ref,{'reference':order.provider_ref,'state':state})
    if state=='SUCCESSFUL':
        post_receipt(order,account)
    elif state in {'FAILED','CANCELLED','REJECTED'}:
        change_state(order,'failed',cancelled=state=='CANCELLED')
    elif state=='REFUNDED':
        if not BillingJournal.query.filter_by(event_key='receipt:'+order.id).first():post_receipt(order,account)
        post_refund(order,order.amount_minor,{'reference':order.provider_ref,'status':state})
    elif state=='PARTIALLY_REFUNDED':
        risk=db.session.get(BillingRisk,'clicpay:'+order.id)
        if not risk:
            db.session.add(BillingRisk(reference='clicpay:'+order.id,live=order.live,owner_id=order.owner_id,order_id=order.id,status='partial_refund'))
        account.risk_hold=True;note(order,'reconciliação necessária','Reembolso parcial: a equipa precisa de confirmar o montante junto do fornecedor.')
    elif order.state not in FINAL:
        order.state='review' if utcnow()>order.expires_at else 'pending'
    return order


def invoice_subscription(invoice):
    parent=invoice.get('parent') or {}
    return (parent.get('subscription_details') or {}).get('subscription') or invoice.get('subscription')


def reconcile_invoice(invoice_id):
    invoice=stripe_api('GET','/invoices/'+invoice_id)
    if invoice.get('id')!=invoice_id:raise ProviderError('Invoice reference mismatch')
    subscription_id=invoice_subscription(invoice)
    if not isinstance(subscription_id,str):raise ProviderError('Invoice has no subscription')
    subscription=stripe_api('GET','/subscriptions/'+subscription_id)
    root_id=(subscription.get('metadata') or {}).get('billing_order')
    root=db.session.get(BillingOrder,root_id) if isinstance(root_id,str) else None
    if not root:raise UnmanagedPayment('Payment belongs to another product')
    if root.provider!='stripe' or root.record_kind!='checkout':raise ProviderError('Unknown agreement')
    if root.live!=live_mode() or invoice.get('livemode') is not root.live or subscription.get('livemode') is not root.live:
        raise ProviderError('Invoice environment mismatch')
    if subscription.get('id')!=subscription_id or invoice.get('customer')!=subscription.get('customer'):
        raise ProviderError('Invoice ownership mismatch')
    account=lock_account(root.owner_id,live=root.live)
    if account.stripe_root!=root.id or (account.stripe_subscription and account.stripe_subscription!=subscription_id):
        raise ProviderError('Conflicting recurring agreement')
    account.stripe_subscription=subscription_id
    order=BillingOrder.query.filter_by(provider='stripe',provider_ref=invoice_id).first()
    if order is None:
        order=BillingOrder(owner_id=root.owner_id,plan_id=root.plan_id,snapshot=root.snapshot,
            amount_minor=root.amount_minor,currency=root.currency,method='stripe',provider='stripe',
            live=root.live,recurring=True,provider_ref=invoice_id,root_id=root.id,
            state='pending',expires_at=utcnow()+timedelta(days=2))
        db.session.add(order);db.session.flush()
    order.checked_at=utcnow()
    if invoice.get('status') in {'void','uncollectible'}:
        change_state(order,'failed');return order
    if invoice.get('status')!='paid':
        note(order,'pagamento pendente','A renovação ainda não foi confirmada. O acesso mantém apenas a validade já paga.')
        return order
    items=(subscription.get('items') or {}).get('data',[])
    lines=(invoice.get('lines') or {}).get('data',[])
    if len(items)!=1 or len(lines)!=1 or (invoice.get('lines') or {}).get('has_more'):
        raise ProviderError('Unexpected invoice lines')
    price=items[0].get('price') or {}
    expected_interval='month' if root.snapshot['interval']=='monthly' else 'year'
    if (items[0].get('quantity')!=1 or price.get('unit_amount')!=root.amount_minor
        or price.get('currency','').upper()!=root.currency or (price.get('recurring') or {}).get('interval')!=expected_interval
        or (price.get('recurring') or {}).get('interval_count',1)!=1):raise ProviderError('Agreement price changed')
    if any(invoice.get(k)!=root.amount_minor for k in ('amount_paid','amount_due','total')) or invoice.get('currency','').upper()!=root.currency:
        raise ProviderError('Invoice amount mismatch')
    if invoice.get('collection_method')!='charge_automatically' or invoice.get('paid_out_of_band'):
        raise ProviderError('Unsupported settlement')
    payments=stripe_api('GET','/invoice_payments',{'invoice':invoice_id,'limit':100})
    rows=[p for p in payments.get('data',[]) if p.get('status')=='paid']
    if payments.get('has_more') or len(rows)!=1:raise ProviderError('Payment evidence missing')
    row=rows[0];payment=row.get('payment') or {}
    if (row.get('invoice')!=invoice_id or row.get('amount_paid')!=root.amount_minor or row.get('livemode') is not root.live
        or row.get('currency','').upper()!=root.currency or payment.get('type')!='payment_intent'):
        raise ProviderError('Invalid payment evidence')
    pi=stripe_api('GET','/payment_intents/'+payment['payment_intent'])
    if pi.get('id')!=payment['payment_intent']:raise ProviderError('Payment reference mismatch')
    if (pi.get('status')!='succeeded' or pi.get('amount_received')!=root.amount_minor or pi.get('livemode') is not root.live
        or pi.get('currency','').upper()!=root.currency or pi.get('customer')!=subscription.get('customer')):
        raise ProviderError('Payment not settled')
    period=lines[0].get('period') or {}
    try:
        start=datetime.fromtimestamp(period['start'],timezone.utc).replace(tzinfo=None)
        end=datetime.fromtimestamp(period['end'],timezone.utc).replace(tzinfo=None)
    except (KeyError,TypeError,ValueError,OverflowError):raise ProviderError('Invalid billing period') from None
    days=(end-start).total_seconds()/86400
    if not ((26<=days<=32) if expected_interval=='month' else (364<=days<=367)):
        raise ProviderError('Prorated or unsupported billing period')
    order.payment_ref=pi['id']
    post_receipt(order,account,start,end)
    # Fetch the latest charge so a refund/dispute arriving before invoice.paid is not lost.
    if isinstance(pi.get('latest_charge'),str):
        charge=stripe_api('GET','/charges/'+pi['latest_charge'])
        if charge.get('payment_intent')!=pi['id'] or charge.get('amount')!=order.amount_minor or charge.get('livemode') is not order.live:
            raise ProviderError('Charge mismatch')
        total_refund=charge.get('amount_refunded',0)
        if total_refund:post_refund(order,total_refund,{'charge':charge['id'],'refund_total':total_refund})
        if charge.get('disputed'):
            disputes=stripe_api('GET','/disputes',{'charge':charge['id'],'limit':100})
            if disputes.get('has_more'):raise ProviderError('Dispute reconciliation incomplete')
            for dispute in disputes.get('data',[]):record_dispute(order,dispute)
    root.state='paid'
    if account.open_order_id==root.id:account.open_order_id=None
    return order


def sync_cancellation(account):
    if not account.cancel_requested:return
    if not account.stripe_subscription:
        root=db.session.get(BillingOrder,account.stripe_root) if account.stripe_root else None
        if root and root.provider_ref:
            session=stripe_api('GET','/checkout/sessions/'+root.provider_ref)
            if session.get('subscription'):
                account.stripe_subscription=session['subscription']
            elif session.get('status')=='open':
                result=stripe_api('POST','/checkout/sessions/'+root.provider_ref+'/expire',key='expire-'+root.id)
                if result.get('status')!='expired':raise ProviderError('Cancellation not confirmed')
                change_state(root,'expired');account.cancel_confirmed=True;account.agreement_closed=True;return
            elif session.get('status')=='expired':
                change_state(root,'expired');account.cancel_confirmed=True;account.agreement_closed=True;return
        if not account.stripe_subscription:raise ProviderError('Cancellation awaiting provider reconciliation')
    result=stripe_api('POST','/subscriptions/'+account.stripe_subscription,{'cancel_at_period_end':'true'},
                      key='cancel-'+account.stripe_root)
    if result.get('cancel_at_period_end') is not True and result.get('status')!='canceled':
        raise ProviderError('Cancellation not confirmed')
    account.cancel_confirmed=True
    account.agreement_closed=result.get('status')=='canceled'


def reconcile_stripe_checkout(order):
    result=stripe_api('GET','/checkout/sessions/'+order.provider_ref)
    if result.get('id')!=order.provider_ref or result.get('client_reference_id')!=order.id or result.get('livemode') is not order.live:
        raise ProviderError('Session mismatch')
    account=lock_account(order.owner_id,live=order.live)
    if result.get('subscription'):
        if account.stripe_subscription and account.stripe_subscription!=result['subscription']:raise ProviderError('Agreement conflict')
        account.stripe_subscription=result['subscription']
    if result.get('invoice'):reconcile_invoice(result['invoice'])
    elif result.get('status')=='expired':
        change_state(order,'expired');account.agreement_closed=True
    if account.cancel_requested:sync_cancellation(account)


def audit_finance():
    errors=[];totals={}
    for order in BillingOrder.query.filter_by(record_kind='payment'):
        rows=BillingJournal.query.filter_by(order_id=order.id).all()
        receipts=sum(r.amount_minor for r in rows if r.kind=='receipt')
        refunds=sum(r.amount_minor for r in rows if r.kind=='refund')
        if order.state in {'paid','refunded'} and receipts!=order.amount_minor:errors.append(order.id+':receipt')
        if order.state not in {'paid','refunded'} and receipts:errors.append(order.id+':state')
        if refunds!=order.refund_minor or refunds>receipts:errors.append(order.id+':refund')
        if any(r.currency!=order.currency or r.live!=order.live for r in rows):errors.append(order.id+':currency')
        for row in rows:
            expected=('gateway_clearing','premium_deferred') if row.kind=='receipt' else ('premium_deferred','gateway_clearing')
            if (row.debit,row.credit)!=expected:errors.append(order.id+':accounts')
        key=('live:' if order.live else 'test:')+order.currency
        total=totals.setdefault(key,{'gross_minor':0,'refund_minor':0,'net_clearing_minor':0})
        total['gross_minor']+=receipts;total['refund_minor']+=refunds;total['net_clearing_minor']+=receipts-refunds
    for grant in BillingGrant.query:
        order=db.session.get(BillingOrder,grant.order_id)
        if not order or not order.live or not BillingJournal.query.filter_by(event_key='receipt:'+grant.order_id).first():
            errors.append(grant.order_id+':access_without_receipt')
        elif order.refund_minor==order.amount_minor and not grant.revoked:
            errors.append(grant.order_id+':refunded_access')
    return {'errors':errors,'totals':totals,'unresolved_risks':BillingRisk.query.filter_by(resolved=False).count(),'basis':'gateway clearing; excludes unknown fees, bank settlement and tax recognition'}


def reconcile_agreement(account):
    if not account.stripe_subscription:
        root=db.session.get(BillingOrder,account.stripe_root)
        if root and root.provider_ref:reconcile_stripe_checkout(root)
        return
    result=stripe_api('GET','/subscriptions/'+account.stripe_subscription)
    if result.get('id')!=account.stripe_subscription or (result.get('metadata') or {}).get('billing_order')!=account.stripe_root:
        raise ProviderError('Agreement identity mismatch')
    account.agreement_closed=result.get('status') in {'canceled','incomplete_expired'}
    account.cancel_confirmed=bool(result.get('cancel_at_period_end') or account.agreement_closed)
    invoice=result.get('latest_invoice')
    if isinstance(invoice,str):reconcile_invoice(invoice)
    if account.cancel_requested and not account.cancel_confirmed:sync_cancellation(account)


def record_dispute(order, dispute):
    if dispute.get('payment_intent')!=order.payment_ref or dispute.get('livemode') is not order.live:
        raise ProviderError('Dispute identity mismatch')
    account=lock_account(order.owner_id,live=order.live)
    risk=db.session.get(BillingRisk,dispute['id'])
    if not risk:
        risk=BillingRisk(reference=dispute['id'],live=order.live,owner_id=order.owner_id,order_id=order.id)
        db.session.add(risk)
    risk.status=dispute.get('status','needs_review');risk.resolved=risk.status=='won'
    db.session.flush()
    account.risk_hold=BillingRisk.query.filter_by(owner_id=order.owner_id,live=order.live,resolved=False).first() is not None
    note(order,'contestação '+risk.status,'A contestação foi actualizada. A equipa financeira acompanha os valores em disputa.')
