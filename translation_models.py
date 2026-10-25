"""Translations are separate editorial artefacts; originals and PDFs are immutable here."""
from models import db, utcnow


class ContentTranslation(db.Model):
    __table_args__ = (db.UniqueConstraint('kind', 'source_id', 'language'),)
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(20), nullable=False)
    source_id = db.Column(db.Integer, nullable=False)
    original_language = db.Column(db.String(8), nullable=False, default='pt')
    language = db.Column(db.String(8), nullable=False, default='en')
    state = db.Column(db.String(24), nullable=False, default='pending', index=True)
    version = db.Column(db.Integer, nullable=False, default=0)
    published_version = db.Column(db.Integer)
    approved_version = db.Column(db.Integer)
    reviewer_id = db.Column(db.Integer)
    reviewer_name = db.Column(db.String(160), nullable=False, default='')
    reviewed_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    error = db.Column(db.Text, nullable=False, default='')


class TranslationVersion(db.Model):
    __table_args__ = (db.UniqueConstraint('translation_id', 'number'),)
    id = db.Column(db.Integer, primary_key=True)
    translation_id = db.Column(db.Integer, db.ForeignKey('content_translation.id'), nullable=False, index=True)
    number = db.Column(db.Integer, nullable=False)
    source_hash = db.Column(db.String(64), nullable=False)
    source = db.Column(db.JSON, nullable=False)
    content = db.Column(db.JSON, nullable=False)
    report = db.Column(db.JSON, nullable=False)
    actor_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class TranslationJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    translation_id = db.Column(db.Integer, db.ForeignKey('content_translation.id'), nullable=False, index=True)
    state = db.Column(db.String(20), nullable=False, default='queued', index=True)
    priority = db.Column(db.Integer, nullable=False, default=50)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)
    reserved_units = db.Column(db.Integer, nullable=False, default=1)
    mode = db.Column(db.String(16), nullable=False, default='generate')


class TranslationEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    translation_id = db.Column(db.Integer, db.ForeignKey('content_translation.id'), nullable=False, index=True)
    action = db.Column(db.String(30), nullable=False)
    state = db.Column(db.String(24), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    actor_id = db.Column(db.Integer)
    actor_name = db.Column(db.String(160), nullable=False, default='Sistema')
    detail = db.Column(db.Text, nullable=False, default='')
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class TranslationQuota(db.Model):
    day = db.Column(db.Date, primary_key=True)
    reserved_units = db.Column(db.Integer, nullable=False, default=0)


class TranslationWorker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lease = db.Column(db.String(64))
    expires_at = db.Column(db.DateTime)


class InterfaceTranslation(db.Model):
    """Editor-reviewed interface and institutional text catalogue."""
    key = db.Column(db.String(64), primary_key=True)
    source = db.Column(db.Text, nullable=False)
    english = db.Column(db.Text, nullable=False, default='')
    published = db.Column(db.Boolean, nullable=False, default=False)
    reviewer_id = db.Column(db.Integer)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    pending_batch_id = db.Column(db.Integer)


class InterfaceBatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    keys = db.Column(db.JSON, nullable=False)


# Mark changes in the same transaction as the original edit, preserving the published pointer.
from sqlalchemy import event, inspect, select
from models import Article, Journal


def original_updated(mapper,connection,obj):
    kind='article' if isinstance(obj,Article) else 'journal'
    fields=('title','summary','body','keywords','references') if kind=='article' else ('article_title','summary','keywords','description','guidelines','aims_scope')
    visibility='status' if kind=='article' else 'published'
    unpublished=(obj.status!='published') if kind=='article' else not obj.published
    if not any(inspect(obj).attrs[field].history.has_changes() for field in fields) and not (unpublished and inspect(obj).attrs[visibility].history.has_changes()):
        return
    rows=connection.execute(select(ContentTranslation.__table__).where(ContentTranslation.kind==kind,
        ContentTranslation.source_id==obj.id,ContentTranslation.state.in_(['approved','published']))).mappings()
    for row in rows:
        connection.execute(ContentTranslation.__table__.update().where(ContentTranslation.id==row['id']).values(state='outdated',approved_version=None))
        connection.execute(TranslationEvent.__table__.insert().values(translation_id=row['id'],action='source_updated',
            state='outdated',version=row['version'],actor_id=None,actor_name='Alteração do original',detail='O original foi alterado; a versão inglesa publicada foi preservada.',created_at=utcnow()))


event.listen(Article,'after_update',original_updated)
event.listen(Journal,'after_update',original_updated)
