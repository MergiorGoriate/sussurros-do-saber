"""Subscriber workspace, limited grace access and audited service requests."""
from datetime import timedelta
from functools import wraps
from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from admin import validate_csrf
from extensions import limiter
from models import db, utcnow
from premium_models import (PremiumAccessHistory, PremiumEnrollment, PremiumServiceRequest,
    PremiumSubscription, PremiumContent, PremiumProgress, PremiumCertificate)
from premium_access import can, required
from premium_resources import detail, reader, visible_clause, parse_local
from premium_settings import notify
from submissions import researcher

REQUEST_KINDS = {'refund':'Reembolso','extension':'Prorrogação de curso',
                 'reactivation':'Reactivação de curso','assistance':'Assistência'}
REQUEST_STATES = {'pending':'Pendente','review':'Em análise','approved':'Aprovado',
                  'rejected':'Recusado','fulfilled':'Concluído'}
GRACE = timedelta(days=3)


def in_grace(sub, now=None):
    now = now or utcnow()
    return bool(sub and sub.source == 'billing' and sub.status == 'active'
                and sub.starts_at < sub.ends_at <= now < sub.ends_at + GRACE)


def previously_accessed(sub, item):
    history = db.session.get(PremiumAccessHistory,(sub.owner_id,item.id))
    return bool(history and history.first_access_at < sub.ends_at)


def can_access(sub, item, resource, now=None, allow_grace=True):
    from premium import entitled
    if not item.published or resource.state != 'published': return False
    if item.open_access_required: return True
    if not sub or resource.plan_ids and sub.plan_id not in resource.plan_ids: return False
    if sub.plan.tier in {'pro','max'} and not resource.plan_ids: return False
    return entitled(sub,now) or bool(allow_grace and in_grace(sub,now) and previously_accessed(sub,item))


def member_required(view):
    @wraps(view)
    def wrapped(*args,**kwargs):
        account = researcher()
        if not account: return redirect(url_for('submissions.login'))
        if not account.active or not account.verified: abort(403,description='Confirme a sua conta para consultar esta área.')
        try:return view(*args,**kwargs)
        except (IntegrityError,StaleDataError):
            db.session.rollback()
            abort(409,description='Este pedido já foi registado ou alterado. Reabra a página.')
    return wrapped


def safe_commit():
    try: db.session.commit()
    except (IntegrityError,StaleDataError):
        db.session.rollback()
        abort(409,description='Este registo foi alterado. Reabra a página antes de repetir.')


def enrollment_for(account, item, resource, sub):
    """Serialize quota checks per account before creating a course enrolment."""
    from premium import entitled, audit
    from premium_features import progress_for
    from submission_models import Researcher
    if db.engine.dialect.name == 'sqlite':
        db.session.execute(db.update(Researcher).where(Researcher.id==account.id).values(name=Researcher.name))
    else:
        db.session.execute(db.select(Researcher.id).where(Researcher.id==account.id).with_for_update()).scalar_one()
    existing=db.session.get(PremiumEnrollment,(account.id,item.id))
    if existing:return existing
    if not entitled(sub):abort(403,description='Uma nova inscrição exige uma subscrição válida.')
    limit=sub.plan_snapshot.get('course_limit')
    used=PremiumEnrollment.query.filter(PremiumEnrollment.owner_id==account.id,
        PremiumEnrollment.enrolled_at>=sub.starts_at,PremiumEnrollment.enrolled_at<sub.ends_at).count()
    if limit is not None and used>=limit:abort(403,description='Atingiu o limite de inscrições deste período.')
    days=resource.metadata_fields.get('completion_days')
    row=PremiumEnrollment(owner_id=account.id,content_id=item.id,
        deadline=utcnow()+timedelta(days=days) if type(days) is int and 1<=days<=3650 else None)
    db.session.add(row);progress_for(account,item)
    audit('course.enroll',item,{'owner_id':account.id,'deadline':row.deadline.isoformat() if row.deadline else None})
    notify(account.id,'learning','Inscrição confirmada',item.title,f'enrollment:{account.id}:{item.id}')
    return row


def process_membership_notices(limit=100, now=None):
    """Bounded, restart-safe lifecycle notices. HTTP requests never run this job."""
    from governance_models import StaffNotice
    now=now or utcnow();count=0
    phases=[('reminder',PremiumSubscription.ends_at>now,PremiumSubscription.ends_at<=now+GRACE,
             'Renovação próxima','O período pago termina dentro de três dias. Consulte a subscrição para regularizar a renovação.'),
            ('grace',PremiumSubscription.ends_at<=now,PremiumSubscription.ends_at>now-GRACE,
             'Período de tolerância','A subscrição venceu. Durante três dias pode continuar materiais anteriores; novas inscrições exigem pagamento.'),
            ('expired',PremiumSubscription.ends_at<=now-GRACE,PremiumSubscription.ends_at<=now-GRACE,
             'Tolerância terminada','O período de tolerância terminou. Os conteúdos exclusivos estão restritos; o histórico e os certificados foram preservados.')]
    for phase,lower,upper,subject,body in phases:
        # Skip delivered records before applying the batch limit.
        candidates=PremiumSubscription.query.filter_by(source='billing',status='active').filter(lower,upper).order_by(PremiumSubscription.id)
        for sub in candidates.yield_per(100):
            key=f'lifecycle:{sub.id}:{sub.ends_at.isoformat()}:{phase}'
            source='premium:'+key+':researcher:'+str(sub.owner_id)
            if db.session.scalar(db.select(StaffNotice.id).where(StaffNotice.source_key==source)):continue
            notify(sub.owner_id,'payment',subject,body,key);count+=1
            if count>=limit:return count
    return count


def install_members(public, admin):
    @public.app_context_processor
    def member_context():
        from premium_commercial import TIERS, annual_saving
        return dict(premium_tiers=TIERS,premium_annual_saving=annual_saving,
                    premium_request_kinds=REQUEST_KINDS,premium_request_states=REQUEST_STATES)

    @public.get('/painel')
    @member_required
    def member_dashboard():
        from premium import subscription_for, subscription_label, entitled
        from billing_models import BillingAccount, BillingOrder
        account=reader();sub=subscription_for(account)
        historical=PremiumSubscription.query.filter_by(owner_id=account.id).first()
        # Historical members keep access to their records after expiry; no free tier is created.
        if not historical:
            return render_template('premium/member_unavailable.html'),403
        courses=PremiumContent.query.join(PremiumProgress,PremiumProgress.content_id==PremiumContent.id).filter(
            PremiumProgress.owner_id==account.id,PremiumContent.published.is_(True),visible_clause()).order_by(
            PremiumProgress.updated_at.desc()).limit(6).all()
        certificates=PremiumCertificate.query.filter_by(owner_id=account.id).order_by(PremiumCertificate.issued_at.desc()).limit(6).all()
        requests=PremiumServiceRequest.query.filter_by(owner_id=account.id).order_by(PremiumServiceRequest.created_at.desc()).limit(6).all()
        payments=BillingOrder.query.filter_by(owner_id=account.id).order_by(BillingOrder.created_at.desc()).limit(5).all()
        agreement=db.session.get(BillingAccount,(account.id,True)) if historical.source=='billing' else None
        state='Acesso suspenso para verificação' if historical and not sub else ('Em tolerância' if in_grace(sub) else subscription_label(sub))
        from premium_features import completion
        progress={item.id:completion(item,account) for item in courses}
        return render_template('premium/dashboard.html',subscription=historical,state=state,has_access=entitled(sub),
            grace=in_grace(sub),grace_end=historical.ends_at+GRACE,courses=courses,progress=progress,
            certificates=certificates,service_requests=requests,payments=payments,agreement=agreement)

    @public.post('/cursos/<int:ident>/inscricao')
    @member_required
    @limiter.limit('20 per hour')
    def enroll_course(ident):
        validate_csrf()
        from premium import subscription_for, entitled, audit
        from premium_features import progress_for
        from premium_resources import require_access
        account=reader();item=db.get_or_404(PremiumContent,ident)
        resource=require_access(item,allow_grace=False)
        if resource.resource_type!='course':abort(400)
        sub=subscription_for(account)
        if not entitled(sub):abort(403,description='Uma nova inscrição exige uma subscrição válida.')
        enrollment_for(account,item,resource,sub)
        safe_commit()
        return redirect(url_for('premium.content',ident=ident))

    @public.route('/pedidos',methods=['GET','POST'])
    @member_required
    @limiter.limit('20 per hour',methods=['POST'])
    def service_requests():
        from billing_models import BillingOrder, BillingJournal
        from premium import audit
        from premium_resources import integer
        from request_values import pagination_page
        account=reader();error=None
        if request.method=='POST':
            validate_csrf()
            try:
                kind=request.form.get('kind','');reason=request.form.get('reason','').strip()
                if kind not in REQUEST_KINDS or not 10<=len(reason)<=2000:
                    raise ValueError('Escolha o tipo de pedido e apresente um motivo entre 10 e 2000 caracteres.')
                content_id=None;order_id=None
                if kind=='refund':
                    order_id=request.form.get('order_id','')
                    order=BillingOrder.query.filter_by(id=order_id,owner_id=account.id).first_or_404()
                    receipt=BillingJournal.query.filter_by(order_id=order.id,kind='receipt').first()
                    if not receipt or order.refund_minor>=order.amount_minor:
                        raise ValueError('O pedido exige um pagamento confirmado com valor por reembolsar.')
                if kind in {'extension','reactivation'}:
                    content_id=integer(request.form.get('content_id'))
                    if not db.session.get(PremiumEnrollment,(account.id,content_id)):
                        raise ValueError('Escolha um curso em que esteja inscrito.')
                duplicate=PremiumServiceRequest.query.filter_by(owner_id=account.id,kind=kind,order_id=order_id,content_id=content_id).filter(
                    PremiumServiceRequest.state.in_(['pending','review','approved'])).first()
                if duplicate:raise ValueError('Já existe um pedido em acompanhamento para esta situação.')
                row=PremiumServiceRequest(owner_id=account.id,kind=kind,content_id=content_id,order_id=order_id,reason=reason)
                db.session.add(row);db.session.flush()
                audit('request.create',row,{'kind':kind,'owner_id':account.id,'order_id':order_id,'content_id':content_id})
                notify(account.id,'learning' if content_id else 'payment','Pedido recebido',REQUEST_KINDS[kind],f'request:{row.id}:created')
                safe_commit();flash('Pedido registado para análise. Não foi efectuada uma devolução ou alteração automática.','success')
                return redirect(url_for('premium.service_requests'))
            except ValueError as exc:db.session.rollback();error=str(exc)
        rows=PremiumServiceRequest.query.filter_by(owner_id=account.id).order_by(PremiumServiceRequest.created_at.desc()).paginate(
            page=pagination_page(),per_page=20,error_out=False)
        orders=BillingOrder.query.filter_by(owner_id=account.id).filter(BillingOrder.refund_minor<BillingOrder.amount_minor,
            BillingOrder.id.in_(db.select(BillingJournal.order_id).where(BillingJournal.kind=='receipt'))).order_by(BillingOrder.created_at.desc()).limit(100).all()
        enrollments=db.session.execute(db.select(PremiumEnrollment,PremiumContent).join(PremiumContent,PremiumContent.id==PremiumEnrollment.content_id).where(
            PremiumEnrollment.owner_id==account.id)).all()
        return render_template('premium/requests.html',rows=rows,orders=orders,enrollments=enrollments,error=error),400 if error else 200

    @admin.route('/pedidos',methods=['GET'])
    @required('any')
    def member_requests():
        from request_values import pagination_page
        kinds=[]
        if can('finance'):kinds.append('refund')
        if can('content'):kinds.extend(['extension','reactivation','assistance'])
        if not kinds:abort(403)
        state=request.args.get('estado','')
        query=PremiumServiceRequest.query.filter(PremiumServiceRequest.kind.in_(kinds))
        if state:
            if state not in REQUEST_STATES:abort(400)
            query=query.filter_by(state=state)
        rows=query.order_by(PremiumServiceRequest.created_at.desc()).paginate(page=pagination_page(),per_page=20,error_out=False)
        return render_template('admin/premium_requests.html',rows=rows,state=state)

    @admin.post('/pedidos/<int:ident>')
    @required('any')
    @limiter.limit('60 per hour')
    def decide_request(ident):
        validate_csrf()
        from premium import audit,check_version
        from billing_models import BillingOrder, BillingJournal
        row=db.get_or_404(PremiumServiceRequest,ident)
        if not can('finance' if row.kind=='refund' else 'content'):abort(403)
        check_version(row)
        decision=request.form.get('decision','').strip();state=request.form.get('state','')
        transitions={'pending':{'review','approved','rejected'},'review':{'approved','rejected'},'approved':{'fulfilled'}}
        if state not in transitions.get(row.state,set()) or not 10<=len(decision)<=2000:
            abort(400,description='Indique uma decisão fundamentada e uma transição válida.')
        try:
            if state=='approved' and row.kind=='refund':
                from decimal import Decimal, InvalidOperation
                try:
                    raw_amount=request.form.get('amount','')
                    if len(raw_amount)>32:raise ValueError()
                    amount=Decimal(raw_amount)
                    if not amount.is_finite() or amount<=0 or amount!=amount.quantize(Decimal('.01')):raise ValueError()
                    amount_minor=int(amount*100)
                except (InvalidOperation,ValueError,OverflowError):raise ValueError('Indique um montante válido com até duas casas decimais.')
                order=db.get_or_404(BillingOrder,row.order_id)
                if amount_minor>order.amount_minor-order.refund_minor:raise ValueError('O montante excede o valor por reembolsar.')
                row.amount_minor=amount_minor
            if state=='fulfilled' and row.kind=='refund':
                # A decision does not fabricate provider confirmation or financial entries.
                refunded=db.session.scalar(db.select(db.func.sum(BillingJournal.amount_minor)).where(
                    BillingJournal.order_id==row.order_id,BillingJournal.kind=='refund',BillingJournal.created_at>=row.created_at)) or 0
                if not row.amount_minor or refunded<row.amount_minor:
                    raise ValueError('Aguarde a confirmação financeira do fornecedor antes de concluir o pedido.')
            if state=='approved' and row.kind in {'extension','reactivation'}:
                until=parse_local(request.form.get('extension_until',''))
                enrollment=db.session.get(PremiumEnrollment,(row.owner_id,row.content_id))
                if not enrollment or until<=utcnow() or enrollment.deadline and until<=enrollment.deadline:
                    raise ValueError('Indique um novo prazo futuro, posterior ao prazo actual.')
                row.extension_until=until;enrollment.deadline=until;enrollment.state='active'
            before=row.state
            row.state=state;row.decision=decision;row.decided_by=str(session.get('admin_id') or 'primary-environment');row.decided_at=utcnow()
            audit('request.decide',row,{'before':before,'after':state,'decision':decision,'amount_minor':row.amount_minor,
                'extension_until':row.extension_until.isoformat() if row.extension_until else None})
            notify(row.owner_id,'learning' if row.content_id else 'payment','Decisão do pedido',REQUEST_KINDS[row.kind]+': '+REQUEST_STATES[state]+'. '+decision,
                f'request:{row.id}:{row.version}:{state}')
            safe_commit();flash('Decisão registada. A aprovação de um reembolso não confirma a devolução.','success')
        except ValueError as exc:db.session.rollback();flash(str(exc),'error')
        return redirect(url_for('premium_admin.member_requests'))

    @public.get('/certificados/verificar/<token>')
    @limiter.limit('30 per minute')
    def verify_certificate(token):
        import re
        if not re.fullmatch('[a-f0-9]{32}',token):abort(404)
        certificate=db.get_or_404(PremiumCertificate,token)
        # Only course and issue date are public; learner names and PDFs remain private.
        return render_template('premium/certificate_verify.html',certificate=certificate)
