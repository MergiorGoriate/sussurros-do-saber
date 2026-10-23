"""Payment attempts, agreements and append-only financial records; no card or PIN fields."""
import uuid
from sqlalchemy import event, inspect
from models import db, utcnow


class BillingAccount(db.Model):
    owner_id = db.Column(db.Integer, db.ForeignKey('researcher.id'), primary_key=True)
    live = db.Column(db.Boolean, primary_key=True, nullable=False)
    open_order_id = db.Column(db.String(32))
    stripe_subscription = db.Column(db.String(120), unique=True)
    stripe_root = db.Column(db.String(32))
    cancel_requested = db.Column(db.Boolean, nullable=False, default=False)
    cancel_confirmed = db.Column(db.Boolean, nullable=False, default=False)
    agreement_closed = db.Column(db.Boolean, nullable=False, default=False)
    suspended = db.Column(db.Boolean, nullable=False, default=False)
    risk_hold = db.Column(db.Boolean, nullable=False, default=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}


class BillingOrder(db.Model):
    __table_args__ = (
        db.UniqueConstraint('provider', 'provider_ref', name='billing_unique_provider_ref'),
        db.UniqueConstraint('provider', 'payment_ref', name='billing_unique_payment_ref'),
        db.CheckConstraint('amount_minor > 0 AND refund_minor >= 0 AND refund_minor <= amount_minor', name='billing_amounts'),
        db.CheckConstraint("state IN ('initiating','pending','paid','failed','expired','review','refunded')", name='billing_states'),
        db.CheckConstraint("method IN ('mpesa','emola','netshop','stripe')", name='billing_method'),
    )
    id = db.Column(db.String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    owner_id = db.Column(db.Integer, db.ForeignKey('researcher.id'), nullable=False, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('premium_plan.id'), nullable=False)
    snapshot = db.Column(db.JSON, nullable=False)
    record_kind = db.Column(db.String(10), nullable=False, default='payment')
    root_id = db.Column(db.String(32))
    amount_minor = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    method = db.Column(db.String(10), nullable=False)
    provider = db.Column(db.String(10), nullable=False)
    live = db.Column(db.Boolean, nullable=False)
    recurring = db.Column(db.Boolean, nullable=False, default=False)
    consent_version = db.Column(db.String(30), nullable=False, default='premium-payments-2026-10')
    state = db.Column(db.String(12), nullable=False, default='initiating', index=True)
    provider_ref = db.Column(db.String(120))
    payment_ref = db.Column(db.String(120))
    checkout_url = db.Column(db.Text)
    refund_minor = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    checked_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    owner = db.relationship('Researcher')
    __mapper_args__ = {'version_id_col': version}


class BillingGrant(db.Model):
    order_id = db.Column(db.String(32), db.ForeignKey('billing_order.id'), primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('researcher.id'), nullable=False, index=True)
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    revoked = db.Column(db.Boolean, nullable=False, default=False)
    __table_args__ = (db.CheckConstraint('ends_at > starts_at', name='billing_grant_dates'),)


class BillingJournal(db.Model):
    """One balanced debit/credit pair per row. Settlement means gateway clearing, not bank cash."""
    id = db.Column(db.Integer, primary_key=True)
    event_key = db.Column(db.String(180), nullable=False, unique=True)
    order_id = db.Column(db.String(32), db.ForeignKey('billing_order.id'), nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False)
    debit = db.Column(db.String(40), nullable=False)
    credit = db.Column(db.String(40), nullable=False)
    amount_minor = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False)
    live = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    __table_args__ = (
        db.CheckConstraint('amount_minor > 0 AND debit <> credit', name='billing_journal_pair'),
        db.CheckConstraint("kind IN ('receipt','refund')", name='billing_journal_kind'),
    )


class BillingEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_key = db.Column(db.String(180), nullable=False, unique=True)
    kind = db.Column(db.String(80), nullable=False)
    object_ref = db.Column(db.String(120), nullable=False)
    digest = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


@event.listens_for(BillingOrder, 'before_update')
def protect_quote(mapper, connection, target):
    state = inspect(target)
    for name in ('owner_id','plan_id','snapshot','record_kind','root_id','amount_minor','currency','method','provider','live','recurring','consent_version','created_at'):
        if state.attrs[name].history.has_changes():
            raise ValueError('As condições de um pedido financeiro não podem ser reescritas.')


class BillingRisk(db.Model):
    live = db.Column(db.Boolean, nullable=False)
    reference = db.Column(db.String(140), primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('researcher.id'), nullable=False, index=True)
    order_id = db.Column(db.String(32), db.ForeignKey('billing_order.id'), nullable=False)
    status = db.Column(db.String(40), nullable=False)
    resolved = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
