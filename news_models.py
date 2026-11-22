"""Editorial identity and independently published versions of science news."""
from datetime import timezone
from zoneinfo import ZoneInfo
from sqlalchemy.orm import joinedload

from models import db, utcnow


class NewsStory(db.Model):
    id = db.Column(db.Integer, primary_key=True)


class NewsVersion(db.Model):
    __table_args__ = (
        db.UniqueConstraint('story_id', 'language'),
        db.UniqueConstraint('language', 'slug'),
        db.CheckConstraint("language IN ('pt', 'en')", name='news_language'),
        db.CheckConstraint(
            "status IN ('draft', 'review', 'reviewed', 'approved', 'published', 'withdrawn')",
            name='news_status',
        ),
        db.CheckConstraint(
            "NOT featured OR status = 'published'", name='news_featured_is_public',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(db.Integer, db.ForeignKey('news_story.id'), nullable=False)
    language = db.Column(db.String(2), nullable=False)
    slug = db.Column(db.String(160), nullable=False)
    title = db.Column(db.String(240), nullable=False, default='')
    summary = db.Column(db.Text, nullable=False, default='')
    body = db.Column(db.Text, nullable=False, default='')
    author_id = db.Column(db.Integer, db.ForeignKey('author.id', ondelete='RESTRICT'))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id', ondelete='RESTRICT'))
    image = db.Column(db.String(1000), nullable=False, default='')
    image_alt = db.Column(db.String(300), nullable=False, default='')
    image_credit = db.Column(db.String(300), nullable=False, default='')
    sources = db.Column(db.JSON, nullable=False, default=list)
    evidence = db.Column(db.String(24), nullable=False, default='')
    evidence_note = db.Column(db.Text, nullable=False, default='')
    africa_focus = db.Column(db.Boolean, nullable=False, default=False)
    related_article_id = db.Column(db.Integer, db.ForeignKey('article.id', ondelete='SET NULL'))
    status = db.Column(db.String(16), nullable=False, default='draft')
    featured = db.Column(db.Boolean, nullable=False, default=False)
    published_at = db.Column(db.DateTime)
    revised_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    edited_by = db.Column(db.Integer, db.ForeignKey('admin_user.id', ondelete='SET NULL'))
    reviewer_id = db.Column(db.Integer, db.ForeignKey('team_member.id', ondelete='SET NULL'))
    review_note = db.Column(db.Text, nullable=False, default='')
    revision = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': revision}

    author = db.relationship('Author')
    category = db.relationship('Category')
    reviewer = db.relationship('TeamMember')
    related_article = db.relationship('Article')

    @classmethod
    def public(cls, language):
        return cls.query.filter_by(language=language, status='published').filter(
            cls.published_at <= utcnow(),
        ).options(joinedload(cls.author), joinedload(cls.category))

    @property
    def published_date(self):
        return self.published_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Africa/Maputo'))

    @property
    def revised_date(self):
        if self.revised_at:
            return self.revised_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Africa/Maputo'))


db.Index('ix_news_listing', NewsVersion.language, NewsVersion.status, NewsVersion.published_at, NewsVersion.id)
db.Index('ix_news_category', NewsVersion.category_id)
db.Index('ix_news_author', NewsVersion.author_id)
db.Index('uq_news_featured_language', NewsVersion.language, unique=True,
         postgresql_where=NewsVersion.featured.is_(True), sqlite_where=NewsVersion.featured.is_(True))
