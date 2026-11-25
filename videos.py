"""Public catalogue, dedicated watch pages and first-party playback metrics."""
from datetime import timezone
from uuid import uuid4
from xml.etree import ElementTree as XML

from flask import Blueprint, Response, abort, current_app, g, render_template, request, url_for
from itsdangerous import BadData, URLSafeTimedSerializer
from sqlalchemy.exc import IntegrityError

from extensions import limiter
from cover_media import cover_delivery_url
from models import Category, db
from request_values import pagination_page
from video_models import ScienceVideo, VideoPlayback

videos_bp = Blueprint('videos', __name__)
EN_ROUTES = {'videos.index': '/videos', 'videos.detail': '/videos/<slug>'}
SITEMAP = 'http://www.sitemaps.org/schemas/sitemap/0.9'
VIDEO_XML = 'http://www.google.com/schemas/sitemap-video/1.1'


def listing_values():
    values = {key: request.args.get(key, '').strip()[:100] for key in ('q', 'tema')}
    values = {key: value for key, value in values.items() if value}
    if request.args.get('ordem') == 'popular':
        values['ordem'] = 'popular'
    if pagination_page() > 1:
        values['page'] = pagination_page()
    return values


def localized_slug(slug, source_locale, target):
    key = (slug, source_locale)
    cache = g.setdefault('video_alternates', {})
    if key not in cache:
        group = ScienceVideo.public(source_locale).filter_by(slug=slug).with_entities(ScienceVideo.series).scalar()
        cache[key] = dict(ScienceVideo.public().filter_by(series=group).with_entities(
            ScienceVideo.language, ScienceVideo.slug).all()) if group else {}
    return cache[key].get(target)


def watch_path(item):
    return url_for('videos.detail', slug=item.slug, _language='en' if item.language == 'en' else None)


def public_article_video(article, locale):
    return ScienceVideo.public(locale).filter_by(article_id=article.id, url=article.cover_video).first()


def asset_counts():
    return db.session.query(
        VideoPlayback.video_id.label('video_id'), db.func.count().label('views'),
        db.func.sum(db.case((VideoPlayback.started.is_(True), 1), else_=0)).label('plays'),
        db.func.sum(db.case((VideoPlayback.completed.is_(True), 1), else_=0)).label('completions'),
        db.func.sum(VideoPlayback.seconds).label('seconds'),
    ).group_by(VideoPlayback.video_id).subquery()


def ordered(query):
    return query.order_by(ScienceVideo.published_at.desc(), ScienceVideo.id.desc())


@videos_bp.get('/videos')
def index():
    from internationalization import language

    values = listing_values()
    public = ScienceVideo.public(language())
    categories = Category.query.filter(Category.id.in_(
        public.with_entities(ScienceVideo.category_id).distinct().statement
    )).order_by(Category.name).all()
    query = public
    if values.get('tema'):
        query = query.join(ScienceVideo.category).filter(Category.slug == values['tema'])
    if values.get('q'):
        terms = values['q']
        query = query.filter(db.or_(*(field.icontains(terms, autoescape=True) for field in (
            ScienceVideo.title, ScienceVideo.description, ScienceVideo.keywords,
        ))))
    if values.get('ordem'):
        counts = asset_counts()
        query = query.outerjoin(counts, counts.c.video_id == ScienceVideo.id).order_by(
            db.func.coalesce(counts.c.views, 0).desc())
    page = ordered(query).paginate(page=values.get('page', 1), per_page=12, error_out=False)
    filters = {key: value for key, value in values.items() if key != 'page'}
    return render_template('videos/index.html', videos=page, video_categories=categories, video_filters=filters)


def published_timestamp(item):
    return item.published_at.replace(tzinfo=timezone.utc).isoformat()


def structured_data(item, site_url):
    payload = {
        '@context': 'https://schema.org', '@type': 'VideoObject',
        'name': item.title, 'description': item.description,
        'thumbnailUrl': item.thumbnail, 'uploadDate': published_timestamp(item),
        'inLanguage': 'en' if item.language == 'en' else 'pt-MZ',
        'publisher': {'@type': 'Organization', 'name': 'Sussurros do Saber', 'url': site_url},
    }
    payload['embedUrl' if item.embed_url else 'contentUrl'] = item.embed_url or cover_delivery_url(item.url)
    if item.duration:
        payload['duration'] = f'PT{item.duration}S'
    return payload


def playback_signer():
    return URLSafeTimedSerializer(current_app.secret_key, salt='science-video-playback')


@videos_bp.get('/videos/<slug>')
def detail(slug):
    from internationalization import language, published

    locale = language()
    video = ScienceVideo.public(locale).filter_by(slug=slug).first_or_404()
    article = video.article
    if article and locale == 'en' and not published('article', article.id)[1]:
        article = None
    recommendations = ordered(ScienceVideo.public(locale).filter(
        ScienceVideo.id != video.id, ScienceVideo.category_id == video.category_id,
    )).limit(3).all()
    return render_template('videos/detail.html', video=video, video_article=article,
                           video_related=recommendations,
                           video_schema=structured_data(video, current_app.config['SCIENCE_VIDEO_SITE_URL']),
                           video_playback=playback_signer().dumps([video.id, uuid4().hex]))


@videos_bp.post('/api/videos/playback')
@limiter.limit('60 per minute')
def playback():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400)
    token, kind = payload.get('token'), payload.get('event')
    if not isinstance(token, str) or len(token) > 240 or kind not in ('view', 'start', 'progress', 'end'):
        abort(400)
    try:
        video_id, key = playback_signer().loads(token, max_age=21600)
    except BadData:
        abort(400)
    video = ScienceVideo.public().filter_by(id=video_id).first_or_404()
    seconds = payload.get('seconds', 0)
    if type(seconds) is not int or not 0 <= seconds <= min(video.duration or 21600, 21600):
        abort(400)
    if video.embed_url and kind != 'view':
        abort(400)
    for attempt in range(2):
        try:
            row = db.session.get(VideoPlayback, key, with_for_update=True)
            if row is None:
                row = VideoPlayback(token=key, video_id=video.id)
                db.session.add(row)
            if kind != 'view':
                row.started = True
                row.seconds = max(row.seconds or 0, seconds)
                if kind == 'end':
                    row.completed = True
            db.session.commit()
            return '', 204
        except IntegrityError:
            db.session.rollback()
            if attempt:
                raise


def sitemap_entries(site_url):
    from internationalization import interface_ready
    from xml.sax.saxutils import escape, quoteattr

    rows = ordered(ScienceVideo.public()).all()
    include_english = interface_ready()
    paths = {(row.series, row.language): site_url + watch_path(row)
             for row in rows if row.language == 'pt' or include_english}
    entries = []
    for (series, locale), path in paths.items():
        alternates = ''.join(
            f'<xhtml:link rel="alternate" hreflang="{language}" href={quoteattr(other)}/>'
            for code, language in (('pt', 'pt-MZ'), ('en', 'en'), ('pt', 'x-default'))
            if (other := paths.get((series, code)))
        )
        entries.append(f'<url><loc>{escape(path)}</loc>{alternates}</url>')
    return ''.join(entries)


@videos_bp.get('/video-sitemap.xml')
def video_sitemap():
    from internationalization import interface_ready

    site_url = current_app.config['SCIENCE_VIDEO_SITE_URL']
    root = XML.Element('urlset', {'xmlns': SITEMAP, 'xmlns:video': VIDEO_XML})
    query = ScienceVideo.public()
    if not interface_ready():
        query = query.filter_by(language='pt')
    for item in ordered(query).all():
        entry = XML.SubElement(root, 'url')
        XML.SubElement(entry, 'loc').text = site_url + watch_path(item)
        video = XML.SubElement(entry, 'video:video')
        fields = {
            'thumbnail_loc': item.thumbnail, 'title': item.title,
            'description': item.description, 'publication_date': published_timestamp(item),
        }
        fields['player_loc' if item.embed_url else 'content_loc'] = item.embed_url or cover_delivery_url(item.url)
        if item.duration and item.duration <= 28800:
            fields['duration'] = str(item.duration)
        for key, value in fields.items():
            XML.SubElement(video, f'video:{key}').text = value
    return Response(XML.tostring(root, encoding='utf-8', xml_declaration=True),
                    mimetype='application/xml', headers={'Cache-Control': 'no-cache'})
