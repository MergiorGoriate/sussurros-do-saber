from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, and_
from sqlalchemy.orm import joinedload, load_only

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AdminUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(60), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(180), unique=True)
    password_hash = db.Column(db.String(300), nullable=False)
    is_superadmin = db.Column(db.Boolean, default=False, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    last_login_at = db.Column(db.DateTime)
    two_factor_enabled = db.Column(db.Boolean, default=False, nullable=False)
    totp_secret = db.Column(db.String(64))
    recovery_code_hashes = db.Column(db.Text, default="", nullable=False)


class Author(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(160), unique=True, nullable=False, index=True)
    email = db.Column(db.String(180), unique=True)
    role = db.Column(db.String(140), default="")
    headline = db.Column(db.String(220), default="")
    academic_background = db.Column(db.Text, default="")
    institution = db.Column(db.String(220), default="")
    bio = db.Column(db.Text, default="")
    interests = db.Column(db.Text, default="")
    projects = db.Column(db.Text, default="")
    orcid = db.Column(db.String(19), default="")
    google_scholar = db.Column(db.String(600), default="")
    researchgate = db.Column(db.String(600), default="")
    publications = db.Column(db.Text, default="")
    editorial_experience = db.Column(db.Text, default="")
    photo = db.Column(db.String(600), default="")
    display_order = db.Column(db.Integer, default=100, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    articles = db.relationship("Article", back_populates="author_rel")

    @property
    def published_article_count(self):
        """Número de artigos efetivamente publicados deste autor."""
        return Article.query.filter(
            Article.author_id == self.id,
            Article.status == "published",
        ).count()


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(90), unique=True, nullable=False)
    articles = db.relationship("Article", back_populates="category_rel")


class Journal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False, index=True)
    abbreviation = db.Column(db.String(30), default="")
    field = db.Column(db.String(140), nullable=False)
    description = db.Column(db.Text, nullable=False)
    issn = db.Column(db.String(9), default="")
    frequency = db.Column(db.String(80), default="")
    current_issue = db.Column(db.String(120), default="")
    doi = db.Column(db.String(180), default="")
    publication_date = db.Column(db.Date)
    authors_orcid = db.Column(db.Text, default="")
    guidelines = db.Column(db.Text, default="")
    aims_scope = db.Column(db.Text, default="")
    editorial_policy = db.Column(db.Text, default="")
    peer_review = db.Column(db.Text, default="")
    publication_ethics = db.Column(db.Text, default="")
    submission_guidelines = db.Column(db.Text, default="")
    article_types = db.Column(db.Text, default="")
    open_access_policy = db.Column(db.Text, default="")
    copyright_policy = db.Column(db.Text, default="")
    fees_policy = db.Column(db.Text, default="")
    editorial_board = db.Column(db.Text, default="")
    contact_info = db.Column(db.Text, default="")
    cover_image = db.Column(db.String(600), default="")
    cover_alt = db.Column(db.String(300), default="")
    published = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


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
    comments = db.relationship("Comment", back_populates="article", cascade="all, delete-orphan")

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

    @property
    def is_public(self):
        return self.status == "published"

    @classmethod
    def publish_due_scheduled(cls):
        """Promove artigos programados vencidos para publicados.

        O agendamento é guardado em UTC sem timezone, tal como utcnow().
        A atualização em lote mantém o estado persistido coerente no /admin.
        """
        now = utcnow()
        due = cls.query.filter(
            cls.status == "scheduled",
            cls.scheduled_at.isnot(None),
            cls.scheduled_at <= now,
        )
        changed = due.update(
            {
                cls.status: "published",
                cls.published_at: db.func.coalesce(cls.published_at, cls.scheduled_at),
                cls.updated_at: now,
            },
            synchronize_session=False,
        )
        if changed:
            db.session.commit()
        return changed

    @classmethod
    def public_query(cls):
        # Artigos futuros/programados nunca entram nas consultas públicas.
        # publish_due_scheduled() converte os vencidos antes de cada pedido.
        return cls.query.filter(cls.status == "published")

    @classmethod
    def public_card_query(cls):
        """Consulta leve para listas: evita carregar corpo e referências extensos."""
        return cls.public_query().options(
            load_only(
                cls.id, cls.title, cls.slug, cls.summary, cls.image, cls.status,
                cls.read_minutes, cls.featured, cls.published_at, cls.scheduled_at,
                cls.created_at, cls.updated_at, cls.author_id, cls.category_id,
            ),
            joinedload(cls.author_rel).load_only(Author.id, Author.name, Author.slug, Author.photo),
            joinedload(cls.category_rel).load_only(Category.id, Category.name, Category.slug),
        )


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey("article.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    body = db.Column(db.Text, nullable=False)
    approved = db.Column(db.Boolean, default=False, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    article = db.relationship("Article", back_populates="comments")


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
