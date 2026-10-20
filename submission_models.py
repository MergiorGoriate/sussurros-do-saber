"""Private editorial records. Existing public authors and administrators remain separate."""
from models import db, utcnow

class Researcher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(300), nullable=False)
    verified = db.Column(db.Boolean, default=False, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    token_nonce = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

class SubmissionSetting(db.Model):
    journal_id = db.Column(db.Integer, db.ForeignKey('journal.id'), primary_key=True)
    enabled = db.Column(db.Boolean, default=False, nullable=False)
    article_types = db.Column(db.Text, default='', nullable=False)
    main_formats = db.Column(db.String(100), default='docx,pdf', nullable=False)
    editorial_email = db.Column(db.String(254), default='', nullable=False)
    journal = db.relationship('Journal')

class Manuscript(db.Model):
    removed_at = db.Column(db.DateTime, index=True)
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('researcher.id'), nullable=False, index=True)
    journal_id = db.Column(db.Integer, db.ForeignKey('journal.id'), nullable=False, index=True)
    code = db.Column(db.String(40), unique=True)
    status = db.Column(db.String(40), default='draft', nullable=False, index=True)
    article_type = db.Column(db.String(180), default='', nullable=False)
    field = db.Column(db.String(140), default='', nullable=False)
    language = db.Column(db.String(80), default='', nullable=False)
    title = db.Column(db.String(300), default='', nullable=False)
    summary = db.Column(db.Text, default='', nullable=False)
    keywords = db.Column(db.Text, default='', nullable=False)
    abstract = db.Column(db.Text, default='', nullable=False)
    abstract_keywords = db.Column(db.Text, default='', nullable=False)
    editor_comments = db.Column(db.Text, default='', nullable=False)
    scientific_details = db.Column(db.JSON, default=dict, nullable=False)
    declarations = db.Column(db.JSON, default=dict, nullable=False)
    current_version = db.Column(db.Integer, default=1, nullable=False)
    submitted_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    editor_id = db.Column(db.Integer, db.ForeignKey('admin_user.id'))
    publication_id = db.Column(db.Integer, db.ForeignKey('journal.id'), unique=True)
    owner = db.relationship('Researcher')
    journal = db.relationship('Journal', foreign_keys=[journal_id])
    publication = db.relationship('Journal', foreign_keys=[publication_id])
    authors = db.relationship('ManuscriptAuthor', cascade='all, delete-orphan', order_by='ManuscriptAuthor.position')
    versions = db.relationship('ManuscriptVersion', order_by='ManuscriptVersion.number')
    events = db.relationship('EditorialEvent', order_by='EditorialEvent.id')

class ManuscriptAuthor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    manuscript_id = db.Column(db.Integer, db.ForeignKey('manuscript.id'), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False)
    name = db.Column(db.String(180), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    orcid = db.Column(db.String(80), default='', nullable=False)
    affiliation = db.Column(db.String(300), default='', nullable=False)
    department = db.Column(db.String(180), default='', nullable=False)
    institution = db.Column(db.String(300), default='', nullable=False)
    city = db.Column(db.String(140), default='', nullable=False)
    country = db.Column(db.String(140), default='', nullable=False)
    corresponding = db.Column(db.Boolean, default=False, nullable=False)

class ManuscriptVersion(db.Model):
    __table_args__ = (db.UniqueConstraint('manuscript_id', 'number'),)
    id = db.Column(db.Integer, primary_key=True)
    manuscript_id = db.Column(db.Integer, db.ForeignKey('manuscript.id'), nullable=False, index=True)
    number = db.Column(db.Integer, nullable=False)
    uploader_id = db.Column(db.Integer, db.ForeignKey('researcher.id'), nullable=False)
    snapshot = db.Column(db.JSON, default=dict, nullable=False)
    response_to_editor = db.Column(db.Text, default='', nullable=False)
    finalized_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    files = db.relationship('ManuscriptFile', cascade='all, delete-orphan', order_by='ManuscriptFile.id')

class ManuscriptFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey('manuscript_version.id'), nullable=False, index=True)
    kind = db.Column(db.String(40), nullable=False)
    original_name = db.Column(db.String(180), nullable=False)
    internal_name = db.Column(db.String(80), unique=True, nullable=False)
    mime = db.Column(db.String(100), nullable=False)
    size = db.Column(db.Integer, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    # Bounded private payloads are separate from metadata and never stored in /static.
    payload = db.Column(db.LargeBinary, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    version = db.relationship('ManuscriptVersion', back_populates='files')

class EditorialEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    manuscript_id = db.Column(db.Integer, db.ForeignKey('manuscript.id'), nullable=False, index=True)
    previous_status = db.Column(db.String(40), nullable=False)
    new_status = db.Column(db.String(40), nullable=False)
    action = db.Column(db.String(60), nullable=False)
    actor = db.Column(db.String(180), nullable=False)
    note = db.Column(db.Text, default='', nullable=False)
    visible_to_author = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

class ReviewAssignment(db.Model):
    """Foundation for future reviewer UI; no account gains access from this row alone."""
    id = db.Column(db.Integer, primary_key=True)
    manuscript_id = db.Column(db.Integer, db.ForeignKey('manuscript.id'), nullable=False, index=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('researcher.id'), nullable=False)
    assigned_by = db.Column(db.Integer, db.ForeignKey('admin_user.id'), nullable=False)
    mode = db.Column(db.String(30), default='double_blind', nullable=False)
    status = db.Column(db.String(30), default='invited', nullable=False)
    due_at = db.Column(db.DateTime)
    accepted_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    report = db.Column(db.Text, default='', nullable=False)
    recommendation = db.Column(db.String(40), default='', nullable=False)

class EditorialNotification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    recipient = db.Column(db.String(254), nullable=False)
    subject = db.Column(db.String(300), nullable=False)
    body = db.Column(db.Text, nullable=False)
    html_body = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    sent_at = db.Column(db.DateTime)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    last_error = db.Column(db.String(120), default='', nullable=False)

class PublicationAsset(db.Model):
    """Sanitized figure copies; originals remain private even after publication."""
    id = db.Column(db.Integer, primary_key=True)
    journal_id = db.Column(db.Integer, db.ForeignKey('journal.id'), nullable=False, index=True)
    name = db.Column(db.String(180), nullable=False)
    payload = db.Column(db.LargeBinary, nullable=False)


