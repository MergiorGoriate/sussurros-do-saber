from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, and_

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AdminUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True)
    password_hash = db.Column(db.String(300), nullable=False)
    role = db.Column(db.String(20), default="editor", nullable=False)
    session_version = db.Column(db.Integer, default=1, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime)
    password_changed_at = db.Column(db.DateTime)

    @property
    def is_superadmin(self):
        return self.role == "superadmin"


class AdminAuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admin_user.id"))
    actor_username = db.Column(db.String(60), nullable=False)
    action = db.Column(db.String(80), nullable=False)
    target = db.Column(db.String(240), default="", nullable=False)
    ip_address = db.Column(db.String(80), default="", nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Author(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True)
    bio = db.Column(db.Text, default="")
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    articles = db.relationship("Article", back_populates="author_rel")


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(90), unique=True, nullable=False)
    articles = db.relationship("Article", back_populates="category_rel")


class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(240), nullable=False)
    slug = db.Column(db.String(260), unique=True, nullable=False)
    summary = db.Column(db.Text, nullable=False)
    body = db.Column(db.Text, default="", nullable=False)
    references = db.Column(db.Text, default="", nullable=False)
    keywords = db.Column(db.String(500), default="")
    doi = db.Column(db.String(180), default="")
    image = db.Column(db.String(600), default="")
    image_public_id = db.Column(db.String(300), default="")
    image_alt = db.Column(db.String(300), default="")
    status = db.Column(db.String(20), default="draft", nullable=False)
    read_minutes = db.Column(db.Integer, default=5, nullable=False)
    featured = db.Column(db.Boolean, default=False, nullable=False)
    published_at = db.Column(db.DateTime)
    scheduled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("author.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    author_rel = db.relationship("Author", back_populates="articles")
    category_rel = db.relationship("Category", back_populates="articles")

    @property
    def author(self):
        return self.author_rel.name

    @property
    def category(self):
        return self.category_rel.name

    @property
    def date(self):
        value = self.published_at or self.scheduled_at or self.created_at
        return value.strftime("%d/%m/%Y")

    @property
    def read_time(self):
        return f"{self.read_minutes} min"

    @classmethod
    def public_query(cls):
        now = utcnow()
        return cls.query.filter(or_(
            cls.status == "published",
            and_(cls.status == "scheduled", cls.scheduled_at.isnot(None), cls.scheduled_at <= now),
        ))


class Journal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False, index=True)
    abbreviation = db.Column(db.String(30), default="", nullable=False)
    field = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=False)
    issn = db.Column(db.String(20), default="", nullable=False)
    frequency = db.Column(db.String(80), default="", nullable=False)
    current_issue = db.Column(db.String(120), default="", nullable=False)
    guidelines = db.Column(db.Text, default="", nullable=False)
    cover_image = db.Column(db.String(600), default="", nullable=False)
    cover_public_id = db.Column(db.String(300), default="", nullable=False)
    cover_alt = db.Column(db.String(300), default="", nullable=False)
    published = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    @classmethod
    def public_query(cls):
        return cls.query.filter_by(published=True)

    @property
    def abbr(self):
        return self.abbreviation

    @property
    def issue(self):
        return self.current_issue

    @property
    def status(self):
        return "Publicada" if self.published else "Oculta"


class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), nullable=False)
    subject = db.Column(db.String(220), nullable=False)
    message = db.Column(db.Text, nullable=False)
    read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Subscriber(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(180), unique=True, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
