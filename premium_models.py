"""Additional learning products; Article and Journal deliberately have no paywall flag."""
from models import db, utcnow


class PremiumPlan(db.Model):
    __table_args__ = (
        db.CheckConstraint("interval IN ('monthly', 'annual')", name='premium_plan_interval'),
        db.CheckConstraint('price_minor >= 0', name='premium_plan_price'),
        db.CheckConstraint('NOT active OR price_minor > 0', name='premium_plan_published_price'),
    )
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    interval = db.Column(db.String(10), nullable=False)
    price_minor = db.Column(db.Integer, nullable=False, default=0)
    currency = db.Column(db.String(3), nullable=False, default='MZN')
    description = db.Column(db.Text, nullable=False, default='')
    active = db.Column(db.Boolean, nullable=False, default=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}


class PremiumSubscription(db.Model):
    __table_args__ = (
        db.CheckConstraint("status IN ('active', 'suspended', 'cancelled')", name='premium_subscription_status'),
        db.CheckConstraint('ends_at > starts_at', name='premium_subscription_dates'),
    )
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('researcher.id'), nullable=False, unique=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('premium_plan.id'), nullable=False)
    status = db.Column(db.String(12), nullable=False, default='active')
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    # Phase one grants are complimentary and never imply a settled payment.
    source = db.Column(db.String(20), nullable=False, default='complimentary')
    reason = db.Column(db.String(500), nullable=False)
    plan_snapshot = db.Column(db.JSON, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    owner = db.relationship('Researcher')
    plan = db.relationship('PremiumPlan')
    __mapper_args__ = {'version_id_col': version}


class PremiumContent(db.Model):
    __table_args__ = (db.CheckConstraint("kind IN ('course', 'series', 'event', 'interview')", name='premium_content_kind'),)
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    kind = db.Column(db.String(15), nullable=False)
    summary = db.Column(db.String(1000), nullable=False)
    body = db.Column(db.Text, nullable=False)
    published = db.Column(db.Boolean, nullable=False, default=False, index=True)
    open_access_required = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    version = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}


class PremiumAudit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    actor = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(40), nullable=False)
    entity_id = db.Column(db.Integer, nullable=False)
    detail = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
