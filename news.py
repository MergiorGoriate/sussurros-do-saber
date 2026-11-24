"""Public Science News pages and language-aware publication queries."""
from xml.sax.saxutils import escape

from flask import Blueprint, abort, g, render_template, request, url_for

from models import Category, db, utcnow
from news_models import NewsVersion
from request_values import pagination_page

news_bp = Blueprint('news', __name__)
EN_ROUTES = {'news.index': '/news', 'news.detail': '/news/<slug>'}
MISSING_COPY = {
    'en': ('This article is not yet available in English', 'Browse Science News in English'),
    'pt': ('Esta notícia ainda não está disponível em português', 'Ver Notícias de Ciência em português'),
}
EVIDENCE_LABELS = {
    'peer_reviewed': 'Revisto por pares',
    'preprint': 'Pré-publicação sem revisão por pares',
    'preliminary': 'Evidência preliminar',
    'unconfirmed': 'Revisão por pares por confirmar',
}


def ordered_news(query):
    return query.order_by(NewsVersion.published_at.desc(), NewsVersion.id.desc())


def latest_news(locale):
    return ordered_news(NewsVersion.public(locale).options(
        db.defer(NewsVersion.body), db.defer(NewsVersion.sources), db.defer(NewsVersion.evidence_note),
    )).limit(3).all()


def listing_values(*, include_page=True):
    theme = request.args.get('tema', '').strip()[:90]
    values = {'tema': theme} if theme else {}
    if include_page and pagination_page() > 1:
        values['page'] = pagination_page()
    return values


def translation_routes(slug, source_locale=None):
    """Resolve a published story in the current locale, then find public siblings."""
    from internationalization import language

    source_locale = source_locale or language()
    cache = g.setdefault('news_routes', {})
    key = (source_locale, slug)
    if key not in cache:
        story_id = db.session.scalar(db.select(NewsVersion.story_id).where(
            NewsVersion.language == source_locale, NewsVersion.slug == slug,
            NewsVersion.status == 'published', NewsVersion.published_at <= utcnow(),
        ))
        cache[key] = dict(db.session.execute(
            db.select(NewsVersion.language, NewsVersion.slug).where(
                NewsVersion.story_id == story_id,
                NewsVersion.status == 'published',
                NewsVersion.published_at <= utcnow(),
            )
        ).all()) if story_id else {}
    return cache[key]


@news_bp.get('/noticias')
def index():
    from internationalization import language

    query = NewsVersion.public(language()).options(
        db.defer(NewsVersion.body), db.defer(NewsVersion.sources), db.defer(NewsVersion.evidence_note),
    )
    theme = listing_values(include_page=False).get('tema', '')
    categories = Category.query.filter(db.exists().where(
        NewsVersion.category_id == Category.id,
        NewsVersion.language == language(),
        NewsVersion.status == 'published',
        NewsVersion.published_at <= utcnow(),
    )).order_by(Category.name).all()
    if theme:
        query = query.join(NewsVersion.category).filter(Category.slug == theme)
        lead = None
    else:
        lead = ordered_news(query.filter_by(featured=True)).first() or ordered_news(query).first()
        if lead:
            query = query.filter(NewsVersion.id != lead.id)
    results = ordered_news(query).paginate(page=pagination_page(), per_page=12, error_out=False)
    return render_template('news/index.html', lead_news=lead, news_items=results.items,
                           news_page=results, news_themes=categories, active_theme=theme)


@news_bp.get('/noticias/<slug>')
def detail(slug):
    from internationalization import interface_ready, language, published

    locale = language()
    item = NewsVersion.public(locale).filter_by(slug=slug).first_or_404()
    related = item.related_article
    if related and (
        related.status != 'published' or
        (locale == 'en' and not (interface_ready() and published('article', related.id)[1]))
    ):
        related = None
    missing = request.args.get('idioma_indisponivel')
    if missing not in {'pt', 'en'} or missing == locale or missing in translation_routes(slug):
        missing = None
    # Apenas notícias públicas do mesmo idioma, sem expor rascunhos ou versões futuras.
    related_news = ordered_news(
        NewsVersion.public(locale).filter(NewsVersion.id != item.id).options(
            db.defer(NewsVersion.body), db.defer(NewsVersion.sources),
            db.defer(NewsVersion.evidence_note),
        )
    ).limit(3).all()
    return render_template('news/detail.html', news_item=item, news_related=related,
                           news_suggestions=related_news,
                           news_missing_locale=missing, news_missing_copy=MISSING_COPY.get(missing),
                           news_listing=listing_values(),
                           evidence_labels=EVIDENCE_LABELS)


def sitemap_entries(origin):
    from internationalization import interface_ready

    query = db.select(NewsVersion.story_id, NewsVersion.language, NewsVersion.slug,
                      db.func.coalesce(NewsVersion.revised_at, NewsVersion.published_at))
    query = query.where(NewsVersion.status == 'published', NewsVersion.published_at <= utcnow())
    english = interface_ready()
    groups = {}
    for story_id, locale, slug, updated in db.session.execute(query.order_by(NewsVersion.story_id)):
        if locale == 'en' and not english:
            continue
        path = url_for('news.detail', slug=slug, _language='en' if locale == 'en' else None)
        groups.setdefault(story_id, {})[locale] = (origin + path, updated)
    entries = []
    for versions in groups.values():
        links = ''
        if len(versions) == 2:
            for code, locale in (('pt-MZ', 'pt'), ('en', 'en'), ('x-default', 'pt')):
                target = escape(versions[locale][0], {'"': '&quot;'})
                links += f'<xhtml:link rel="alternate" hreflang="{code}" href="{target}"/>'
        for url, updated in versions.values():
            entries.append(f'<url><loc>{escape(url)}</loc><lastmod>{updated:%Y-%m-%d}</lastmod>{links}</url>')
    return ''.join(entries)
