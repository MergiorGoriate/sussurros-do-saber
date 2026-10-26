"""Persistent translation limits; reservations remain atomic and are never reset here."""
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from models import db, utcnow
from translation_models import TranslationLimitSetting, TranslationLimitChange, TranslationQuota
from dissemination_service import integer_setting
from dissemination_ai import GenerationError


def _setting(lock=False):
    statement = select(TranslationLimitSetting).where(TranslationLimitSetting.id == 1)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    row = db.session.execute(statement).scalar_one_or_none()
    if row is None and lock:
        try:
            with db.session.begin_nested():
                db.session.add(TranslationLimitSetting(id=1, version=0))
                db.session.flush()
        except IntegrityError:
            pass
        row = db.session.execute(statement).scalar_one()
    return row


def daily_limit(lock=False):
    row = _setting(lock)
    if row is not None and row.daily_units is not None:
        return row.daily_units
    return integer_setting('TRANSLATION_DAILY_UNITS', 100)


def quota_summary():
    row = _setting()
    error = ''
    try:
        limit = daily_limit()
    except GenerationError:
        limit = None
        error = 'O limite definido no servidor é inválido. Defina um limite no painel.'
    today = utcnow().date()
    quota = db.session.get(TranslationQuota, today)
    reserved = quota.reserved_units if quota else 0
    return dict(limit=limit, reserved=reserved, remaining=max(0, (limit or 0)-reserved),
                day=today, version=row.version if row else 0,
                source='panel' if row and row.daily_units is not None else 'environment', error=error)


def set_daily_limit(value, expected_version, actor_id, actor_name):
    raw = str(value).strip()
    if not raw.isascii() or not raw.isdigit() or len(raw) > 7 or not 1 <= int(raw) <= 1_000_000:
        raise GenerationError('Introduza um limite inteiro entre 1 e 1 000 000 unidades.')
    try:
        expected = int(expected_version)
    except (ValueError, TypeError):
        raise GenerationError('Actualize a página antes de alterar o limite.')
    row = _setting(lock=True)
    if expected != row.version:
        raise GenerationError('O limite foi alterado por outra sessão. Actualize a página.')
    try:
        previous = daily_limit()
    except GenerationError:
        previous = None
    changed = db.session.execute(update(TranslationLimitSetting).where(
        TranslationLimitSetting.id == 1, TranslationLimitSetting.version == expected
    ).values(daily_units=int(raw), version=expected+1, updated_at=utcnow()))
    if changed.rowcount != 1:
        raise GenerationError('O limite foi alterado por outra sessão. Actualize a página.')
    db.session.add(TranslationLimitChange(previous_units=previous, daily_units=int(raw),
        actor_id=actor_id, actor_name=(actor_name or 'Administrador principal')[:160]))
