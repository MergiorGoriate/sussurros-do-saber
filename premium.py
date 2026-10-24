"""Premium catalogue and complimentary access; payments live in billing.py."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for, has_request_context
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import load_only
from sqlalchemy.orm.exc import StaleDataError
from admin import superadmin_required, validate_csrf, protect_admin_responses
from extensions import limiter
from models import db, utcnow
from submission_models import Researcher
from submissions import researcher
from premium_models import PremiumPlan, PremiumSubscription, PremiumContent, PremiumAudit
from premium_access import required as premium_required, can as premium_can

premium_bp = Blueprint('premium', __name__, url_prefix='/premium')
premium_admin_bp = Blueprint('premium_admin', __name__, url_prefix='/admin/premium')
premium_admin_bp.after_request(protect_admin_responses)
KINDS = {'course': 'Curso especializado', 'series': 'Série educativa', 'event': 'Evento', 'interview': 'Entrevista'}
STATES = {'active': 'Activa', 'suspended': 'Suspensa', 'cancelled': 'Cancelada'}
INTERVALS = {'monthly': 'Mensal', 'annual': 'Anual'}


def subscription_for(account):
    if not account or not account.active or not account.verified:
        return None
    subscription = PremiumSubscription.query.filter_by(owner_id=account.id).first()
    if subscription and subscription.source == 'billing':
        from billing_models import BillingAccount
        billing_account = db.session.get(BillingAccount, (account.id, True))
        if billing_account and (billing_account.suspended or billing_account.risk_hold):
            return None
    return subscription


def entitled(subscription, now=None):
    now = now or utcnow()
    return bool(subscription and subscription.status == 'active'
                and subscription.starts_at <= now < subscription.ends_at)


def subscription_label(subscription):
    if not subscription:
        return 'Sem acesso Premium'
    if subscription.status != 'active':
        return STATES[subscription.status]
    if subscription.ends_at <= utcnow():
        return 'Expirada'
    return 'Activa' if subscription.starts_at <= utcnow() else 'Por iniciar'


@premium_bp.after_request
def private_response(response):
    # Even the catalogue carries account state; shared caches must never reuse it.
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Vary'] = 'Cookie'
    if request.endpoint == 'premium.content':
        response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    return response


@premium_bp.get('')
@premium_bp.get('/')
def index():
    account = researcher()
    sub = subscription_for(account)
    return render_template('premium/index.html', plans=PremiumPlan.query.filter_by(active=True).order_by(PremiumPlan.price_minor).all(),
                           subscription=sub, has_access=entitled(sub), state=subscription_label(sub), intervals=INTERVALS)


@premium_bp.get('/biblioteca')
def library():
    from premium_resources import PremiumResource, visible_clause
    account = researcher()
    sub = subscription_for(account)
    kind = request.args.get('tipo', '')
    if kind and kind not in KINDS:
        abort(400)
    search = request.args.get('q', '').strip()
    category = request.args.get('categoria', '').strip()
    if len(search) > 120 or len(category) > 80:
        abort(400)
    categories = [value for (value,) in db.session.query(PremiumContent.category).filter(
        PremiumContent.published.is_(True), visible_clause(), PremiumContent.category != '').distinct().order_by(PremiumContent.category).all()]
    query = PremiumContent.query.options(load_only(PremiumContent.id, PremiumContent.title, PremiumContent.kind,
                                                   PremiumContent.summary, PremiumContent.category, PremiumContent.open_access_required)).filter_by(published=True).filter(visible_clause())
    if kind:
        query = query.filter_by(kind=kind).filter(or_(
            ~db.exists(db.select(PremiumResource.content_id).where(PremiumResource.content_id==PremiumContent.id)),
            PremiumContent.id.in_(db.select(PremiumResource.content_id).where(PremiumResource.resource_type==kind))))
    if search:
        author_matches=db.select(PremiumResource.content_id).where(PremiumResource.metadata_fields['author'].as_string().icontains(search,autoescape=True))
        query = query.filter(or_(PremiumContent.title.icontains(search, autoescape=True),
                                 PremiumContent.summary.icontains(search, autoescape=True),PremiumContent.id.in_(author_matches)))
    resource_type=request.args.get('recurso','')
    file_format=request.args.get('formato','')
    from premium_resources import TYPES, FORMATS
    from premium_models import PremiumFile
    if resource_type:
        if resource_type not in TYPES:abort(400)
        query=query.filter(PremiumContent.id.in_(db.select(PremiumResource.content_id).where(PremiumResource.resource_type==resource_type)))
    if file_format:
        if file_format not in FORMATS:abort(400)
        query=query.filter(PremiumContent.id.in_(db.select(PremiumFile.content_id).where(PremiumFile.name.iendswith('.'+file_format))))
    if category:
        query = query.filter_by(category=category)
    page = request.args.get('page', '1')
    if not page.isascii() or not page.isdigit() or len(page) > 6 or int(page) < 1:
        abort(400)
    featured=db.exists(db.select(PremiumResource.content_id).where(PremiumResource.content_id==PremiumContent.id,PremiumResource.featured.is_(True)))
    results = query.order_by(featured.desc(),PremiumContent.id.desc()).paginate(page=int(page), per_page=12, error_out=False)
    return render_template('premium/library.html', results=results, kinds=KINDS, kind=kind,
                           has_access=entitled(sub), search=search, category=category, categories=categories,
                           resource_type=resource_type,file_format=file_format,formats=FORMATS)


@premium_bp.get('/conteudos/<int:ident>')
def content(ident):
    from premium_resources import require_access, detail, record_usage
    from premium_models import (PremiumFile,PremiumLesson,PremiumProgress,PremiumCollectionItem,PremiumEvent,PremiumRegistration)
    # Load no protected body before checking identity, verification and dates.
    item = PremiumContent.query.options(load_only(PremiumContent.id, PremiumContent.title, PremiumContent.kind,
                                                   PremiumContent.summary, PremiumContent.category, PremiumContent.open_access_required)).filter_by(id=ident, published=True).first_or_404()
    if not item.open_access_required and not entitled(subscription_for(researcher())):
        return render_template('premium/locked.html', item=item), 403
    resource=require_access(item)
    account=researcher()
    if account:
        from premium_features import progress_for,completion
        progress=progress_for(account,item);progress.updated_at=utcnow()
        lessons,completed=completion(item,account)
    else:
        progress=None;completed=[]
        lessons=PremiumLesson.query.filter_by(content_id=ident,published=True).order_by(PremiumLesson.position,PremiumLesson.id).all()
    record_usage(item,'content_view');db.session.commit()
    collection=PremiumContent.query.join(PremiumCollectionItem,PremiumCollectionItem.content_id==PremiumContent.id).filter(
        PremiumCollectionItem.collection_id==ident,PremiumContent.published.is_(True)).order_by(PremiumCollectionItem.position).all()
    return render_template('premium/content.html', item=item, kinds=KINDS,resource=resource,
        files=PremiumFile.query.filter_by(content_id=ident).all(),lessons=lessons,completed=completed,progress=progress,
        collection=collection,event=db.session.get(PremiumEvent,ident),
        registration=db.session.get(PremiumRegistration,(ident,account.id)) if account else None)


def text_field(name, maximum, minimum=1):
    value = request.form.get(name, '').strip()
    if not minimum <= len(value) <= maximum:
        raise ValueError(f'O campo {name} deve ter entre {minimum} e {maximum} caracteres.')
    return value


def choice(name, choices):
    value = request.form.get(name, '')
    if value not in choices:
        raise ValueError(f'Valor inválido para {name}.')
    return value


def check_version(record):
    if request.form.get('version') != str(record.version):
        abort(409, description='Este registo foi alterado. Reabra a página antes de guardar.')


def audit(action, record, detail):
    try:
        db.session.flush()
    except (StaleDataError, IntegrityError):
        db.session.rollback()
        abort(409, description='Alteração concorrente. Reabra a página antes de guardar.')
    db.session.add(PremiumAudit(actor=str(session.get('admin_id') or 'primary-environment') if has_request_context() else 'premium-worker',
                               action=action, entity_id=record.id, detail=detail))


def commit():
    try:
        db.session.commit()
    except (StaleDataError, IntegrityError):
        db.session.rollback()
        abort(409, description='Alteração concorrente ou dados em conflito. Reabra a página.')


@premium_admin_bp.get('')
@premium_admin_bp.get('/')
@premium_required('any')
def dashboard():
    if not session.get('admin_superuser'):
        if premium_can('content'):return redirect(url_for('premium_admin.manage',section='catalogo'))
        if premium_can('events'):return redirect(url_for('premium_admin.manage',section='eventos'))
        if premium_can('finance'):return redirect(url_for('premium_finance.dashboard'))
        if premium_can('plans'):return redirect(url_for('premium_admin.manage',section='planos'))
        if premium_can('members'):return redirect(url_for('premium_admin.manage',section='membros'))
        return redirect(url_for('premium_admin.reports'))
    from request_values import pagination_page
    subscriptions = PremiumSubscription.query.order_by(PremiumSubscription.id.desc()).paginate(
        page=pagination_page(), per_page=25, error_out=False)
    return render_template('admin/premium.html', plans=PremiumPlan.query.order_by(PremiumPlan.id).all(),
                           subscriptions=subscriptions, contents=PremiumContent.query.options(load_only(
                               PremiumContent.id, PremiumContent.title, PremiumContent.kind, PremiumContent.category, PremiumContent.open_access_required, PremiumContent.published))
                               .order_by(PremiumContent.id.desc()).paginate(page=pagination_page('content_page'), per_page=25, error_out=False),
                           audits=PremiumAudit.query.order_by(PremiumAudit.id.desc()).limit(30).all(),
                           kinds=KINDS, intervals=INTERVALS, subscription_label=subscription_label)


@premium_admin_bp.route('/planos/novo', methods=['GET', 'POST'], defaults={'ident': None})
@premium_admin_bp.route('/planos/<int:ident>', methods=['GET', 'POST'])
@premium_required('plans')
@limiter.limit('60 per hour', methods=['POST'])
def plan(ident):
    record = db.get_or_404(PremiumPlan, ident) if ident else None
    error = None
    if request.method == 'POST':
        validate_csrf()
        if record:
            check_version(record)
        try:
            name = text_field('name', 100)
            interval = choice('interval', INTERVALS)
            currency = choice('currency', {'MZN', 'USD', 'EUR', 'ZAR'})
            raw = request.form.get('price', '')
            if len(raw) > 32:
                raise ValueError('Preço inválido.')
            # All supported currencies use two decimal places. Never use floats for money.
            amount = Decimal(raw)
            if not amount.is_finite() or amount < 0 or amount > Decimal('10000000') or amount != amount.quantize(Decimal('.01')):
                raise ValueError('Preço inválido; use até duas casas decimais.')
            active = request.form.get('active') == 'on'
            if active and amount <= 0:
                raise ValueError('Defina um preço positivo antes de apresentar o plano.')
            benefits = [line.strip() for line in request.form.get('benefits', '').splitlines() if line.strip()]
            if len(benefits) > 20 or any(len(line) > 180 for line in benefits):
                raise ValueError('Indique até 20 benefícios, com até 180 caracteres por linha.')
            if len(set(benefits)) != len(benefits):
                raise ValueError('Não repita benefícios.')
            values = dict(benefits=benefits, name=name, interval=interval, currency=currency, price_minor=int(amount * 100),
                          active=active, description=text_field('description', 2000, 0))
            before = {key: getattr(record, key) for key in values} if record else {}
            if record is None:
                record = PremiumPlan()
                db.session.add(record)
            for key, value in values.items():
                setattr(record, key, value)
            if 'renewal' in request.form:
                from premium_models import PremiumPlanTerms
                db.session.flush()
                contract=db.session.get(PremiumPlanTerms,record.id) or PremiumPlanTerms(plan_id=record.id)
                for field in ('renewal','cancellation','refund','limitations'):
                    value=request.form.get(field,'').strip()
                    if len(value)>2000:raise ValueError('Condição contratual demasiado extensa.')
                    setattr(contract,field,value)
                db.session.add(contract)
                # Contract-only edits also invalidate outstanding signed quotes.
                if ident:record.version+=1
            audit('plan.save', record, {'before': before, 'after': values})
            commit()
            flash('Plano guardado. As condições dos acessos já concedidos são preservadas.', 'success')
            return redirect(url_for('premium_admin.dashboard'))
        except (ValueError, InvalidOperation) as exc:
            db.session.rollback()
            record=db.session.get(PremiumPlan,ident) if ident else None
            error = str(exc) if isinstance(exc, ValueError) else 'Preço inválido.'
    return render_template('admin/premium_plan.html', item=record, error=error, intervals=INTERVALS), 400 if error else 200


@premium_admin_bp.route('/conteudos/novo', methods=['GET', 'POST'], defaults={'ident': None})
@premium_admin_bp.route('/conteudos/<int:ident>', methods=['GET', 'POST'])
@premium_required('content')
@limiter.limit('60 per hour', methods=['POST'])
def edit_content(ident):
    record = db.get_or_404(PremiumContent, ident) if ident else None
    error = None
    if request.method == 'POST':
        validate_csrf()
        if record:
            check_version(record)
        try:
            values = dict(title=text_field('title', 180), kind=choice('kind', KINDS),
                          summary=text_field('summary', 1000), category=text_field('category', 80, 0), body=text_field('body', 200000),
                          published=(request.form.get('resource_state')=='published' if 'resource_type' in request.form else request.form.get('published') == 'on'), open_access_required=request.form.get('open_access_required') == 'on')
            if request.form.get('resource_type') in {'course','series','event','interview'}:
                values['kind']=request.form['resource_type']
            if record is None:
                record = PremiumContent()
                db.session.add(record)
            for key, value in values.items():
                setattr(record, key, value)
            if ident and 'resource_type' in request.form:record.version+=1
            db.session.flush()
            from premium_resources import save_details
            save_details(record)
            audit('content.save', record, {'title': record.title, 'published': record.published, 'version': record.version})
            commit()
            flash('Conteúdo Premium guardado.', 'success')
            return redirect(url_for('premium_admin.dashboard'))
        except ValueError as exc:
            db.session.rollback()
            record=db.session.get(PremiumContent,ident) if ident else None
            error = str(exc)
    from premium_resources import detail, TYPES, STATES
    from premium_models import PremiumFile,PremiumEvent,PremiumCollectionItem,PremiumCategory
    collection_positions={r.content_id:r.position for r in PremiumCollectionItem.query.filter_by(collection_id=ident)} if ident else {}
    collection_choices=PremiumContent.query.options(load_only(PremiumContent.id,PremiumContent.title,PremiumContent.kind)).filter(PremiumContent.id!=ident).order_by(PremiumContent.id.desc()).limit(200).all()
    if collection_positions:
        existing={row.id for row in collection_choices}
        collection_choices.extend(PremiumContent.query.filter(PremiumContent.id.in_(set(collection_positions)-existing)).all())
    return render_template('admin/premium_content.html', item=record, kinds=KINDS, error=error,
        resource=detail(record) if record else None,resource_types=TYPES,resource_states=STATES,
        files=PremiumFile.query.filter_by(content_id=ident).all() if ident else [],
        event=db.session.get(PremiumEvent,ident) if ident else None,
        collection_ids=','.join(str(r.content_id) for r in PremiumCollectionItem.query.filter_by(collection_id=ident).order_by(PremiumCollectionItem.position)) if ident else '',
        collection_choices=collection_choices,collection_positions=collection_positions,
        available_plans=PremiumPlan.query.order_by(PremiumPlan.id).all(),categories=PremiumCategory.query.order_by(PremiumCategory.name).all()), 400 if error else 200


def utc_date(name):
    try:
        value = datetime.strptime(request.form.get(name, ''), '%Y-%m-%dT%H:%M')
    except ValueError:
        raise ValueError('Indique datas válidas em UTC.') from None
    return value


@premium_admin_bp.route('/assinaturas/nova', methods=['GET', 'POST'])
@premium_required('members')
@limiter.limit('30 per hour', methods=['POST'])
def grant():
    error = None
    if request.method == 'POST':
        validate_csrf()
        try:
            from request_values import database_id
            account = db.session.get(Researcher, database_id(request.form.get('owner_id')))
            plan_record = db.session.get(PremiumPlan, database_id(request.form.get('plan_id')))
            if not account or not account.active or not account.verified:
                raise ValueError('A conta deve estar activa e ter o e-mail confirmado.')
            if not plan_record or not plan_record.active:
                raise ValueError('Escolha um plano activo.')
            start, end = utc_date('starts_at'), utc_date('ends_at')
            if end <= start or end <= utcnow():
                raise ValueError('A validade deve terminar no futuro e depois do início.')
            reason = text_field('reason', 500, 10)
            if request.form.get('complimentary') != 'on':
                raise ValueError('Confirme que este acesso é uma oferta sem cobrança.')
            record = PremiumSubscription.query.filter_by(owner_id=account.id).first()
            if record:
                # Renewals/changes use the exact version displayed in a dedicated form.
                raise ValueError('Esta conta já tem um registo. Altere a assinatura existente.')
            record = PremiumSubscription(owner_id=account.id, plan_id=plan_record.id, starts_at=start, ends_at=end,
                reason=reason, source='complimentary', plan_snapshot={key: getattr(plan_record, key) for key in
                    ('name', 'interval', 'currency', 'price_minor', 'benefits')})
            db.session.add(record)
            audit('subscription.grant', record, {'owner_id': account.id, 'plan': record.plan_snapshot,
                'starts_at': start.isoformat(), 'ends_at': end.isoformat(), 'reason': reason, 'source': 'complimentary'})
            commit()
            flash('Acesso de oferta concedido, sem cobrança nem renovação automática.', 'success')
            return redirect(url_for('premium_admin.dashboard'))
        except ValueError as exc:
            error = str(exc)
    query = request.args.get('q', '').strip()[:254]
    accounts = Researcher.query.filter(Researcher.active.is_(True), Researcher.verified.is_(True),
                                      Researcher.email.contains(query, autoescape=True)).limit(20).all() if query else []
    return render_template('admin/premium_grant.html', plans=PremiumPlan.query.filter_by(active=True).all(),
                           accounts=accounts, query=query, error=error), 400 if error else 200


@premium_admin_bp.route('/assinaturas/<int:ident>', methods=['GET', 'POST'])
@premium_required('members')
@limiter.limit('30 per hour', methods=['POST'])
def subscription(ident):
    record = db.get_or_404(PremiumSubscription, ident)
    if record.source == 'billing':
        return redirect(url_for('premium_finance.dashboard'))
    error = None
    if request.method == 'POST':
        validate_csrf()
        check_version(record)
        try:
            status = choice('status', STATES)
            start, end = utc_date('starts_at'), utc_date('ends_at')
            if end <= start:
                raise ValueError('O fim deve ser posterior ao início.')
            reason = text_field('reason', 500, 10)
            before = {'status': record.status, 'starts_at': record.starts_at.isoformat(), 'ends_at': record.ends_at.isoformat()}
            record.status, record.starts_at, record.ends_at, record.reason = status, start, end, reason
            audit('subscription.change', record, {'before': before, 'after': {'status': status,
                  'starts_at': start.isoformat(), 'ends_at': end.isoformat()}, 'reason': reason})
            commit()
            flash('Assinatura actualizada. Suspensão e cancelamento retiram o acesso imediatamente.', 'success')
            return redirect(url_for('premium_admin.dashboard'))
        except ValueError as exc:
            error = str(exc)
    return render_template('admin/premium_subscription.html', item=record, states=STATES, error=error), 400 if error else 200


from premium_features import install_features
install_features(premium_bp, premium_admin_bp)

