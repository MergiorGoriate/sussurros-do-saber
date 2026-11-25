"""Catalogue records and anonymous playback counters."""
from uuid import uuid4

from models import Article, db, utcnow


class ScienceVideo(db.Model):
    __table_args__ = (
        db.UniqueConstraint('language', 'slug', name='uq_science_video_slug'),
        db.UniqueConstraint('language', 'asset_key', name='uq_science_video_asset'),
        db.UniqueConstraint('language', 'series', name='uq_science_video_series'),
        db.UniqueConstraint('language', 'article_id', name='uq_science_video_article'),
        db.CheckConstraint("language in ('pt', 'en')", name='science_video_language'),
        db.CheckConstraint("status in ('draft', 'published', 'withdrawn', 'archived')", name='science_video_status'),
        db.Index('ix_science_video_listing', 'language', 'status', 'published_at', 'id'),
    )
    id = db.Column(db.Integer, primary_key=True)
    series = db.Column(db.String(32), nullable=False, default=lambda: uuid4().hex)
    language = db.Column(db.String(2), nullable=False)
    slug = db.Column(db.String(160), nullable=False)
    title = db.Column(db.String(240), nullable=False)
    description = db.Column(db.Text, nullable=False, default='')
    url = db.Column(db.String(1000), nullable=False)
    asset_key = db.Column(db.String(64), nullable=False)
    cloudinary_id = db.Column(db.String(500), nullable=False, default='')
    embed_url = db.Column(db.String(1000), nullable=False, default='')
    thumbnail = db.Column(db.String(1000), nullable=False, default='')
    duration = db.Column(db.Integer)
    format = db.Column(db.String(12), nullable=False, default='')
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    author = db.Column(db.String(240), nullable=False, default='')
    credits = db.Column(db.String(500), nullable=False, default='')
    license = db.Column(db.String(240), nullable=False, default='')
    keywords = db.Column(db.String(500), nullable=False, default='')
    captions = db.Column(db.String(1000), nullable=False, default='')
    transcript = db.Column(db.Text, nullable=False, default='')
    category_id = db.Column(db.Integer, db.ForeignKey('category.id', ondelete='RESTRICT'))
    article_id = db.Column(db.Integer, db.ForeignKey('article.id', ondelete='CASCADE'), index=True)
    status = db.Column(db.String(16), nullable=False, default='draft')
    published_at = db.Column(db.DateTime)
    scheduled_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    revision = db.Column(db.Integer, nullable=False, default=1)
    __mapper_args__ = {'version_id_col': revision}

    category = db.relationship('Category')
    article = db.relationship('Article')

    @classmethod
    def public(cls, locale=None):
        query = cls.query.filter(cls.status == 'published', cls.published_at <= utcnow(),
                                 db.or_(cls.article_id.is_(None), cls.article.has(Article.status == 'published')))
        return query.filter(cls.language == locale) if locale else query

    @property
    def state(self):
        if self.status == 'published' and self.scheduled_at and self.scheduled_at > utcnow():
            return 'scheduled'
        if self.status == 'published' and self.article and self.article.status != 'published':
            return 'blocked'
        return self.status

    @property
    def duration_label(self):
        if self.duration is None:
            return ''
        minutes, seconds = divmod(self.duration, 60)
        return f'{minutes}:{seconds:02d}'


class VideoPlayback(db.Model):
    token = db.Column(db.String(32), primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('science_video.id', ondelete='CASCADE'), nullable=False, index=True)
    started = db.Column(db.Boolean, nullable=False, default=False)
    completed = db.Column(db.Boolean, nullable=False, default=False)
    seconds = db.Column(db.Integer, nullable=False, default=0)
