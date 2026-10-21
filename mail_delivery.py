"""Coordinated delivery of the existing outbox, with durable reservations.

SMTP acceptance and a database commit cannot be atomic. Any abandoned claim or
uncertain DATA result is suspended, never automatically retried. Fixed UTC
windows conservatively count *every reserved attempt*, including connection
failures. No worker sleeps; the existing scheduled CLI resumes due work.
"""
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from email.message import EmailMessage
import os
import random
import re
import secrets
import smtplib
import ssl

from flask import has_request_context, session
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.exc import IntegrityError

from models import db, Subscriber, utcnow
from submission_models import (EditorialNotification as Mail, NewsletterCampaign as Campaign,
                               MailDeliveryAttempt as Attempt, MailDeliveryPolicy as Policy)

LABELS = {'pending':'Pendente', 'processing':'Em processamento', 'accepted':'Aceite pelo SMTP',
          'temporary':'Falha temporária', 'permanent':'Falha permanente', 'cancelled':'Cancelado',
          'suspended':'Suspenso', 'uncertain':'Resultado incerto', 'prepared':'Preparada',
          'approved':'Aprovada', 'scheduled':'Agendada', 'paused':'Em pausa', 'completed':'Concluída'}
LOCK_KEY = 1936949613
LEASE_SECONDS = 300


def audit(action, ident=None, detail='', entity='mail'):
    from governance_models import GovernanceAudit
    db.session.add(GovernanceAudit(
        actor_id=session.get('admin_id') if has_request_context() else None,
        actor_name=session.get('admin_username', 'Responsável') if has_request_context() else 'Trabalhador SMTP',
        action='mail.'+action, entity=entity, entity_id=ident, detail=detail[:1000]))


def policy(lock=False):
    row = db.session.get(Policy, 1)
    if row is None:
        try:
            # Savepoint allows simultaneous first requests without rolling back caller work.
            with db.session.begin_nested():
                db.session.add(Policy(id=1)); db.session.flush()
        except IntegrityError:
            pass
    if lock:
        if db.engine.dialect.name == 'sqlite':
            # A write acquires SQLite's writer lock, including after read-only SELECTs.
            db.session.execute(update(Policy).where(Policy.id == 1).values(id=1))
        return db.session.execute(select(Policy).where(Policy.id == 1).with_for_update()
                                  .execution_options(populate_existing=True)).scalar_one()
    return db.session.get(Policy, 1)


def usage(now=None):
    now = now or utcnow()
    hour = now.replace(minute=0, second=0, microsecond=0)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    def count(start):
        return db.session.scalar(select(func.count(Attempt.id)).where(
            Attempt.started_at >= start, Attempt.started_at < now+timedelta(microseconds=1))) or 0
    return count(hour), count(day)


def effective_limits(p):
    return min(p.hourly_limit, p.provider_hourly or p.hourly_limit), min(p.daily_limit, p.provider_daily or p.daily_limit)


def update_policy(form):
    p = policy(lock=True)
    values = {}
    for name, low, high in [('hourly_limit',1,100000),('daily_limit',1,1000000),
                            ('edition_limit',1,100000),('max_retries',0,10),('interval_seconds',0,86400)]:
        value = form.get(name, '')
        if not re.fullmatch(r'\d{1,7}', str(value)) or not low <= int(value) <= high:
            raise ValueError('Valor inválido para '+name+'.')
        values[name] = int(value)
    for name in ('provider_hourly','provider_daily'):
        value = form.get(name,'').strip()
        if value and (not re.fullmatch(r'\d{1,7}',value) or not 1 <= int(value) <= 1000000):
            raise ValueError('Quota externa inválida.')
        values[name] = int(value) if value else None
    source = form.get('provider_source','').strip()
    if len(source)>300 or any(ord(c)<32 for c in source):
        raise ValueError('Origem de verificação inválida.')
    verified = form.get('provider_verified_on','').strip()
    try:
        verified = date.fromisoformat(verified) if verified else None
    except ValueError as exc:
        raise ValueError('Data de verificação inválida.') from exc
    if verified and verified > utcnow().date():
        raise ValueError('A verificação não pode ter uma data futura.')
    if any(values[n] for n in ('provider_hourly','provider_daily')) and (not source or not verified):
        raise ValueError('Indique a origem e a data da verificação das quotas externas.')
    old = {name:getattr(p,name) for name in values}
    for name,value in values.items():setattr(p,name,value)
    p.provider_source,p.provider_verified_on = source,verified
    for campaign in Campaign.query.filter(Campaign.status.in_(['scheduled','approved'])).all():
        if Mail.query.filter_by(campaign_id=campaign.id).count()>p.edition_limit:
            campaign.status='paused'
            campaign.suspension_reason='Destinatários preparados excedem o novo limite por edição.'
            audit('campaign.paused',campaign.id,campaign.suspension_reason,'newsletter_campaign')
    if p.suspension_reason.startswith('Limite '):
        p.suspended_until,p.suspension_reason=None,''
    audit('limits.updated',1, 'Valores anteriores: '+str(old)+'; novos: '+str(values), 'mail_policy')
    db.session.commit()


def record_id(value):
    if not re.fullmatch(r'[1-9]\d{0,9}',str(value)) or int(value)>2147483647:
        raise ValueError('Identificador inválido.')
    return int(value)


def campaign_action(ident, action, form):
    p=policy(lock=True)  # Same gate as claims, so pause/cancel precedes subsequent starts.
    c = db.session.get(Campaign, ident)
    if c is None:raise ValueError('Campanha inexistente.')
    if action in ('approve','schedule','start') and Mail.query.filter_by(campaign_id=c.id).count()>p.edition_limit:
        raise ValueError('A campanha excede o limite actual de destinatários por edição. Reveja os limites antes de autorizar.')
    if action == 'approve':
        if c.status != 'prepared':raise ValueError('A campanha já não está em preparação.')
        if form.get('reviewed_campaign')!='on' or form.get('campaign_fingerprint')!=c.fingerprint:
            raise ValueError('Reveja e confirme o conteúdo guardado desta campanha.')
        c.status,c.approved_at = 'approved',utcnow()
    elif action in ('schedule','start'):
        if c.status not in ('approved','scheduled','paused') or not c.approved_at:
            raise ValueError('Aprovar a campanha antes de autorizar o envio.')
        try:
            when = datetime.fromisoformat(form.get('scheduled_at','')) if action=='schedule' else utcnow()
        except ValueError as exc:raise ValueError('Data de agendamento UTC inválida.') from exc
        if when.tzinfo is not None or (action=='schedule' and when < utcnow()):
            raise ValueError('Utilize uma data futura em UTC sem deslocamento.')
        c.status,c.scheduled_at = 'scheduled',when
        c.suspension_reason=''
    elif action == 'pause':
        if c.status not in ('scheduled','approved'):raise ValueError('Campanha não está activa.')
        c.status='paused'
        c.suspension_reason='Pausa administrativa da campanha.'
    elif action == 'cancel':
        if c.status=='completed':raise ValueError('Campanha concluída.')
        c.status='cancelled'
        Mail.query.filter(Mail.campaign_id==c.id,Mail.sent_at.is_(None),Mail.status.in_(['pending','temporary'])).update(
            {'status':'cancelled','last_error':'Campanha cancelada.'},synchronize_session='fetch')
    else:raise ValueError('Acção de campanha inválida.')
    audit('campaign.'+action,c.id, 'Edição '+c.issue+('; UTC '+str(c.scheduled_at) if c.scheduled_at else ''),'newsletter_campaign')
    db.session.commit()


def cancel_subscriber(ident):
    """Do not revive old pending campaign messages if a cancelled reader resubscribes."""
    Mail.query.filter(Mail.subscriber_id==ident,Mail.campaign_id.is_not(None),Mail.sent_at.is_(None),
        Mail.status.in_(['pending','temporary'])).update(
            {'status':'cancelled','last_error':'Boletim cancelado: inscrição inactiva.'},synchronize_session='fetch')


def reconcile(ident, action, evidence):
    policy(lock=True)
    row=db.session.get(Mail,ident)
    if not row or row.status not in ('uncertain','suspended') or row.sent_at:
        raise ValueError('Esta mensagem não admite reconciliação.')
    evidence=evidence.strip()
    if not 10 <= len(evidence) <= 500 or any(ord(c)<32 for c in evidence):
        raise ValueError('Registe uma referência de evidência do fornecedor entre 10 e 500 caracteres, sem segredos.')
    if action=='confirmed_accepted':
        row.status,row.sent_at,row.last_error='accepted',utcnow(),'Aceitação reconciliada; hora de registo, não de entrega.'
    elif action=='confirmed_not_accepted':
        if row.attempts >= 1+policy().max_retries:
            raise ValueError('Limite de tentativas esgotado; não é permitido novo envio.')
        row.status,row.next_attempt_at,row.last_error='temporary',utcnow(),'Não aceitação confirmada pelo responsável.'
    else:raise ValueError('Resultado de reconciliação inválido.')
    row.claim_token=None
    audit('reconciled.'+action,row.id,evidence)
    db.session.commit()


def retry(ident):
    p=policy(lock=True);row=db.session.get(Mail,ident)
    if not row or row.sent_at or row.status!='temporary' or row.attempts>=1+p.max_retries:
        raise ValueError('Só falhas temporárias conhecidas dentro do limite admitem reprocessamento.')
    # Keep backoff and quotas; this action cannot reset attempts or advance the due date.
    audit('retry.requested',row.id,'Mantidos o intervalo e o número de tentativas.');db.session.commit()


def dashboard(campaign_page=1,failure_page=1,selected_id=None):
    p=policy();now=utcnow();hours,days=usage(now);hlimit,dlimit=effective_limits(p)
    counts=dict(db.session.execute(select(Mail.status,func.count(Mail.id)).group_by(Mail.status)).all())
    campaigns=db.paginate(select(Campaign).order_by(Campaign.id.desc()),page=min(1000000,max(1,campaign_page)),per_page=10,error_out=False)
    failures=db.paginate(select(Mail).where(Mail.status.in_(['temporary','permanent','uncertain','suspended'])).order_by(Mail.id.desc()),page=min(1000000,max(1,failure_page)),per_page=25,error_out=False)
    if selected_id is not None and not 1<=selected_id<=2147483647:selected_id=None
    selected=db.session.get(Campaign,selected_id) if selected_id else None
    preview=Mail.query.filter_by(campaign_id=selected.id).order_by(Mail.id).first() if selected else None
    campaign_counts=dict(db.session.execute(select(Mail.status,func.count(Mail.id)).where(Mail.campaign_id==selected.id).group_by(Mail.status)).all()) if selected else {}
    return dict(policy=p,counts=counts,hour_count=hours,day_count=days,hour_limit=hlimit,day_limit=dlimit,
        hour_percent=min(100,round(100*hours/hlimit)),day_percent=min(100,round(100*days/dlimit)),
        worker_active=bool(p.worker_token and p.worker_lease_until and p.worker_lease_until>now),
        campaigns=campaigns,failures=failures,selected=selected,preview=preview,campaign_counts=campaign_counts,
        attempts=Attempt.query.order_by(Attempt.id.desc()).limit(30).all(),labels=LABELS,
        reason=('Pausa administrativa' if p.paused else p.suspension_reason if p.suspended_until and p.suspended_until>now else 'Disponível'),now=now)


@contextmanager
def worker_slot():
    """PostgreSQL session lock survives row commits; pooled connection is always unlocked.

    Lease is also kept for observability/recovery and for SQLite tests. Under
    PostgreSQL the session lock is authoritative, even after a long suspension.
    """
    conn=None;locked=False;token=secrets.token_hex(24)
    try:
        if db.engine.dialect.name=='postgresql':
            conn=db.engine.connect()
            locked=bool(conn.execute(text('SELECT pg_try_advisory_lock(:key)'),{'key':LOCK_KEY}).scalar())
            conn.commit()
            if not locked:
                yield None;return
        p=policy(lock=True);now=utcnow()
        if conn is None and p.worker_token and p.worker_lease_until and p.worker_lease_until>now:
            db.session.rollback();yield None;return
        # A new owner never repeats a message whose prior send may have reached SMTP.
        for row in Mail.query.filter_by(status='processing').all():
            row.status,row.last_error,row.claim_token='uncertain','Trabalhador interrompido; verificar aceitação no fornecedor.',None
            for a in Attempt.query.filter_by(notification_id=row.id,outcome='processing').all():
                a.outcome,a.finished_at,a.reason='uncertain',now,row.last_error
            audit('claim.abandoned',row.id,row.last_error)
        p.worker_token,p.worker_lease_until,p.worker_heartbeat_at=token,now+timedelta(seconds=LEASE_SECONDS),now
        db.session.commit()
        yield token
    finally:
        db.session.rollback()
        # Conditional cleanup must not clear a successor's lease.
        db.session.execute(update(Policy).where(Policy.id==1,Policy.worker_token==token).values(
            worker_token=None,worker_lease_until=None))
        db.session.commit()
        if conn is not None:
            try:
                if locked:conn.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':LOCK_KEY});conn.commit()
            except Exception:
                conn.invalidate()
            finally:conn.close()


def due_messages(now):
    from newsletter_service import smtp_ready
    campaigns=select(Campaign.id).where(or_(Campaign.status=='cancelled',
        db.and_(Campaign.status=='scheduled',Campaign.approved_at.is_not(None),Campaign.scheduled_at<=now)))
    query=Mail.query.filter(Mail.sent_at.is_(None),Mail.status.in_(['pending','temporary']),
        or_(Mail.next_attempt_at.is_(None),Mail.next_attempt_at<=now),
        or_(Mail.campaign_id.is_(None),Mail.campaign_id.in_(campaigns)))
    if not smtp_ready():
        query=query.filter(Mail.campaign_id.is_(None),~Mail.subject.like('Sussurros do Saber — Boletim %'))
    return query.order_by(Mail.id)


def reserve(token, now):
    from newsletter_service import is_newsletter, smtp_ready, CANCELLED
    p=policy(lock=True)
    if p.worker_token!=token:raise RuntimeError('Trabalhador perdeu a reserva de execução.')
    p.worker_heartbeat_at,p.worker_lease_until=now,now+timedelta(seconds=LEASE_SECONDS)
    if p.paused or (p.suspended_until and p.suspended_until>now):
        db.session.commit();return None
    h,d=usage(now);hl,dl=effective_limits(p)
    if h>=hl or d>=dl:
        until=now.replace(minute=0,second=0,microsecond=0)+timedelta(hours=1)
        if d>=dl:until=now.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)
        p.suspended_until,p.suspension_reason=until,'Limite diário UTC atingido.' if d>=dl else 'Limite horário UTC atingido.'
        db.session.commit();return None
    if p.last_started_at and now < p.last_started_at+timedelta(seconds=p.interval_seconds):
        db.session.commit();return None
    # Oldest due message first across all campaigns, with transactional mail in the same budget.
    rows=due_messages(now).limit(100)
    for row in rows:
        c=db.session.get(Campaign,row.campaign_id) if row.campaign_id else None
        if row.campaign_id or is_newsletter(row):
            if c is None:
                row.status,row.last_error='suspended','Boletim legado sem campanha; requer migração e revisão.'
                audit('legacy.suspended',row.id);continue
            if Mail.query.filter_by(campaign_id=c.id).count()>p.edition_limit:
                c.status='paused';c.suspension_reason='Destinatários preparados excedem o limite actual por edição.'
                audit('campaign.paused',c.id,c.suspension_reason,'newsletter_campaign');continue
            subscriber=db.session.get(Subscriber,row.subscriber_id) if row.subscriber_id else None
            if not subscriber or not subscriber.active or subscriber.email!=row.recipient:
                row.status,row.last_error='cancelled',CANCELLED;audit('recipient.cancelled',row.id);continue
            if c.status=='cancelled':
                row.status,row.last_error='cancelled','Campanha cancelada.';continue
            if not smtp_ready() or c.status!='scheduled' or not c.approved_at or not c.scheduled_at or c.scheduled_at>now:
                continue
        if row.attempts>=1+p.max_retries:
            row.status,row.last_error='permanent','Limite de tentativas esgotado.';continue
        row.attempts+=1;row.last_attempt_at=now;row.claim_token=token;row.status='processing'
        a=Attempt(notification_id=row.id,number=row.attempts,started_at=now)
        db.session.add(a);p.last_started_at=now;db.session.flush()
        result=(row.id,a.id)
        audit('attempt.started',row.id,'Tentativa '+str(row.attempts))
        db.session.commit();return result
    db.session.commit();return None


def classify(error, during_send):
    code=getattr(error,'smtp_code',None)
    raw=getattr(error,'smtp_error',b'')
    if isinstance(error,smtplib.SMTPRecipientsRefused):
        response=next(iter(error.recipients.values()),(None,b''));code,raw=response
    raw=raw.decode('ascii','ignore') if isinstance(raw,bytes) else str(raw)
    # Inspect but never persist raw SMTP text: providers can echo addresses or secrets.
    quota=bool(code in (421,452) or re.search(r'quota|rate.?limit|too many|limite.*envio',raw,re.I))
    if isinstance(error,smtplib.SMTPAuthenticationError):return 'suspended',code,False,'Autenticação SMTP recusada; verificar configuração.'
    if isinstance(error,(smtplib.SMTPHeloError,smtplib.SMTPSenderRefused)) and code and code>=500:
        return 'suspended',code,False,'Configuração ou remetente SMTP recusado; verificar fornecedor.'
    if quota:return 'temporary',code,True,'Fornecedor SMTP adiou o envio por limite ou indisponibilidade.'
    if code and 400<=code<500:return 'temporary',code,False,'SMTP recusou temporariamente a mensagem.'
    if code and 500<=code<600:return 'permanent',code,False,'SMTP recusou definitivamente a mensagem.'
    if during_send:return 'uncertain',code,False,'Aceitação SMTP desconhecida; reconciliação obrigatória.'
    return 'temporary',code,False,'Ligação SMTP indisponível antes do envio.'


def finish(ident,attempt_id,error=None,during_send=False,now=None):
    now=now or utcnow();p=policy(lock=True)
    row=db.session.get(Mail,ident);a=db.session.get(Attempt,attempt_id)
    if not error:
        row.status,row.sent_at,row.last_error,row.smtp_code='accepted',now,'',250
    else:
        state,code,quota,reason=classify(error,during_send)
        row.status,row.smtp_code,row.last_error=state,code,reason
        if state=='temporary':
            if row.attempts>=1+p.max_retries:
                row.status,row.last_error='permanent','Tentativas temporárias esgotadas.'
            else:
                row.next_attempt_at=now+timedelta(seconds=300*2**(row.attempts-1)+random.randint(0,60))
        if quota or state=='suspended':
            p.suspended_until=now+timedelta(minutes=15)
            p.suspension_reason=reason
        if state=='suspended':p.paused=True
    row.claim_token=None
    a.outcome,a.smtp_code,a.reason,a.finished_at=row.status,row.smtp_code,row.last_error,now
    audit('attempt.'+row.status,row.id,'Código SMTP '+str(row.smtp_code) if row.smtp_code else row.last_error)
    db.session.commit()


def transmit(ident,attempt_id,smtp_factory=None):
    from newsletter_service import unsubscribe_url
    row=db.session.get(Mail,ident)
    message=EmailMessage();message['From']=os.getenv('SMTP_FROM','')
    message['To'],message['Subject']=row.recipient,row.subject
    message['Message-ID']=f'<editorial-{row.id}@sussurrosdosaber.com>'
    subscriber=db.session.get(Subscriber,row.subscriber_id) if row.campaign_id else None
    message.set_content(row.body)
    if subscriber:
        message['List-Unsubscribe']='<'+unsubscribe_url(subscriber)+'>'
        message['List-Unsubscribe-Post']='List-Unsubscribe=One-Click'
        if row.html_body:message.add_alternative(row.html_body,subtype='html')
    use_ssl=os.getenv('SMTP_SSL','false').lower()=='true'
    use_tls=os.getenv('SMTP_TLS','true').lower()=='true'
    factory=smtp_factory or (smtplib.SMTP_SSL if use_ssl else smtplib.SMTP)
    smtp=None;during=False
    try:
        options={'timeout':15}
        context=ssl.create_default_context()
        if use_ssl:options['context']=context
        smtp=factory(os.environ['SMTP_HOST'],int(os.getenv('SMTP_PORT','465' if use_ssl else '587')),**options)
        if use_tls and not use_ssl:smtp.starttls(context=context)
        if os.getenv('SMTP_USERNAME'):smtp.login(os.environ['SMTP_USERNAME'],os.getenv('SMTP_PASSWORD',''))
        # Recheck eligibility after network setup; pause stops new claims, not this already reserved attempt.
        if subscriber:
            db.session.refresh(subscriber)
            if not subscriber.active or subscriber.email!=row.recipient:
                p=policy(lock=True);a=db.session.get(Attempt,attempt_id)
                row.status,row.last_error,row.claim_token='cancelled','Inscrição inactiva antes do envio.',None
                a.outcome,a.finished_at,a.reason='cancelled',utcnow(),row.last_error
                audit('recipient.cancelled',row.id);db.session.commit();return
        during=True
        refused=smtp.send_message(message)
        if refused:raise smtplib.SMTPRecipientsRefused(refused)
    except (OSError,smtplib.SMTPException,ValueError) as error:
        finish(ident,attempt_id,error,during)
    else:
        # Commit before QUIT. If commit fails, durable processing claim becomes uncertain on recovery.
        finish(ident,attempt_id)
    finally:
        if smtp:
            try:smtp.quit()
            except (OSError,smtplib.SMTPException):
                try:smtp.close()
                except (OSError,smtplib.SMTPException):pass


def deliver_batch(limit=50,smtp_factory=None):
    from submissions import email_valid
    if not os.getenv('SMTP_HOST') or not email_valid(os.getenv('SMTP_FROM','')):
        raise ValueError('Configure SMTP_HOST e SMTP_FROM; fila preservada.')
    if not any(os.getenv(k,default).lower()=='true' for k,default in [('SMTP_TLS','true'),('SMTP_SSL','false')]):
        raise ValueError('É obrigatório utilizar SMTP_TLS ou SMTP_SSL.')
    accepted=0
    with worker_slot() as token:
        if token is None:return 0
        for _ in range(limit):
            claim=reserve(token,utcnow())
            if claim is None:break
            transmit(*claim,smtp_factory=smtp_factory)
            if db.session.get(Mail,claim[0]).status=='accepted':accepted+=1
        # Completion is informational; suspended/uncertain work prevents a false completed status.
        for c in Campaign.query.filter_by(status='scheduled').all():
            outstanding=Mail.query.filter(Mail.campaign_id==c.id,Mail.status.notin_(['accepted','cancelled','permanent'])).count()
            if not outstanding:c.status='completed'
        db.session.commit()
    return accepted
