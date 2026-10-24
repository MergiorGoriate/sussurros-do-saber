"""Reader checkout, verified callbacks, cancellation, financial reporting and CLI."""
import csv
import hashlib
import hmac
import io
import json
import re
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlsplit
import click
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for, send_file
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from admin import validate_csrf, superadmin_required, protect_admin_responses, csv_safe_cell
from extensions import limiter
from premium_access import required as premium_required
from premium_settings import terms as plan_terms
from models import db, utcnow
from submissions import researcher
from premium_models import PremiumPlan, PremiumSubscription, PremiumAudit
from billing_models import BillingAccount, BillingOrder, BillingJournal, BillingEvent, BillingRisk
from billing_providers import (ProviderError, UnmanagedPayment, available_methods, live_mode, enabled,
                               create_clicpay, create_stripe, stripe_api, netshop_checkout_url)
from billing_service import (lock_account, note, change_state, event_record, reconcile_clicpay,
                            reconcile_stripe_checkout, reconcile_invoice, sync_cancellation,
                            post_refund, audit_finance, reconcile_agreement, record_dispute)

billing_bp=Blueprint('billing',__name__,url_prefix='/premium')
finance_bp=Blueprint('premium_finance',__name__,url_prefix='/admin/premium/financeiro')
finance_bp.after_request(protect_admin_responses)
STATES={'initiating':'A iniciar','pending':'Pendente','paid':'Confirmado','failed':'Recusado',
        'expired':'Expirado','cancelled':'Cancelado','review':'A reconciliar','refunded':'Reembolsado'}


@billing_bp.after_request
def private(response):
    response.headers['Cache-Control']='private, no-store'
    response.headers['X-Robots-Tag']='noindex, nofollow, noarchive'
    response.vary.add('Cookie')
    return response


@billing_bp.app_context_processor
def context():
    return dict(billing_available=bool(available_methods()),billing_live=live_mode(),billing_states=STATES,billing_plan_methods=plan_methods,billing_order_state=payment_state)


def plan_methods(plan):
    if not plan.active or plan.price_minor<=0:return {}
    methods=available_methods(plan.currency)
    if not 100<=plan.price_minor<=15000000:
        methods={k:v for k,v in methods.items() if k=='stripe'}
    return methods


def cancelled_evidence():
    return db.exists(db.select(BillingEvent.id).where(BillingEvent.event_key=='poll:'+BillingOrder.id+':CANCELLED'))


def payment_state(order):
    if order.state=='failed' and BillingEvent.query.filter_by(event_key='poll:'+order.id+':CANCELLED').first():return 'cancelled'
    return order.state


def reader_required(view):
    @wraps(view)
    def wrapped(*args,**kwargs):
        from premium_return import remember_plan, auth_url
        if request.endpoint=='billing.checkout':
            ident=kwargs.get('ident')
            if not isinstance(ident,int) or not 0<ident<=2147483647:abort(404)
            plan=db.get_or_404(PremiumPlan,ident)
            if not plan.active:abort(404)
            remember_plan(ident)
        account=researcher()
        if not account:return redirect(auth_url('submissions.login'))
        if not account.verified:
            if request.endpoint=='billing.checkout':return redirect(auth_url('submissions.verify_notice'))
            abort(403,description='Confirme o seu e-mail antes de efectuar um pagamento.')
        return view(*args,**kwargs)
    return wrapped


def financial_transaction(view):
    @wraps(view)
    def wrapped(*args,**kwargs):
        try:return view(*args,**kwargs)
        except (IntegrityError,StaleDataError):
            db.session.rollback()
            abort(409,description='A operação está em curso ou foi alterada. Consulte o histórico antes de repetir.')
    return wrapped


def signer():
    return URLSafeTimedSerializer(current_app.secret_key,salt='premium-financial-quote')


def origin():
    from app import SITE_URL
    parsed=urlsplit(SITE_URL)
    if parsed.scheme!='https' or not parsed.netloc or parsed.username:
        raise ProviderError('Configure HTTPS SITE_URL before enabling checkout')
    return SITE_URL.rstrip('/')


@billing_bp.route('/aderir/<int:ident>',methods=['GET','POST'])
@reader_required
@limiter.limit('20 per hour',methods=['POST'])
@financial_transaction
def checkout(ident):
    plan=db.get_or_404(PremiumPlan,ident)
    account=researcher()
    methods=plan_methods(plan)
    session.pop('premium_return',None)
    error=None
    if request.method=='POST':
        validate_csrf()
        try:
            quote=signer().loads(request.form.get('quote',''),max_age=900)
            if quote.get('owner')!=account.id or quote.get('plan')!=plan.id:raise ValueError('Condições inválidas.')
            prior=db.session.get(BillingOrder,quote['nonce'])
            if prior:
                if prior.owner_id!=account.id:abort(404)
                return redirect(url_for('billing.order_detail',ident=prior.id))
            if quote.get('version')!=plan.version or quote.get('live')!=live_mode():
                raise ValueError('As condições foram actualizadas. Reabra a página e confirme o preço.')
            method=request.form.get('method','')
            if method not in methods:raise ValueError('Este meio de pagamento não está disponível.')
            if request.form.get('consent')!='on':raise ValueError('Confirme o preço e as condições antes de continuar.')
            if method=='stripe' and request.form.get('recurring_consent')!='on':
                raise ValueError('A Stripe exige consentimento explícito para renovação automática.')
            phone=''
            if method in {'mpesa','emola'}:
                phone=re.sub(r'[ +()-]','',request.form.get('phone',''))
                if phone.startswith('258'):phone=phone[3:]
                if not re.fullmatch(r'8[2-7]\d{7}',phone):raise ValueError('Introduza um número moçambicano válido.')
                if plan.currency!='MZN' or not 100<=plan.price_minor<=15000000:raise ValueError('Valor fora dos limites da carteira móvel.')
            public_origin=origin()
            ledger_account=lock_account(account.id)
            if ledger_account.suspended or ledger_account.risk_hold:raise ValueError('A conta exige acompanhamento pela equipa.')
            if ledger_account.open_order_id:
                return redirect(url_for('billing.order_detail',ident=ledger_account.open_order_id))
            if ledger_account.stripe_root and not ledger_account.agreement_closed:
                raise ValueError('Já existe uma assinatura automática. Gira-a na página dos seus pagamentos.')
            previous=PremiumSubscription.query.filter_by(owner_id=account.id).first()
            if previous and previous.status=='active' and previous.source=='complimentary' and previous.ends_at>utcnow():
                raise ValueError('Já dispõe de um acesso de oferta válido. Pode aderir depois do seu término.')
            if previous and previous.status=='active' and previous.ends_at>utcnow() and previous.plan_id!=plan.id:
                raise ValueError('Pode alterar o plano depois de terminar o período já contratado. A renovação do mesmo plano mantém-se disponível.')
            order=BillingOrder(id=quote['nonce'],owner_id=account.id,plan_id=plan.id,
                snapshot={**{k:getattr(plan,k) for k in ('name','interval','price_minor','currency','version','benefits')},
                          'terms':plan_terms(plan)},
                amount_minor=plan.price_minor,currency=plan.currency,method=method,
                provider='stripe' if method=='stripe' else 'clicpay',live=live_mode(),recurring=method=='stripe',
                record_kind='checkout' if method=='stripe' else 'payment',expires_at=utcnow()+timedelta(hours=24))
            db.session.add(order);ledger_account.open_order_id=order.id
            if method=='stripe':
                ledger_account.stripe_root=order.id;ledger_account.stripe_subscription=None
                ledger_account.cancel_requested=False;ledger_account.cancel_confirmed=False;ledger_account.agreement_closed=False
            db.session.commit() # Durable reference BEFORE any external request.
            try:
                if method=='stripe':
                    result=create_stripe(order,public_origin)
                    order.provider_ref=result['id'];order.checkout_url=result['url']
                else:
                    result=create_clicpay(order,phone,public_origin)
                    ref=result.get('clicpay_reference','')
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,120}',ref):raise ProviderError('No confirmed transaction reference')
                    order.provider_ref=ref
                    db.session.commit()
                    if method=='netshop':order.checkout_url=netshop_checkout_url(result.get('checkout_url',''))
                order.state='pending'
                note(order,'pagamento pendente','O pedido foi iniciado. Aguarde a confirmação antes de repetir qualquer cobrança.')
                db.session.commit()
            except ProviderError:
                db.session.rollback()
                order=db.session.get(BillingOrder,order.id);order.state='review'
                note(order,'reconciliação necessária','Não foi possível confirmar a iniciação. Não repita a cobrança; contacte a equipa com a referência do pedido.')
                db.session.commit()
            if order.state=='pending' and order.checkout_url:
                return redirect(order.checkout_url,code=303)
            return redirect(url_for('billing.order_detail',ident=order.id))
        except (ValueError,BadSignature,SignatureExpired,ProviderError) as exc:
            db.session.rollback()
            error=str(exc) if isinstance(exc,ValueError) else 'Não foi possível validar as condições ou o serviço de pagamento. Reabra a página.'
    quote=signer().dumps(dict(owner=account.id,plan=plan.id,version=plan.version,live=live_mode(),nonce=secrets.token_hex(16)))
    return render_template('premium/checkout.html',plan=plan,methods=methods,quote=quote,error=error),400 if error else 200


def owned(ident):
    if not re.fullmatch(r'[a-f0-9]{32}',ident):abort(404)
    return BillingOrder.query.filter_by(id=ident,owner_id=researcher().id).first_or_404()


@billing_bp.get('/pagamentos')
@reader_required
def history():
    from request_values import pagination_page
    from premium import subscription_label, entitled, subscription_for
    owner = researcher()
    account = db.session.get(BillingAccount, (owner.id, live_mode()))
    orders = BillingOrder.query.filter_by(owner_id=owner.id).order_by(BillingOrder.created_at.desc()).paginate(
        page=pagination_page(), per_page=20, error_out=False)
    sub = PremiumSubscription.query.filter_by(owner_id=owner.id).first()
    effective = subscription_for(owner)
    state = subscription_label(sub) if not sub or effective else 'Acesso suspenso para verificação'
    return render_template('premium/payments.html', orders=orders, agreement=account, subscription=sub,
                           subscription_state=state, has_access=entitled(effective))


@billing_bp.get('/pagamentos/<ident>')
@reader_required
def order_detail(ident):
    order=owned(ident)
    return render_template('premium/payment.html',order=order,entries=BillingJournal.query.filter_by(order_id=order.id).all())


@billing_bp.get('/pagamentos/<ident>/comprovativo.pdf')
@reader_required
@limiter.limit('10 per minute')
def receipt(ident):
    from billing_receipts import render_receipt
    order=owned(ident)
    entries=BillingJournal.query.filter_by(order_id=order.id).order_by(BillingJournal.id).all()
    if not any(row.kind=='receipt' for row in entries):abort(404)
    return send_file(render_receipt(order,entries),mimetype='application/pdf',as_attachment=True,
                     download_name='comprovativo-'+order.id+'.pdf',max_age=0)


@billing_bp.post('/pagamentos/<ident>/verificar')
@reader_required
@limiter.limit('20 per hour')
@financial_transaction
def refresh(ident):
    validate_csrf();order=owned(ident)
    if order.checked_at and utcnow()-order.checked_at<timedelta(seconds=20):
        flash('Aguarde alguns segundos antes de voltar a consultar.','warning')
    else:
        try:
            if order.provider=='clicpay':reconcile_clicpay(order)
            elif order.record_kind=='checkout':reconcile_agreement(lock_account(order.owner_id))
            else:reconcile_invoice(order.provider_ref)
            db.session.commit()
            flash('Estado consultado junto do fornecedor.','success')
        except ProviderError:
            db.session.rollback();flash('A confirmação ainda não está disponível. Não repita a cobrança; consulte novamente mais tarde.','warning')
    return redirect(url_for('billing.order_detail',ident=ident))


@billing_bp.post('/pagamentos/cancelar-renovacao')
@reader_required
@limiter.limit('10 per hour')
@financial_transaction
def cancel():
    validate_csrf();account=lock_account(researcher().id)
    if not account.stripe_root or account.agreement_closed:
        flash('Não existe renovação automática activa. As carteiras móveis exigem nova autorização em cada período.','success')
        db.session.commit()
    else:
        account.cancel_requested=True;db.session.commit()
        try:
            account=lock_account(researcher().id);sync_cancellation(account)
            root=db.session.get(BillingOrder,account.stripe_root)
            note(root,'renovação cancelada','O fornecedor confirmou o fim da renovação automática. Mantém o acesso até ao fim do período já pago.')
            db.session.commit();flash('Renovação automática cancelada. Mantém o período já pago.','success')
        except ProviderError:
            db.session.rollback();flash('Pedido de cancelamento registado; aguarda confirmação do fornecedor. A equipa pode acompanhar o pedido.','warning')
    return redirect(url_for('billing.history'))


@billing_bp.post('/pagamentos/gerir-cartao')
@reader_required
@limiter.limit('10 per hour')
def card_portal():
    import os
    validate_csrf()
    account=db.session.get(BillingAccount,(researcher().id,live_mode()))
    configuration=os.getenv('STRIPE_PORTAL_CONFIGURATION','')
    if not account or not account.stripe_subscription or not configuration.startswith('bpc_'):
        abort(400,description='A gestão do cartão não está disponível para esta conta.')
    root=db.session.get(BillingOrder,account.stripe_root)
    try:
        subscription=stripe_api('GET','/subscriptions/'+account.stripe_subscription)
        if not root or root.owner_id!=researcher().id or (subscription.get('metadata') or {}).get('billing_order')!=root.id:
            raise ProviderError('Portal ownership mismatch')
        result=stripe_api('POST','/billing_portal/sessions',{'customer':subscription['customer'],
            'configuration':configuration,'return_url':origin()+'/premium/pagamentos'},key='portal-'+secrets.token_hex(16))
        parsed=urlsplit(result.get('url',''))
        if parsed.scheme!='https' or parsed.netloc!='billing.stripe.com' or result.get('livemode') is not root.live:
            raise ProviderError('Invalid portal destination')
        return redirect(result['url'],code=303)
    except ProviderError:
        flash('Não foi possível abrir a gestão segura do cartão. Contacte a equipa se o problema persistir.','warning')
        return redirect(url_for('billing.history'))


def verify_stripe_signature(raw, header):
    import os
    secret=os.getenv('STRIPE_WEBHOOK_SECRET','')
    if not secret or len(header)>4096:abort(400)
    values={}
    for item in header.split(','):
        key,sep,value=item.partition('=')
        if sep:values.setdefault(key,[]).append(value)
    try:stamp=int(values['t'][0])
    except (KeyError,ValueError,IndexError):abort(400)
    if abs(time.time()-stamp)>300:abort(400)
    expected=hmac.new(secret.encode(),str(stamp).encode()+b'.'+raw,hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected,v) for v in values.get('v1',[])):abort(400)


@billing_bp.post('/webhooks/stripe')
@limiter.limit('120 per minute')
@financial_transaction
def stripe_webhook():
    request.max_content_length=262144
    raw=request.get_data()
    verify_stripe_signature(raw,request.headers.get('Stripe-Signature',''))
    try:event=json.loads(raw)
    except (ValueError,TypeError):abort(400)
    if not isinstance(event,dict) or not re.fullmatch(r'evt_[A-Za-z0-9_]+',event.get('id','')):abort(400)
    if event.get('livemode') is not live_mode():abort(400)
    kind=event.get('type','')
    data=event.get('data')
    if not isinstance(kind,str) or not isinstance(data,dict) or not isinstance(data.get('object'),dict):abort(400)
    obj=data['object'];ref=obj.get('id','')
    if not isinstance(ref,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,120}',ref):abort(400)
    key='stripe:'+event['id']
    if BillingEvent.query.filter_by(event_key=key).first():return jsonify(received=True)
    try:
        if kind in {'invoice.paid','invoice.payment_succeeded','invoice.payment_failed','invoice.payment_action_required'}:
            reconcile_invoice(ref)
        elif kind in {'checkout.session.completed','checkout.session.expired','checkout.session.async_payment_failed'}:
            order=BillingOrder.query.filter_by(provider='stripe',provider_ref=ref).first()
            if order:reconcile_stripe_checkout(order)
        elif kind.startswith('customer.subscription.'):
            result=stripe_api('GET','/subscriptions/'+ref)
            root_id=(result.get('metadata') or {}).get('billing_order')
            root=db.session.get(BillingOrder,root_id) if isinstance(root_id,str) else None
            if root:
                account=lock_account(root.owner_id)
                if account.stripe_root==root.id:
                    account.stripe_subscription=ref
                    account.agreement_closed=result.get('status') in {'canceled','incomplete_expired'}
                    account.cancel_confirmed=bool(result.get('cancel_at_period_end') or account.agreement_closed)
                    if account.cancel_requested and not account.cancel_confirmed:sync_cancellation(account)
        elif kind=='charge.refunded':
            charge=stripe_api('GET','/charges/'+ref)
            order=BillingOrder.query.filter_by(provider='stripe',record_kind='payment',payment_ref=charge.get('payment_intent')).first() if isinstance(charge.get('payment_intent'),str) else None
            if order:
                if charge.get('livemode') is not order.live or charge.get('currency','').upper()!=order.currency or charge.get('amount')!=order.amount_minor:
                    raise ProviderError('Refund mismatch')
                post_refund(order,charge.get('amount_refunded'),{'charge':ref,'refund_total':charge.get('amount_refunded')})
        elif kind.startswith('charge.dispute.'):
            dispute=stripe_api('GET','/disputes/'+ref)
            order=BillingOrder.query.filter_by(provider='stripe',record_kind='payment',payment_ref=dispute.get('payment_intent')).first() if isinstance(dispute.get('payment_intent'),str) else None
            if order:
                record_dispute(order,dispute)
        # Store only an event identity, type and digest, never raw card/customer payloads.
        event_record(key,kind,ref,{'id':event['id'],'type':kind,'reference':ref})
        db.session.commit();return jsonify(received=True)
    except UnmanagedPayment:
        db.session.rollback()
        event_record(key,kind,ref,{'id':event['id'],'type':kind,'reference':ref,'unmanaged':True})
        db.session.commit();return jsonify(received=True)
    except ProviderError:
        db.session.rollback();return jsonify(received=False,retry=True),503


def filtered_orders():
    """Only whitelisted, validated filters; shared by history and immutable ledger export."""
    query=BillingOrder.query
    filters={key:request.args.get(key,'').strip() for key in ('q','state','mode','plan','from','to')}
    if len(filters['q'])>120:abort(400)
    if filters['state'] and filters['state'] not in STATES:abort(400)
    if filters['mode'] not in ('','live','test'):abort(400)
    if filters['mode']:query=query.filter(BillingOrder.live.is_(filters['mode']=='live'))
    if filters['state']=='cancelled':query=query.filter(BillingOrder.state=='failed',cancelled_evidence())
    elif filters['state']:
        query=query.filter(BillingOrder.state==filters['state'])
        if filters['state']=='failed':query=query.filter(~cancelled_evidence())
    if filters['q']:
        from submission_models import Researcher
        value=filters['q']
        query=query.join(Researcher,BillingOrder.owner_id==Researcher.id).filter(db.or_(
            BillingOrder.id.contains(value,autoescape=True),BillingOrder.provider_ref.contains(value,autoescape=True),
            Researcher.email.contains(value,autoescape=True)))
    if filters['plan']:
        try:
            ident=int(filters['plan'])
            if not 0<ident<=2147483647:raise ValueError()
        except ValueError:abort(400)
        query=query.filter(BillingOrder.plan_id==ident)
    dates={}
    for key in ('from','to'):
        if filters[key]:
            try:dates[key]=datetime.strptime(filters[key],'%Y-%m-%d')
            except ValueError:abort(400)
    if len(dates)==2 and dates['from']>dates['to']:abort(400)
    if 'from' in dates:query=query.filter(BillingOrder.created_at>=dates['from'])
    if 'to' in dates:
        try:end=dates['to']+timedelta(days=1)
        except OverflowError:abort(400)
        query=query.filter(BillingOrder.created_at<end)
    return query,{key:value for key,value in filters.items() if value}


@finance_bp.get('')
@premium_required('finance')
def dashboard():
    from request_values import pagination_page
    query,filters=filtered_orders()
    orders=query.order_by(BillingOrder.created_at.desc()).paginate(page=pagination_page(),per_page=30,error_out=False)
    now=utcnow()
    subscriptions=PremiumSubscription.query.filter_by(source='billing')
    summary=dict(total=subscriptions.count(),active=subscriptions.filter(PremiumSubscription.status=='active',PremiumSubscription.starts_at<=now,PremiumSubscription.ends_at>now).count(),expired=subscriptions.filter(PremiumSubscription.ends_at<=now).count(),pending=query.filter(BillingOrder.state.in_(['initiating','pending','review'])).count(),confirmed=query.filter(BillingOrder.state.in_(['paid','refunded']),BillingOrder.record_kind=='payment').count())
    popular=db.session.query(PremiumPlan.name,db.func.count(BillingJournal.id)).join(BillingOrder,BillingOrder.plan_id==PremiumPlan.id).join(BillingJournal,BillingJournal.order_id==BillingOrder.id).filter(BillingJournal.kind=='receipt',BillingJournal.live.is_(True)).group_by(PremiumPlan.id,PremiumPlan.name).order_by(db.func.count(BillingJournal.id).desc()).limit(5).all()
    return render_template('admin/premium_finance.html',orders=orders,report=audit_finance(),filters=filters,summary=summary,popular=popular,plans=PremiumPlan.query.order_by(PremiumPlan.name).all(),
        accounts=BillingAccount.query.filter(db.or_(BillingAccount.cancel_requested.is_(True),BillingAccount.risk_hold.is_(True),BillingAccount.suspended.is_(True))).limit(100).all())


@finance_bp.post('/<ident>/reconciliar')
@premium_required('finance')
@limiter.limit('30 per hour')
@financial_transaction
def reconcile_admin(ident):
    validate_csrf();order=db.get_or_404(BillingOrder,ident)
    try:
        if order.provider=='clicpay':reconcile_clicpay(order)
        elif order.record_kind=='checkout':reconcile_agreement(lock_account(order.owner_id))
        else:reconcile_invoice(order.provider_ref)
        db.session.commit();flash('Reconciliação concluída.','success')
    except ProviderError:
        db.session.rollback();flash('A reconciliação exige confirmação do fornecedor. Nenhum pagamento foi presumido.','warning')
    return redirect(url_for('premium_finance.dashboard'))


@finance_bp.post('/contas/<int:ident>/suspensao')
@premium_required('finance')
@financial_transaction
def suspension(ident):
    validate_csrf();reason=request.form.get('reason','').strip()
    if not 10<=len(reason)<=500:abort(400)
    account=lock_account(ident,live=request.form.get('live')=='true')
    action=request.form.get('action')
    if action not in {'suspend','resume'}:abort(400)
    account.suspended=action=='suspend'
    # A risk hold can only be released after independent provider verification, outside this toggle.
    db.session.add(PremiumAudit(actor=str(session.get('admin_id') or 'primary-environment'),action='billing.'+action,
        entity_id=ident,detail={'reason':reason}))
    db.session.commit();return redirect(url_for('premium_finance.dashboard'))


@finance_bp.get('/exportar.csv')
@premium_required('finance')
def export():
    output=io.StringIO();writer=csv.writer(output)
    writer.writerow(['id','pedido','tipo','debito','credito','unidades_minimas','moeda','ambiente','data_utc'])
    query,_=filtered_orders()
    for row in BillingJournal.query.filter(BillingJournal.order_id.in_(query.with_entities(BillingOrder.id))).order_by(BillingJournal.id).yield_per(500):
        writer.writerow([csv_safe_cell(v) for v in [row.id,row.order_id,row.kind,row.debit,row.credit,row.amount_minor,row.currency,'live' if row.live else 'test',row.created_at.isoformat()]])
    return current_app.response_class(output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=premium-financeiro.csv'})


def install_billing_cli(app):
    @app.cli.command('premium-reconciliar')
    @click.option('--limit',default=50,type=click.IntRange(1,500))
    def reconcile_command(limit):
        from sqlalchemy import func
        ids=[r.id for r in BillingOrder.query.filter(BillingOrder.live==live_mode(),BillingOrder.state.in_(['pending','review','initiating']))
             .order_by(func.coalesce(BillingOrder.checked_at,BillingOrder.created_at)).limit(limit)]
        failures=0
        for ident in ids:
            try:
                order=db.session.get(BillingOrder,ident)
                if order.provider=='clicpay':reconcile_clicpay(order)
                elif order.record_kind=='checkout':reconcile_agreement(lock_account(order.owner_id))
                else:reconcile_invoice(order.provider_ref)
                db.session.commit()
            except (ProviderError,IntegrityError,StaleDataError):
                db.session.rollback();failures+=1
                db.session.get(BillingOrder,ident).checked_at=utcnow();db.session.commit()
                click.echo('Revisão necessária: '+ident)
        # Poll the current recurring invoice too, including after a missed webhook.
        recurring=[a.owner_id for a in BillingAccount.query.filter(BillingAccount.live==live_mode(),BillingAccount.stripe_root.isnot(None),BillingAccount.agreement_closed.is_(False)).limit(limit)]
        for owner in recurring:
            try:
                account=lock_account(owner)
                root=db.session.get(BillingOrder,account.stripe_root)
                if root and root.live==live_mode():reconcile_agreement(account)
                db.session.commit()
            except (ProviderError,IntegrityError,StaleDataError):db.session.rollback();failures+=1
        # Durable in-site expiry notices, deduplicated by subscription and end date.
        for sub in PremiumSubscription.query.filter_by(source='billing').filter(PremiumSubscription.ends_at<=utcnow()+timedelta(days=3)).limit(limit):
            order=BillingOrder.query.filter_by(owner_id=sub.owner_id,live=True,state='paid',record_kind='payment').order_by(BillingOrder.created_at.desc()).first()
            if order:
                text='O acesso terminou.' if sub.ends_at<=utcnow() else 'O período de acesso termina dentro de três dias. Consulte a sua assinatura e a modalidade de renovação.'
                note(order,'validade '+sub.ends_at.isoformat()+(' expired' if sub.ends_at<=utcnow() else ' reminder'),text)
        db.session.commit()
        # Retry durable cancellation requests even when sales are disabled.
        owners=[a.owner_id for a in BillingAccount.query.filter_by(live=live_mode(),cancel_requested=True,cancel_confirmed=False).limit(limit)]
        for owner in owners:
            try:
                account=lock_account(owner);sync_cancellation(account);db.session.commit()
            except (ProviderError,IntegrityError,StaleDataError):db.session.rollback();failures+=1
        from premium_features import process_publications
        published=process_publications(limit)
        click.echo(json.dumps({'examined':len(ids),'needs_review':failures,'published_resources':published}))
        if failures:raise click.exceptions.Exit(1)

    @app.cli.command('premium-recuperar-stripe')
    @click.option('--pedido',required=True)
    @click.option('--sessao',required=True)
    def recover_stripe(pedido,sessao):
        order=db.session.get(BillingOrder,pedido)
        if not order or order.provider!='stripe' or order.record_kind!='checkout' or order.provider_ref:
            raise click.ClickException('O pedido não admite recuperação de referência.')
        result=stripe_api('GET','/checkout/sessions/'+sessao)
        if result.get('id')!=sessao or result.get('client_reference_id')!=order.id or result.get('livemode') is not order.live:
            raise click.ClickException('A sessão não corresponde ao pedido e ao ambiente.')
        lock_account(order.owner_id);order.provider_ref=sessao;order.state='pending'
        event_record('recover:'+order.id,'stripe.recovery',sessao,{'order':order.id,'session':sessao})
        db.session.commit()
        reconcile_stripe_checkout(order);db.session.commit()
        click.echo('Referência recuperada e estado reconciliado; não foi iniciada outra cobrança.')

    @app.cli.command('premium-confirmar-reembolso-local')
    @click.option('--pedido',required=True)
    @click.option('--total-minor',required=True,type=click.IntRange(1,2147483647))
    @click.option('--documento',required=True)
    @click.option('--motivo',required=True)
    def local_refund(pedido,total_minor,documento,motivo):
        if not 5<=len(documento)<=120 or not 10<=len(motivo)<=500:
            raise click.ClickException('Identifique o documento verificado e o motivo.')
        order=db.session.get(BillingOrder,pedido)
        if not order or order.provider!='clicpay' or not order.provider_ref or order.live!=live_mode():
            raise click.ClickException('Pedido ou ambiente inválido.')
        from billing_providers import clicpay_status
        result=clicpay_status(order.provider_ref)
        state=result.get('status','').upper()
        if result.get('clicpay_reference')!=order.provider_ref or state not in {'REFUNDED','PARTIALLY_REFUNDED'}:
            raise click.ClickException('O fornecedor não confirma um reembolso desta transacção.')
        if state=='REFUNDED' and total_minor!=order.amount_minor:
            raise click.ClickException('Um reembolso total deve corresponder ao pagamento original.')
        if state=='PARTIALLY_REFUNDED' and not 0<total_minor<order.amount_minor:
            raise click.ClickException('Montante parcial inválido.')
        from billing_service import post_receipt
        account=lock_account(order.owner_id)
        if not BillingJournal.query.filter_by(event_key='receipt:'+order.id).first():post_receipt(order,account)
        post_refund(order,total_minor,{'document':documento,'source':'operator_verified_provider_report'})
        risk=db.session.get(BillingRisk,'clicpay:'+order.id)
        if risk:risk.resolved=True;risk.status='reconciled'
        db.session.flush()
        account.risk_hold=BillingRisk.query.filter_by(owner_id=order.owner_id,live=order.live,resolved=False).first() is not None
        db.session.add(PremiumAudit(actor='finance-cli',action='billing.refund.evidence',entity_id=order.owner_id,
            detail={'order':order.id,'document':documento,'reason':motivo,'total_minor':total_minor}))
        db.session.commit();click.echo('Reembolso já efectuado registado. Este comando não envia dinheiro.')

    @app.cli.command('premium-auditar-financas')
    def audit_command():
        report=audit_finance();click.echo(json.dumps(report))
        if report['errors']:raise click.exceptions.Exit(1)

