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
    benefits = db.Column(db.JSON, nullable=False, default=list, server_default='[]')
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
    category = db.Column(db.String(80), nullable=False, default='', server_default='')
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


class PremiumResource(db.Model):
    """Additional metadata for the existing catalogue, without duplicating content."""
    content_id = db.Column(db.Integer, db.ForeignKey('premium_content.id', ondelete='CASCADE'), primary_key=True)
    resource_type = db.Column(db.String(20), nullable=False, default='document')
    metadata_fields = db.Column(db.JSON, nullable=False, default=dict)
    state = db.Column(db.String(16), nullable=False, default='draft', index=True)
    publish_at = db.Column(db.DateTime, index=True)
    plan_ids = db.Column(db.JSON, nullable=False, default=list)
    download_allowed = db.Column(db.Boolean, nullable=False, default=False)
    featured = db.Column(db.Boolean, nullable=False, default=False)
    certificate_enabled = db.Column(db.Boolean, nullable=False, default=False)
    notification_cursor = db.Column(db.Integer, nullable=False, default=0)
    notification_done = db.Column(db.Boolean, nullable=False, default=True)
    content = db.relationship('PremiumContent')


class PremiumFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content_id = db.Column(db.Integer, db.ForeignKey('premium_content.id', ondelete='CASCADE'), nullable=False, index=True)
    role = db.Column(db.String(12), nullable=False)
    name = db.Column(db.String(180), nullable=False)
    mime = db.Column(db.String(100), nullable=False)
    size = db.Column(db.Integer, nullable=False)
    digest = db.Column(db.String(64), nullable=False)
    payload = db.deferred(db.Column(db.LargeBinary, nullable=False))
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class PremiumLesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content_id = db.Column(db.Integer, db.ForeignKey('premium_content.id', ondelete='CASCADE'), nullable=False, index=True)
    module = db.Column(db.String(120), nullable=False, default='')
    title = db.Column(db.String(180), nullable=False)
    body = db.Column(db.Text, nullable=False, default='')
    position = db.Column(db.Integer, nullable=False, default=1)
    video_file_id = db.Column(db.Integer, db.ForeignKey('premium_file.id'))
    document_file_id = db.Column(db.Integer, db.ForeignKey('premium_file.id'))
    questions = db.Column(db.JSON, nullable=False, default=list)
    published = db.Column(db.Boolean, nullable=False, default=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}


class PremiumProgress(db.Model):
    owner_id = db.Column(db.Integer, db.ForeignKey('researcher.id'), primary_key=True)
    content_id = db.Column(db.Integer, db.ForeignKey('premium_content.id', ondelete='CASCADE'), primary_key=True)
    favourite = db.Column(db.Boolean, nullable=False, default=False)
    position = db.Column(db.Integer, nullable=False, default=1)
    bookmark = db.Column(db.String(500), nullable=False, default='')
    results = db.Column(db.JSON, nullable=False, default=dict)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow, index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}


class PremiumEvent(db.Model):
    content_id = db.Column(db.Integer, db.ForeignKey('premium_content.id', ondelete='CASCADE'), primary_key=True)
    starts_at = db.Column(db.DateTime, nullable=False)
    ends_at = db.Column(db.DateTime, nullable=False)
    mode = db.Column(db.String(12), nullable=False, default='virtual')
    capacity = db.Column(db.Integer, nullable=False, default=100)
    speakers = db.Column(db.String(1000), nullable=False, default='')
    venue = db.Column(db.String(500), nullable=False, default='')
    meeting_url = db.Column(db.String(1000), nullable=False, default='')
    version = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}
    __table_args__ = (db.CheckConstraint('ends_at > starts_at AND capacity > 0', name='premium_event_valid'),)


class PremiumRegistration(db.Model):
    content_id = db.Column(db.Integer, db.ForeignKey('premium_content.id', ondelete='CASCADE'), primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('researcher.id'), primary_key=True)
    state = db.Column(db.String(16), nullable=False, default='registered')
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    owner = db.relationship('Researcher')


class PremiumCollectionItem(db.Model):
    collection_id = db.Column(db.Integer, db.ForeignKey('premium_content.id', ondelete='CASCADE'), primary_key=True)
    content_id = db.Column(db.Integer, db.ForeignKey('premium_content.id', ondelete='CASCADE'), primary_key=True)
    position = db.Column(db.Integer, nullable=False)


class PremiumCertificate(db.Model):
    id = db.Column(db.String(32), primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('researcher.id'), nullable=False)
    content_id = db.Column(db.Integer, db.ForeignKey('premium_content.id', ondelete='CASCADE'), nullable=False)
    content_version = db.Column(db.Integer, nullable=False)
    snapshot = db.Column(db.JSON, nullable=False)
    issued_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    __table_args__ = (db.UniqueConstraint('owner_id','content_id','content_version', name='premium_certificate_once'),)


class PremiumSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    values = db.Column(db.JSON, nullable=False, default=dict)
    version = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': version}


class PremiumStaff(db.Model):
    admin_id = db.Column(db.Integer, db.ForeignKey('admin_user.id'), primary_key=True)
    permissions = db.Column(db.JSON, nullable=False, default=list)


class PremiumPlanTerms(db.Model):
    plan_id = db.Column(db.Integer, db.ForeignKey('premium_plan.id'), primary_key=True)
    renewal = db.Column(db.String(2000), nullable=False, default='')
    cancellation = db.Column(db.String(2000), nullable=False, default='')
    refund = db.Column(db.String(2000), nullable=False, default='')
    limitations = db.Column(db.String(2000), nullable=False, default='')


class PremiumCategory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    description = db.Column(db.String(500), nullable=False, default='')


class PremiumUsage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_key = db.Column(db.String(180), nullable=False, unique=True)
    content_id = db.Column(db.Integer, db.ForeignKey('premium_content.id', ondelete='CASCADE'), nullable=False, index=True)
    action = db.Column(db.String(30), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

