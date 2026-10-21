from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, and_
from sqlalchemy.orm import joinedload, load_only
from sqlalchemy import event, inspect as sqlalchemy_inspect

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
    governance_managed = db.Column(db.Boolean, default=False, nullable=False)
    security_version = db.Column(db.Integer, default=1, nullable=False)


@event.listens_for(AdminUser, "before_update")
def invalidate_changed_admin_credentials(mapper, connection, administrator):
    """Revoke existing sessions and challenges on security-sensitive changes."""
    state = sqlalchemy_inspect(administrator)
    if any(state.attrs[name].history.has_changes() for name in (
        "password_hash", "username", "active", "is_superadmin",
        "two_factor_enabled", "totp_secret",
    )):
        administrator.security_version = (administrator.security_version or 1) + 1


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
    article_title = db.Column(db.String(300), default="")
    article_title_en = db.Column(db.String(300), default="")
    corresponding_author = db.Column(db.Text, default="")
    summary = db.Column(db.Text, default="")
    keywords = db.Column(db.Text, default="")
    abstract = db.Column(db.Text, default="")
    abstract_keywords = db.Column(db.Text, default="")
    author_contributions = db.Column(db.Text, default="")
    conflicts_of_interest = db.Column(db.Text, default="")
    ethics_approval = db.Column(db.Text, default="")
    informed_consent = db.Column(db.Text, default="")
    data_availability = db.Column(db.Text, default="")
    notes = db.Column(db.Text, default="")

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
    authors_data = db.Column(db.Text, default="")
    submission_history = db.Column(db.Text, default="")
    acknowledgements = db.Column(db.Text, default="")
    funding = db.Column(db.Text, default="")
    license_info = db.Column(db.Text, default="")
    content_markdown = db.Column(db.Text, default="")
    references = db.Column(db.Text, default="")
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


class EditorialPolicy(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    page_title = db.Column(db.Text, default="", nullable=False)
    page_description = db.Column(db.Text, default="", nullable=False)
    page_content = db.Column(db.Text, default="", nullable=False)
    author_guidelines = db.Column(db.Text, default="", nullable=False)
    reviewer_guidelines = db.Column(db.Text, default="", nullable=False)
    ethics_policy = db.Column(db.Text, default="", nullable=False)
    ai_policy = db.Column(db.Text, default="", nullable=False)
    data_policy = db.Column(db.Text, default="", nullable=False)
    fees_policy = db.Column(db.Text, default="", nullable=False)
    open_access_policy = db.Column(db.Text, default="", nullable=False)
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
    cover_video = db.Column(db.String(1000), default="")
    cover_mode = db.Column(db.String(24), default="auto", server_default="auto", nullable=False)
    background = db.Column(db.String(20), default="default", server_default="default", nullable=False)
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
    def cover_format(self):
        from cover_media import effective_cover_mode
        return effective_cover_mode(self.cover_mode, self.cover_video)

    @staticmethod
    def normalize_background(value):
        return value if value in ("default", "aged_paper") else "default"

    @property
    def background_style(self):
        return self.normalize_background(self.background)

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
        """Publica aprovações pendentes e agendamentos vencidos, sob bloqueio.

        Aprovações antigas exigem revisão independente e decisão registadas no
        fluxo. Programações futuras permanecem privadas até ao horário UTC.
        """
        now = utcnow()
        due = cls.query.filter(or_(
            cls.status == "approved",
            and_(cls.status == "scheduled", cls.scheduled_at.isnot(None),
                 cls.scheduled_at <= now),
        ))
        # Lock due rows so concurrent workers cannot publish or notify twice.
        from governance_models import ArticleWorkflow, GovernanceAudit
        from internal_notices import dispatch
        changed = 0
        for article in due.with_for_update(skip_locked=True).all():
            workflow = ArticleWorkflow.query.filter_by(article_id=article.id).with_for_update().first()
            was_approved = article.status == 'approved'
            if was_approved:
                from governance import independent_article_reviewer
                if (not workflow or workflow.stage != 'approved' or not workflow.approved_at
                    or not workflow.reviewed_at
                    or not independent_article_reviewer(workflow.reviewer, article, workflow.owner_id)
                    or (workflow.editor and (workflow.editor_id in {workflow.owner_id, workflow.reviewer_id}
                                            or workflow.editor.author_id == article.author_id))):
                    continue
            elif workflow and (not workflow.approved_at or workflow.stage != 'scheduled'):
                continue
            article.status = 'published'
            article.published_at = now if was_approved else (article.published_at or article.scheduled_at)
            if was_approved:
                article.scheduled_at = None
            article.updated_at = now
            if workflow:
                workflow.stage = 'published'
            detail = 'Publicação automática após aprovação editorial.' if was_approved else 'Publicação automática na data programada.'
            event_key = (f'approved-publication:{article.id}:{workflow.approved_at.isoformat()}' if was_approved
                         else f'scheduled-publication:{article.id}:{article.scheduled_at.isoformat()}')
            db.session.add(GovernanceAudit(actor_name='Publicação automática', action='article.publish',
                entity='article', entity_id=article.id, detail=detail))
            dispatch('article.publish', 'article', article.id, detail, key=event_key)
            changed += 1
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






