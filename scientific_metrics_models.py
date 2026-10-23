"""Scientific metrics refer only to Journal, never to portal Article."""
from models import db, utcnow


class ScientificMetricDay(db.Model):
    journal_id = db.Column(db.Integer, db.ForeignKey('journal.id', ondelete='CASCADE'), primary_key=True)
    day = db.Column(db.Date, primary_key=True)
    country = db.Column(db.String(2), primary_key=True, default='ZZ')
    views = db.Column(db.Integer, nullable=False, default=0)
    downloads = db.Column(db.Integer, nullable=False, default=0)


class ScientificMetricReceipt(db.Model):
    # Daily keyed digest; no raw IP, user agent, cookie or user identifier.
    digest = db.Column(db.String(64), primary_key=True)
    day = db.Column(db.Date, nullable=False, index=True)


class ScientificMetricStart(db.Model):
    journal_id = db.Column(db.Integer, db.ForeignKey('journal.id', ondelete='CASCADE'), primary_key=True)
    started_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class ScientificMetricSource(db.Model):
    __table_args__ = (db.UniqueConstraint('journal_id', 'source', name='scientific_metric_source_unique'),)
    id = db.Column(db.Integer, primary_key=True)
    journal_id = db.Column(db.Integer, db.ForeignKey('journal.id', ondelete='CASCADE'), nullable=False, index=True)
    source = db.Column(db.String(20), nullable=False)
    doi = db.Column(db.String(180), nullable=False)
    state = db.Column(db.String(30), nullable=False, default='unavailable')
    citations = db.Column(db.Integer)
    mentions = db.Column(db.Integer)
    attention_score = db.Column(db.Float)
    checked_at = db.Column(db.DateTime)
    measured_at = db.Column(db.DateTime)
    next_attempt = db.Column(db.DateTime, index=True)


class ScientificMetricProvider(db.Model):
    source = db.Column(db.String(20), primary_key=True)
    next_attempt = db.Column(db.DateTime, nullable=False, default=utcnow)
