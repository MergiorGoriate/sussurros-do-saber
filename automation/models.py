"""Persistence restricted to automation settings, results and alerts."""
from models import db, utcnow


class AutomationOperator(db.Model):
    code = db.Column(db.String(32), primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    interval_minutes = db.Column(db.Integer, nullable=False)
    next_run_at = db.Column(db.DateTime, index=True)
    settings = db.Column(db.JSON, nullable=False, default=dict)
    cursor = db.Column(db.JSON, nullable=False, default=dict)
    notify = db.Column(db.Boolean, nullable=False, default=False)
    retention_days = db.Column(db.Integer, nullable=False, default=90)


class AutomationRun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    operator_code = db.Column(db.String(32), db.ForeignKey('automation_operator.code'), nullable=False, index=True)
    trigger = db.Column(db.String(12), nullable=False)
    requested_by = db.Column(db.Integer, db.ForeignKey('admin_user.id', ondelete='SET NULL'))
    status = db.Column(db.String(16), nullable=False, default='queued')
    queued_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    started_at = db.Column(db.DateTime)
    deadline_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)
    duration_ms = db.Column(db.Integer)
    version = db.Column(db.String(16), nullable=False)
    result = db.Column(db.JSON, nullable=False, default=dict)
    error = db.Column(db.String(240), nullable=False, default='')
    __table_args__ = (
        db.CheckConstraint("status IN ('queued','running','success','warning','failed','cancelled')", name='automation_run_status'),
        db.Index('ix_automation_history', 'operator_code', 'queued_at', 'id'),
        db.Index('uq_automation_active_run', 'operator_code', unique=True,
                 postgresql_where=db.text("status IN ('queued','running')"),
                 sqlite_where=db.text("status IN ('queued','running')")),
    )


class AutomationAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    operator_code = db.Column(db.String(32), db.ForeignKey('automation_operator.code'), nullable=False, index=True)
    fingerprint = db.Column(db.String(64), unique=True, nullable=False)
    severity = db.Column(db.String(12), nullable=False)
    description = db.Column(db.String(500), nullable=False)
    recommendation = db.Column(db.String(500), nullable=False, default='')
    subject = db.Column(db.String(160), nullable=False)
    first_seen = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_seen = db.Column(db.DateTime, nullable=False, default=utcnow)
    occurrences = db.Column(db.Integer, nullable=False, default=1)
    resolved_at = db.Column(db.DateTime, index=True)
    last_notified_at = db.Column(db.DateTime)


class AutomationDiscovery(db.Model):
    doi = db.Column(db.String(255), primary_key=True)
    first_seen = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
