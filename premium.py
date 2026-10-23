"""Premium phase one: no checkout, payment callbacks or automatic debits."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import load_only
from sqlalchemy.orm.exc import StaleDataError
from admin import superadmin_required, validate_csrf, protect_admin_responses
from extensions import limiter
from models import db, utcnow
from submission_models import Researcher
from submissions import researcher
from premium_models import PremiumPlan, PremiumSubscription, PremiumContent, PremiumAudit

premium_bp = Blueprint('premium', __name__, url_prefix='/premium')
premium_admin_bp = Blueprint('premium_admin', __name__, url_prefix='/admin/premium')
premium_admin_bp.after_request(protect_admin_responses)
KINDS = {'course': 'Curso especializado', 'series': 'Série educativa', 'event': 'Evento', 'interview': 'Entrevista'}
STATES = {'active': 'Activa', 'suspended': 'Suspensa', 'cancelled': 'Cancelada'}
INTERVALS = {'monthly': 'Mensal', 'annual': 'Anual'}


def subscription_for(account):
    if not account or not account.active or not account.verified:
        return None
    return PremiumSubscription.query.filter_by(owner_id=account.id).first()


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
    account = researcher()
    sub = subscription_for(account)
    kind = request.args.get('tipo', '')
    if kind and kind not in KINDS:
        abort(400)
    query = PremiumContent.query.options(load_only(PremiumContent.id, PremiumContent.title, PremiumContent.kind,
                                                   PremiumContent.summary)).filter_by(published=True)
    if kind:
        query = query.filter_by(kind=kind)
    page = request.args.get('page', '1')
    if not page.isascii() or not page.isdigit() or len(page) > 6 or int(page) < 1:
        abort(400)
    results = query.order_by(PremiumContent.id.desc()).paginate(page=int(page), per_page=12, error_out=False)
    return render_template('premium/library.html', results=results, kinds=KINDS, kind=kind,
                           has_access=entitled(sub))


@premium_bp.get('/conteudos/<int:ident>')
def content(ident):
    # Load no protected body before checking identity, verification and dates.
    item = PremiumContent.query.options(load_only(PremiumContent.id, PremiumContent.title, PremiumContent.kind,
                                                   PremiumContent.summary)).filter_by(id=ident, published=True).first_or_404()
    if not entitled(subscription_for(researcher())):
        return render_template('premium/locked.html', item=item), 403
    return render_template('premium/content.html', item=item, kinds=KINDS)


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
    db.session.add(PremiumAudit(actor=str(session.get('admin_id') or 'primary-environment'),
                               action=action, entity_id=record.id, detail=detail))


def commit():
    try:
        db.session.commit()
    except (StaleDataError, IntegrityError):
        db.session.rollback()
        abort(409, description='Alteração concorrente ou dados em conflito. Reabra a página.')


@premium_admin_bp.get('')
@premium_admin_bp.get('/')
@superadmin_required
def dashboard():
    from request_values import pagination_page
    subscriptions = PremiumSubscription.query.order_by(PremiumSubscription.id.desc()).paginate(
        page=pagination_page(), per_page=25, error_out=False)
    return render_template('admin/premium.html', plans=PremiumPlan.query.order_by(PremiumPlan.id).all(),
                           subscriptions=subscriptions, contents=PremiumContent.query.options(load_only(
                               PremiumContent.id, PremiumContent.title, PremiumContent.kind, PremiumContent.published))
                               .order_by(PremiumContent.id.desc()).paginate(page=pagination_page('content_page'), per_page=25, error_out=False),
                           audits=PremiumAudit.query.order_by(PremiumAudit.id.desc()).limit(30).all(),
                           kinds=KINDS, intervals=INTERVALS, subscription_label=subscription_label)


@premium_admin_bp.route('/planos/novo', methods=['GET', 'POST'], defaults={'ident': None})
@premium_admin_bp.route('/planos/<int:ident>', methods=['GET', 'POST'])
@superadmin_required
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
            values = dict(name=name, interval=interval, currency=currency, price_minor=int(amount * 100),
                          active=active, description=text_field('description', 2000, 0))
            before = {key: getattr(record, key) for key in values} if record else {}
            if record is None:
                record = PremiumPlan()
                db.session.add(record)
            for key, value in values.items():
                setattr(record, key, value)
            audit('plan.save', record, {'before': before, 'after': values})
            commit()
            flash('Plano guardado. As condições dos acessos já concedidos são preservadas.', 'success')
            return redirect(url_for('premium_admin.dashboard'))
        except (ValueError, InvalidOperation) as exc:
            error = str(exc) if isinstance(exc, ValueError) else 'Preço inválido.'
    return render_template('admin/premium_plan.html', item=record, error=error, intervals=INTERVALS), 400 if error else 200


@premium_admin_bp.route('/conteudos/novo', methods=['GET', 'POST'], defaults={'ident': None})
@premium_admin_bp.route('/conteudos/<int:ident>', methods=['GET', 'POST'])
@superadmin_required
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
                          summary=text_field('summary', 1000), body=text_field('body', 200000),
                          published=request.form.get('published') == 'on')
            if record is None:
                record = PremiumContent()
                db.session.add(record)
            for key, value in values.items():
                setattr(record, key, value)
            audit('content.save', record, {'title': record.title, 'published': record.published, 'version': record.version})
            commit()
            flash('Conteúdo Premium guardado.', 'success')
            return redirect(url_for('premium_admin.dashboard'))
        except ValueError as exc:
            error = str(exc)
    return render_template('admin/premium_content.html', item=record, kinds=KINDS, error=error), 400 if error else 200


def utc_date(name):
    try:
        value = datetime.strptime(request.form.get(name, ''), '%Y-%m-%dT%H:%M')
    except ValueError:
        raise ValueError('Indique datas válidas em UTC.') from None
    return value


@premium_admin_bp.route('/assinaturas/nova', methods=['GET', 'POST'])
@superadmin_required
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
                    ('name', 'interval', 'currency', 'price_minor')})
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
@superadmin_required
@limiter.limit('30 per hour', methods=['POST'])
def subscription(ident):
    record = db.get_or_404(PremiumSubscription, ident)
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
