"""Queue, execution lifecycle and bounded persistence for read-only reports."""
from datetime import timedelta
import hashlib
import os
import subprocess
import sys

import click
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from automation.config import REGISTRY, validate_settings
from automation.models import AutomationAlert, AutomationDiscovery, AutomationOperator, AutomationRun
from automation.operators import OPERATORS, report, finding
from governance_models import StaffNotice
from models import AdminUser, db, utcnow

RUN_TIMEOUT = 110
LEASE_SECONDS = 180


def seed_operators():
    for code, spec in REGISTRY.items():
        if db.session.get(AutomationOperator, code) is None:
            db.session.add(AutomationOperator(code=code, interval_minutes=spec.interval, settings=spec.settings))
    db.session.commit()


def enqueue(code, trigger, actor=None):
    operator = AutomationOperator.query.filter_by(code=code).with_for_update().populate_existing().first()
    if not operator or not operator.enabled:
        return None
    try:
        with db.session.begin_nested():
            run = AutomationRun(operator_code=code, trigger=trigger, requested_by=actor, version=REGISTRY[code].version)
            db.session.add(run)
            db.session.flush()
        return run
    except IntegrityError:
        return None


def queue_due(now):
    due = AutomationOperator.query.filter(
        AutomationOperator.enabled.is_(True), AutomationOperator.next_run_at <= now).all()
    for operator in due:
        code = operator.code
        count = AutomationOperator.query.filter(
            AutomationOperator.code == code, AutomationOperator.enabled.is_(True),
            AutomationOperator.next_run_at <= now).update({
                AutomationOperator.next_run_at: now + timedelta(minutes=operator.interval_minutes)
            }, synchronize_session=False)
        if count:
            enqueue(code, 'scheduled')
    db.session.commit()


def claim(now):
    candidates = db.session.query(AutomationRun.id).join(
        AutomationOperator, AutomationOperator.code == AutomationRun.operator_code
    ).filter(AutomationRun.status == 'queued', AutomationOperator.enabled.is_(True)).order_by(
        AutomationRun.queued_at, AutomationRun.id).limit(10).all()
    for (ident,) in candidates:
        count = AutomationRun.query.filter_by(id=ident, status='queued').update({
            AutomationRun.status: 'running', AutomationRun.started_at: now,
            AutomationRun.deadline_at: now + timedelta(seconds=LEASE_SECONDS),
        }, synchronize_session=False)
        db.session.commit()
        if count:
            return ident
    return None


def alert_for(operator, issue, now):
    if issue['severity'] not in {'CRITICAL', 'HIGH', 'MEDIUM'}:
        return False
    key = hashlib.sha256(f"{operator.code}|{issue['code']}|{issue['subject']}".encode()).hexdigest()
    alert = AutomationAlert.query.filter_by(fingerprint=key).first()
    if not alert:
        alert = AutomationAlert(operator_code=operator.code, fingerprint=key, severity=issue['severity'],
                                subject=issue['subject'], description=issue['description'],
                                recommendation=issue['recommendation'], first_seen=now, last_seen=now, occurrences=1)
        db.session.add(alert)
        db.session.flush()
    else:
        alert.resolved_at = None
        alert.last_seen = now
        alert.occurrences += 1
        alert.description = issue['description']
        alert.severity = issue['severity']
        alert.recommendation = issue['recommendation']
    if (operator.notify and issue['severity'] in {'CRITICAL', 'HIGH'}
            and (not alert.last_notified_at or alert.last_notified_at < now - timedelta(hours=6))):
        alert.last_notified_at = now
        return True
    return False


def complete(ident, result=None, error=''):
    db.session.expire_all()
    run = AutomationRun.query.filter_by(id=ident, status='running').with_for_update().first()
    if not run:
        db.session.rollback()
        return False
    operator = db.session.get(AutomationOperator, run.operator_code)
    now = utcnow()
    if error:
        result = report()
        finding(result, 'HIGH', 'run-failed', operator.code, error, 'Consultar o histórico e repetir após corrigir o ambiente.')
    run.status = 'failed' if error else (
        'warning' if any(i['severity'] in {'CRITICAL', 'HIGH', 'MEDIUM'} for i in result['findings']) else 'success')
    run.error, run.result, run.finished_at = error, result, now
    run.duration_ms = max(0, round((now - run.started_at).total_seconds() * 1000))
    if not error:
        if 'next_cursor' in result:
            operator.cursor = result['next_cursor']
        for record in result.get('records', []):
            if db.session.get(AutomationDiscovery, record['doi']) is None:
                db.session.add(AutomationDiscovery(doi=record['doi'], first_seen=now))
    notifications = sum(bool(alert_for(operator, issue, now)) for issue in result['findings'])
    if notifications:
        for (admin_id,) in db.session.query(AdminUser.id).filter_by(is_superadmin=True, active=True).all():
            db.session.add(StaffNotice(admin_id=admin_id, subject=f'Automação: {REGISTRY[operator.code].name}',
                                       body=f'{notifications} alerta(s) de gravidade alta ou crítica. Consulte a execução #{ident}.',
                                       resource_type='automation_run', resource_id=ident))
    db.session.commit()
    return True


def recover_expired(now):
    expired = db.session.query(AutomationRun.id).filter(
        AutomationRun.status == 'running', AutomationRun.deadline_at < now).limit(20).all()
    for (ident,) in expired:
        complete(ident, error='Execução interrompida ou prazo máximo excedido.')


def retention(now):
    for operator in AutomationOperator.query.all():
        cutoff = now - timedelta(days=operator.retention_days)
        ids = db.session.query(AutomationRun.id).filter(
            AutomationRun.operator_code == operator.code, AutomationRun.finished_at < cutoff,
            AutomationRun.status.in_(['success', 'warning', 'failed', 'cancelled'])).limit(200).all()
        if ids:
            AutomationRun.query.filter(AutomationRun.id.in_([i[0] for i in ids])).delete(synchronize_session=False)
        ids = db.session.query(AutomationAlert.id).filter(
            AutomationAlert.operator_code == operator.code, AutomationAlert.resolved_at < cutoff).limit(200).all()
        if ids:
            AutomationAlert.query.filter(AutomationAlert.id.in_([i[0] for i in ids])).delete(synchronize_session=False)
        if operator.code == 'research':
            ids = db.session.query(AutomationDiscovery.doi).filter(AutomationDiscovery.first_seen < cutoff).limit(200).all()
            if ids:
                AutomationDiscovery.query.filter(AutomationDiscovery.doi.in_([i[0] for i in ids])).delete(synchronize_session=False)
    db.session.commit()


def execute_claimed(ident):
    run = db.session.get(AutomationRun, ident)
    if not run or run.status != 'running':
        return False
    operator = db.session.get(AutomationOperator, run.operator_code)
    try:
        settings = validate_settings(operator.code, operator.settings)
        outcome = OPERATORS[operator.code](settings, operator.cursor or {})
        outcome['settings'] = settings
        db.session.rollback()
        return complete(ident, outcome)
    except Exception:
        db.session.rollback()
        return complete(ident, error='Falha durante a verificação. Consulte a configuração do operador.')


def install_cli(app):
    @app.cli.command('automation-execute')
    @click.argument('run_id', type=int)
    def execute_command(run_id):
        """Internal worker command for an already claimed record."""
        if os.getenv('SUSSURROS_AUTOMATION_WORKER') != 'true' or not execute_claimed(run_id):
            raise click.ClickException('Execução interna indisponível.')

    @app.cli.command('automation-tick')
    def tick():
        """Schedule due work and process one isolated, bounded execution."""
        if os.getenv('SUSSURROS_AUTOMATION_WORKER') != 'true':
            raise click.ClickException('Active SUSSURROS_AUTOMATION_WORKER no serviço de tarefas.')
        now = utcnow()
        try:
            recover_expired(now)
            queue_due(now)
            retention(now)
            ident = claim(now)
        except SQLAlchemyError:
            db.session.rollback()
            raise click.ClickException('Base de dados da automação indisponível.') from None
        if ident is None:
            click.echo('Automação: nenhuma execução pendente.')
            return
        db.session.remove()
        try:
            subprocess.run([sys.executable, '-m', 'flask', '--app', 'app', 'automation-execute', str(ident)],
                           timeout=RUN_TIMEOUT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            complete(ident, error='O processo de automação não confirmou o resultado.')
        except (subprocess.TimeoutExpired, OSError):
            complete(ident, error='O processo de automação excedeu o prazo ou não pôde iniciar.')
        finally:
            db.session.remove()
        run = db.session.get(AutomationRun, ident)
        if run is None or run.status == 'failed':
            raise click.ClickException(f'Execução {ident} falhada. Consulte o histórico.')
        click.echo(f'Automação: execução {ident} terminada. Consulte o histórico.')
