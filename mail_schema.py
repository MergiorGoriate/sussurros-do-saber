"""Additive mail upgrade, shared by Alembic and the existing startup compatibility path."""
import re
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy.schema import CreateColumn
from models import db
import submission_models


def upgrade_mail_schema(connection):
    if connection.dialect.name=='postgresql':
        connection.execute(sa.text('SELECT pg_advisory_xact_lock(1936028275)'))
    tables=set(sa.inspect(connection).get_table_names())
    mail=db.metadata.tables['editorial_notification']
    # Some historical migration fixtures intentionally contain no mail table.
    if 'editorial_notification' not in tables:
        return
    for name in ('newsletter_campaign','mail_delivery_policy','mail_delivery_attempt'):
        db.metadata.tables[name].create(connection,checkfirst=True)
    columns={c['name'] for c in sa.inspect(connection).get_columns(mail.name)}
    added='status' not in columns
    for name in ('campaign_id','subscriber_id','status','next_attempt_at','last_attempt_at','smtp_code','claim_token','last_error'):
        if name not in columns:
            original=mail.c[name]
            column=sa.Column(name,original.type,nullable=original.nullable,
                             server_default=sa.text("'pending'") if name=='status' else sa.text("''") if name=='last_error' else None)
            ddl=str(CreateColumn(column).compile(dialect=connection.dialect))
            connection.execute(sa.text('ALTER TABLE editorial_notification ADD COLUMN '+ddl))
    p=db.metadata.tables['mail_delivery_policy']
    settings=connection.execute(sa.select(p).where(p.c.id==1)).mappings().first()
    if settings is None:
        connection.execute(p.insert().values(id=1))
    if added or settings is None or not settings['legacy_reconciled']:
        connection.execute(sa.text("UPDATE editorial_notification SET status='accepted' WHERE sent_at IS NOT NULL"))
        connection.execute(sa.text("UPDATE editorial_notification SET status='uncertain', last_error='Tentativa anterior sem resultado confirmado; reconciliação obrigatória.' WHERE sent_at IS NULL AND attempts>0"))
        campaign=db.metadata.tables['newsletter_campaign'];attempt=db.metadata.tables['mail_delivery_attempt']
        subscriber=db.metadata.tables['subscriber']
        projection=[mail.c[n] for n in ('id','recipient','subject','sent_at','attempts')]
        projection.append(mail.c.last_error if 'last_error' in columns else sa.literal('').label('last_error'))
        rows=connection.execute(sa.select(*projection).order_by(mail.c.sent_at.is_(None),mail.c.id)).mappings().all()
        issues={};seen=set()
        for row in rows:
            match=re.fullmatch(r'Sussurros do Saber — Boletim (\d{4}-W\d{2})',row['subject'])
            if row['sent_at']:
                connection.execute(attempt.insert().values(notification_id=row['id'],number=max(1,row['attempts'] or 0),
                    started_at=row['sent_at'],finished_at=row['sent_at'],outcome='accepted',reason='Aceitação histórica preservada.'))
            if not match:continue
            issue=match.group(1)
            if issue not in issues:
                existing=connection.execute(sa.select(campaign.c.id).where(campaign.c.issue==issue)).scalar()
                issues[issue]=existing or connection.execute(campaign.insert().values(issue=issue,
                    fingerprint='legacy',subject=row['subject'],status='prepared',created_at=datetime.now(timezone.utc).replace(tzinfo=None))).inserted_primary_key[0]
            values={}
            key=(issue,row['recipient'])
            if key in seen:
                # Preserve every record and sent timestamp, but never send duplicate legacy pending rows.
                if not row['sent_at']:values.update(status='cancelled',last_error='Preparação legada duplicada; não reenviar.')
            else:
                values['campaign_id']=issues[issue];seen.add(key)
                if 'subscriber' in tables:
                    values['subscriber_id']=connection.execute(sa.select(subscriber.c.id).where(subscriber.c.email==row['recipient'])).scalar()
            if row.get('last_error')=='Boletim cancelado: inscrição inactiva.' and not row['sent_at']:
                values.update(status='cancelled')
            if values:connection.execute(mail.update().where(mail.c.id==row['id']).values(**values))
        connection.execute(p.update().where(p.c.id==1).values(legacy_reconciled=True))
    inspector=sa.inspect(connection)
    names={i['name'] for i in inspector.get_indexes(mail.name)}|{i['name'] for i in inspector.get_unique_constraints(mail.name)}
    for name,cols in [('uq_mail_campaign_recipient',['campaign_id','recipient']),('uq_mail_campaign_subscriber',['campaign_id','subscriber_id'])]:
        if name not in names:
            connection.execute(sa.text('CREATE UNIQUE INDEX '+name+' ON editorial_notification ('+','.join(cols)+')'))
    for index in mail.indexes:
        index.create(connection,checkfirst=True)
    if connection.dialect.name=='postgresql':
        fks={fk['name'] for fk in sa.inspect(connection).get_foreign_keys(mail.name)}
        for field,target in [('campaign_id','newsletter_campaign'),('subscriber_id','subscriber')]:
            name='fk_mail_'+field
            if target in sa.inspect(connection).get_table_names() and not any(
                fk['constrained_columns']==[field] for fk in sa.inspect(connection).get_foreign_keys(mail.name)):
                connection.execute(sa.text(f'ALTER TABLE editorial_notification ADD CONSTRAINT {name} FOREIGN KEY ({field}) REFERENCES {target}(id)'))
