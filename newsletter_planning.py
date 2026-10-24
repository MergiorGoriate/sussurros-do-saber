"""Editorial choices and weekly planning; all sends use the existing outbox."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import re

from sqlalchemy import or_
from models import Article, db, utcnow
from submission_models import NewsletterPlan, NewsletterCampaign

MAPUTO = ZoneInfo('Africa/Maputo')
WEEKDAYS = ('Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira',
            'Sexta-feira', 'Sábado', 'Domingo')


def plan():
    return db.session.get(NewsletterPlan, 1) or NewsletterPlan(
        id=1, selection_mode='automatic', article_ids=[], max_articles=5,
        automatic_enabled=False, weekday=0, send_time='09:00', last_result='')


def parse_article_ids(values):
    if len(values) > 20:
        raise ValueError('Seleccione no máximo 20 artigos.')
    ids = []
    for value in values:
        if not re.fullmatch(r'[1-9]\d{0,9}', str(value)) or int(value) > 2147483647:
            raise ValueError('Identificador de artigo inválido.')
        if int(value) in ids:
            raise ValueError('A selecção contém artigos repetidos.')
        ids.append(int(value))
    return ids


def selected_articles(ids, now=None):
    now = now or utcnow()
    ids = parse_article_ids(ids)
    articles = Article.public_card_query().filter(Article.id.in_(ids), or_(
        Article.published_at.is_(None), Article.published_at <= now)).all()
    by_id = {article.id: article for article in articles}
    if len(by_id) != len(ids):
        raise ValueError('Um artigo seleccionado já não está publicado. Reveja a selecção.')
    return [by_id[ident] for ident in ids]


def edition_for(settings, now=None):
    from newsletter_service import digest
    return digest(now, article_ids=settings.article_ids if settings.selection_mode == 'manual' else None,
                  max_articles=settings.max_articles)


def next_run(weekday, send_time, after):
    local = after.replace(tzinfo=timezone.utc).astimezone(MAPUTO)
    hour, minute = map(int, send_time.split(':'))
    candidate = (local + timedelta(days=(weekday-local.weekday()) % 7)).replace(
        hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=7)
    return candidate.astimezone(timezone.utc).replace(tzinfo=None)


def local_time(value):
    return value.replace(tzinfo=timezone.utc).astimezone(MAPUTO) if value else None


def schedule_time(value, now=None):
    try:
        when = datetime.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValueError('Indique uma data e hora válidas para o envio.') from exc
    if when.tzinfo is not None:
        raise ValueError('Introduza a hora local de Moçambique, sem deslocamento.')
    when = when.replace(tzinfo=MAPUTO).astimezone(timezone.utc).replace(tzinfo=None)
    if when <= (now or utcnow()):
        raise ValueError('O envio deve ser programado para uma data futura.')
    return when


def save_plan(form, now=None):
    from mail_delivery import policy, audit
    policy(lock=True)
    now = now or utcnow()
    settings = plan()
    mode = form.get('selection_mode', '')
    if mode not in ('manual', 'automatic'):
        raise ValueError('Escolha a selecção editorial ou automática.')
    ids = parse_article_ids(form.getlist('article_ids'))
    if mode == 'manual':
        if not ids:
            raise ValueError('Seleccione pelo menos um artigo.')
        selected_articles(ids, now)
    else:
        ids = []
    count, day, clock = form.get('max_articles', ''), form.get('weekday', ''), form.get('send_time', '')
    if not re.fullmatch(r'\d{1,2}', count) or not 1 <= int(count) <= 20:
        raise ValueError('O número de artigos deve estar entre 1 e 20.')
    if day not in tuple(str(i) for i in range(7)) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', clock):
        raise ValueError('Dia ou hora do envio semanal inválidos.')
    enabled = form.get('automatic_enabled') == 'on'
    if enabled and form.get('confirm_automation') != 'on':
        raise ValueError('Confirme a autorização para preparar e enviar automaticamente.')
    changed = settings.weekday != int(day) or settings.send_time != clock
    settings.selection_mode, settings.article_ids, settings.max_articles = mode, ids, int(count)
    settings.weekday, settings.send_time = int(day), clock
    if enabled and (not settings.automatic_enabled or changed or not settings.next_run_at or settings.next_run_at <= now):
        settings.next_run_at = next_run(settings.weekday, clock, now)
    elif not enabled:
        settings.next_run_at = None
    settings.automatic_enabled = enabled
    settings.last_result = ''
    db.session.add(settings)
    audit('plan.updated', 1, f'Selecção: {mode}; artigos: {ids}; envio automático: {enabled}; '
          f'dia: {day}; hora Africa/Maputo: {clock}.', 'newsletter_plan')
    db.session.commit()
    return settings


def prepare_plan(expected_hash, delivery_mode='review', scheduled_at='', now=None):
    """One transaction freezes content, approval and the optional sending date."""
    from newsletter_service import queue_digest
    from mail_delivery import policy, audit
    if delivery_mode not in ('review', 'now', 'schedule'):
        raise ValueError('Modo de envio inválido.')
    now = now or utcnow()
    when = schedule_time(scheduled_at, now) if delivery_mode == 'schedule' else now
    delivery_policy = policy(lock=True)
    settings = plan()
    edition = edition_for(settings, now)
    if not edition['articles']:
        raise ValueError('Não há artigos para preparar nesta edição.')
    count = queue_digest(limit=delivery_policy.edition_limit, expected_hash=expected_hash, now=now,
        article_ids=settings.article_ids if settings.selection_mode == 'manual' else None,
        max_articles=settings.max_articles, commit=False)
    campaign = NewsletterCampaign.query.filter_by(issue=edition['issue']).first()
    if delivery_mode != 'review':
        if not campaign or campaign.status != 'prepared':
            raise ValueError('A edição já foi autorizada ou cancelada. Consulte o histórico de campanhas.')
        campaign.status, campaign.approved_at, campaign.scheduled_at = 'scheduled', now, when
        audit('campaign.authorised', campaign.id, 'Conteúdo revisto no painel; envio UTC '+str(when), 'newsletter_campaign')
    db.session.commit()
    return count


def run_due_plan(now=None):
    """Called by the existing periodic worker, never by a public page request."""
    from newsletter_service import smtp_ready, queue_digest
    from mail_delivery import policy, audit
    now = now or utcnow()
    delivery_policy = policy(lock=True)
    # Read after acquiring the shared policy gate; concurrent workers cannot duplicate a slot.
    settings = db.session.get(NewsletterPlan, 1, populate_existing=True)
    if (not settings or not settings.automatic_enabled or not settings.next_run_at
            or settings.next_run_at > now or delivery_policy.paused or not smtp_ready()):
        db.session.commit()
        return 0
    slot = settings.next_run_at
    # A delayed worker uses the latest scheduled week, without sending a backlog of editions.
    while slot + timedelta(days=7) <= now:
        slot += timedelta(days=7)
    try:
        with db.session.begin_nested():
            edition = edition_for(settings, slot)
            count = queue_digest(limit=delivery_policy.edition_limit, now=slot,
                article_ids=settings.article_ids if settings.selection_mode == 'manual' else None,
                max_articles=settings.max_articles, commit=False)
            db.session.flush()
    except ValueError as error:
        settings.automatic_enabled, settings.next_run_at = False, None
        settings.last_result = ('Automatização suspensa: '+str(error))[:300]
        audit('plan.suspended', 1, str(error), 'newsletter_plan')
        db.session.commit()
        return 0
    campaign = NewsletterCampaign.query.filter_by(issue=edition['issue']).first()
    if campaign and campaign.status == 'prepared' and campaign.fingerprint == edition['fingerprint']:
        campaign.status, campaign.approved_at, campaign.scheduled_at = 'scheduled', now, now
        audit('campaign.automated', campaign.id, 'Autorização semanal guardada pelo administrador.', 'newsletter_campaign')
    settings.last_run_at = now
    settings.last_result = (f'{count} mensagens preparadas para a edição {edition["issue"]}.'
                            if edition['articles'] else 'Sem artigos nesta edição; nenhum boletim preparado.')
    settings.next_run_at = next_run(settings.weekday, settings.send_time, now)
    audit('plan.executed', 1, f'Edição {edition["issue"]}; {count} mensagens preparadas.', 'newsletter_plan')
    db.session.commit()
    return count
