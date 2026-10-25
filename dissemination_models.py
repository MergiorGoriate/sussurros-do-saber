"""Private dissemination workflow. Source articles are never modified."""
from models import db, utcnow


class DisseminationMaterial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source_kind = db.Column(db.String(12), nullable=False)
    source_id = db.Column(db.Integer, nullable=False)
    network = db.Column(db.String(20), nullable=False)
    kind = db.Column(db.String(24), nullable=False)
    status = db.Column(db.String(24), nullable=False, default='generating', index=True)
    version = db.Column(db.Integer, nullable=False, default=0)
    approved_version = db.Column(db.Integer)
    approved_by = db.Column(db.Integer)
    approved_at = db.Column(db.DateTime)
    created_by = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    token = db.Column(db.String(64), nullable=False, unique=True)
    publication_url = db.Column(db.String(1000), default='', nullable=False)
    error = db.Column(db.Text, default='', nullable=False)


class DisseminationVersion(db.Model):
    __table_args__ = (db.UniqueConstraint('material_id', 'number'),)
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('dissemination_material.id'), nullable=False, index=True)
    number = db.Column(db.Integer, nullable=False)
    source = db.Column(db.JSON, nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    report = db.Column(db.JSON, nullable=False)
    assets = db.Column(db.JSON, nullable=False, default=list)
    actor_id = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class DisseminationEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('dissemination_material.id'), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(40), nullable=False)
    state = db.Column(db.String(24), nullable=False)
    detail = db.Column(db.Text, nullable=False, default='')
    actor_id = db.Column(db.Integer)
    actor_name = db.Column(db.String(160), nullable=False, default='Trabalhador assíncrono')
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)


class DisseminationJob(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('dissemination_material.id'), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default='queued', index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)
    # Conservative administrative reservation, not a measured provider invoice.
    reserved_units = db.Column(db.Integer, nullable=False)
    mode = db.Column(db.String(16), nullable=False, default='generate')
    instruction = db.Column(db.Text, nullable=False, default='')


class DisseminationBudget(db.Model):
    day = db.Column(db.Date, primary_key=True)
    units = db.Column(db.Integer, nullable=False, default=0)
    jobs = db.Column(db.Integer, nullable=False, default=0)


class DisseminationClick(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    material_id = db.Column(db.Integer, db.ForeignKey('dissemination_material.id'), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
