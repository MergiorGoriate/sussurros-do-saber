"""Automation administration uses the existing admin authentication and CSRF."""
from datetime import timedelta

from flask import abort, flash, redirect, render_template, request, session, url_for
from admin import admin_bp, validate_csrf
from automation.config import REGISTRY, RESEARCH_TOPICS, SEO_PATHS, bounded_int, validate_settings
from automation.engine import enqueue
from automation.models import AutomationAlert, AutomationOperator, AutomationRun
from governance import audit, has_permission, require
from models import db, utcnow
from request_values import pagination_page


def access():
    if not (has_permission('automation.read') or has_permission('automation.manage')):
        abort(403)


def context(**kwargs):
    return dict(registry=REGISTRY, seo_paths=SEO_PATHS, research_topics=RESEARCH_TOPICS,
                can_manage=has_permission('automation.manage'), **kwargs)


@admin_bp.get('/automacao')
def automation_dashboard():
    access()
    operators = AutomationOperator.query.order_by(AutomationOperator.code).all()
    recent = AutomationRun.query.order_by(AutomationRun.id.desc()).limit(10).all()
    last_runs = {operator.code: AutomationRun.query.filter_by(operator_code=operator.code).order_by(
        AutomationRun.id.desc()).first() for operator in operators}
    active = AutomationAlert.query.filter_by(resolved_at=None)
    stats = dict(active=sum(operator.enabled for operator in operators),
                 inactive=sum(not operator.enabled for operator in operators),
                 successes=AutomationRun.query.filter_by(status='success').count(),
                 warnings=AutomationRun.query.filter_by(status='warning').count(),
                 failures=AutomationRun.query.filter_by(status='failed').count(),
                 queued=AutomationRun.query.filter_by(status='queued').count(),
                 running=AutomationRun.query.filter_by(status='running').count(),
                 alerts=active.count(), critical=active.filter_by(severity='CRITICAL').count())
    return render_template('admin/automation/dashboard.html', **context(operators=operators, recent=recent,
                           last_runs=last_runs, stats=stats))


@admin_bp.get('/automacao/execucoes')
def automation_runs():
    access()
    selected = request.args.get('operador', '')
    if selected and selected not in REGISTRY:
        abort(400)
    query = AutomationRun.query
    if selected:
        query = query.filter_by(operator_code=selected)
    page = query.order_by(AutomationRun.id.desc()).paginate(page=pagination_page(), per_page=50, error_out=False)
    return render_template('admin/automation/runs.html', **context(page=page, selected=selected))


@admin_bp.get('/automacao/execucoes/<int:ident>')
def automation_run_detail(ident):
    access()
    return render_template('admin/automation/detail.html', **context(run=db.get_or_404(AutomationRun, ident)))


@admin_bp.get('/automacao/alertas')
def automation_alerts():
    access()
    resolved = request.args.get('estado') == 'resolvidos'
    query = AutomationAlert.query.filter(AutomationAlert.resolved_at.isnot(None) if resolved else AutomationAlert.resolved_at.is_(None))
    page = query.order_by(AutomationAlert.last_seen.desc(), AutomationAlert.id.desc()).paginate(
        page=pagination_page(), per_page=50, error_out=False)
    return render_template('admin/automation/alerts.html', **context(page=page, resolved=resolved))


@admin_bp.post('/automacao/alertas/<int:ident>/resolver')
def automation_resolve(ident):
    require('automation.manage')
    validate_csrf()
    alert = db.get_or_404(AutomationAlert, ident)
    if alert.resolved_at is None:
        alert.resolved_at = utcnow()
        audit('automation.resolve', 'automation_alert', ident)
        db.session.commit()
    return redirect(url_for('admin.automation_alerts'), code=303)


@admin_bp.route('/automacao/operadores/<code>', methods=['GET', 'POST'])
def automation_operator(code):
    access()
    if code not in REGISTRY:
        abort(404)
    if request.method == 'POST':
        require('automation.manage')
        validate_csrf()
        operator = AutomationOperator.query.filter_by(code=code).with_for_update().first_or_404()
        try:
            raw = {key: request.form.getlist(key) if isinstance(value, list) else request.form.get(key, '')
                   for key, value in REGISTRY[code].settings.items()}
            settings = validate_settings(code, raw)
            interval = bounded_int(request.form.get('interval'), 15, 10080)
            retention = bounded_int(request.form.get('retention'), 7, 365)
        except ValueError as error:
            flash(str(error), 'error')
            return render_template('admin/automation/operator.html', **context(operator=operator)), 400
        enabled = request.form.get('enabled') == 'yes'
        if enabled and (not operator.enabled or operator.interval_minutes != interval or operator.next_run_at is None):
            operator.next_run_at = utcnow() + timedelta(minutes=interval)
        if not enabled:
            operator.next_run_at = None
            AutomationRun.query.filter_by(operator_code=code, status='queued').update(
                {'status': 'cancelled', 'finished_at': utcnow()}, synchronize_session=False)
        operator.enabled, operator.settings = enabled, settings
        operator.interval_minutes, operator.retention_days = interval, retention
        operator.notify = request.form.get('notify') == 'yes'
        audit('automation.configure', 'automation_operator', detail=code)
        db.session.commit()
        flash('Configuração guardada.', 'success')
        return redirect(url_for('admin.automation_operator', code=code))
    operator = db.get_or_404(AutomationOperator, code)
    return render_template('admin/automation/operator.html', **context(operator=operator))


@admin_bp.post('/automacao/operadores/<code>/executar')
def automation_execute(code):
    require('automation.manage')
    validate_csrf()
    if code not in REGISTRY:
        abort(404)
    run = enqueue(code, 'manual', session.get('admin_id'))
    if run is None:
        flash('Operador desactivado ou já com uma execução pendente.', 'warning')
        return redirect(url_for('admin.automation_dashboard'), code=303)
    audit('automation.enqueue', 'automation_run', run.id, code)
    db.session.commit()
    return redirect(url_for('admin.automation_run_detail', ident=run.id), code=303)
