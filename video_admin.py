"""Permissioned editorial operations for Science Videos."""
from flask import abort, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from admin import admin_bp, slugify, validate_csrf
from article_scheduling import parse_schedule, schedule_local
from governance import audit, has_permission, require
from models import Article, Category, db, utcnow
from request_values import database_id, pagination_page
from storage import ImageUploadError, upload_article_image
from video_media import article_defaults, cloudinary_details, https_url, media_fields
from video_models import ScienceVideo, VideoPlayback
from videos import asset_counts, watch_path

EDIT = 'article.edit'
PUBLISH = 'article.publish'
TEXT_LIMITS = {
    'title': 240, 'description': 2048, 'thumbnail': 1000, 'keywords': 500,
    'author': 240, 'credits': 500, 'license': 240, 'captions': 1000, 'transcript': 50000,
}
STATUSES = {
    'draft': ('Rascunho', 'Draft'), 'published': ('Publicado', 'Published'),
    'scheduled': ('Agendado', 'Scheduled'), 'withdrawn': ('Retirado', 'Withdrawn'),
    'archived': ('Arquivado', 'Archived'), 'blocked': ('Artigo indisponível', 'Article unavailable'),
}


def admin_url(endpoint, **values):
    if request.args.get('ui') == 'en':
        values['ui'] = 'en'
    return url_for(f'admin.{endpoint}', **values)


@admin_bp.app_context_processor
def video_admin_helpers():
    return dict(video_admin_url=admin_url, video_states=STATUSES, video_schedule_local=schedule_local)


def editorial_access():
    if not (has_permission(EDIT) or has_permission(PUBLISH)):
        abort(403)


def number(name, maximum):
    value = request.form.get(name, '').strip()
    if not value:
        return None
    if not value.isascii() or not value.isdigit() or len(value) > 6 or not 1 <= int(value) <= maximum:
        raise ValueError('Verifique os campos numéricos. / Check the numeric fields.')
    return int(value)


def field_values(prefix='', defaults=None):
    defaults = defaults or {}
    values = {}
    for name, limit in TEXT_LIMITS.items():
        value = request.form.get(prefix + name, '').strip() or str(defaults.get(name) or '').strip()
        if len(value) > limit or any(ord(char) < 32 and char not in '\t\r\n' for char in value):
            raise ValueError('Verifique os limites dos campos. / Check the field limits.')
        values[name] = value
    for name in ('thumbnail', 'captions'):
        values[name] = https_url(values[name])
    if values['captions'] and not values['captions'].split('?')[0].lower().endswith('.vtt'):
        raise ValueError('Use legendas WebVTT (.vtt). / Use WebVTT captions (.vtt).')
    return values


def persist():
    try:
        db.session.commit()
    except (IntegrityError, StaleDataError):
        db.session.rollback()
        abort(409, description='Edição concorrente ou vídeo já registado. / Concurrent edit or duplicate video.')


def stage_article_video(article, upload_metadata=None):
    """Create an opted-in draft in the article transaction without another upload."""
    require(EDIT)
    if article.cover_format not in {'video_animated', 'video_controls'}:
        raise ValueError('Seleccione um formato de capa de vídeo.')
    fields = media_fields(article.cover_video, legacy=True)
    locale = request.form.get('science_video_language', 'pt')
    if locale not in {'pt', 'en'}:
        abort(400)
    existing = ScienceVideo.query.filter_by(article_id=article.id, language=locale).first()
    if existing:
        return existing
    if ScienceVideo.query.filter_by(asset_key=fields['asset_key'], language=locale).first():
        raise ValueError('Este ficheiro já está registado neste idioma.')
    defaults = article_defaults(article) if locale == 'pt' else {
        'author': article.author, 'thumbnail': article.cover_poster,
    }
    values = field_values('science_video_', defaults)
    for name in ('title', 'description'):
        if not values[name]:
            raise ValueError('Preencha o título e a descrição do vídeo no idioma escolhido.')
    category = database_id(request.form.get('science_video_category'), optional=True) or article.category_id
    if not db.session.get(Category, category):
        raise ValueError('Seleccione uma categoria válida.')
    sibling = ScienceVideo.query.filter_by(article_id=article.id).first()
    item = ScienceVideo(language=locale, slug=slugify(values['title'])[:160].strip('-'),
                        category_id=category, article_id=article.id, **fields, **values, **(upload_metadata or {}))
    if not item.slug:
        raise ValueError('Indique um título que permita gerar o endereço do vídeo.')
    if sibling:
        item.series = sibling.series
    db.session.add(item)
    db.session.flush()
    audit('science_video.create', 'science_video', item.id, 'Origem: editor do artigo')
    return item


@admin_bp.get('/videos')
def video_index():
    editorial_access()
    query = ScienceVideo.query
    q = request.args.get('q', '').strip()[:100]
    language = request.args.get('language')
    state = request.args.get('status')
    now = utcnow()
    scheduled = db.and_(ScienceVideo.status == 'published', ScienceVideo.scheduled_at > now)
    if language in {'pt', 'en'}:
        query = query.filter_by(language=language)
    if state == 'published':
        query = query.filter(ScienceVideo.id.in_(ScienceVideo.public().with_entities(ScienceVideo.id).statement))
    elif state == 'scheduled':
        query = query.filter(scheduled)
    elif state in {'draft', 'withdrawn', 'archived'}:
        query = query.filter_by(status=state)
    if q:
        query = query.filter(ScienceVideo.title.icontains(q, autoescape=True))
    page = query.order_by(ScienceVideo.updated_at.desc(), ScienceVideo.id.desc()).paginate(
        page=pagination_page(), per_page=30, error_out=False)
    counts = asset_counts()
    views, plays, ends, seconds = db.session.query(
        *(db.func.coalesce(db.func.sum(column), 0) for column in
          (counts.c.views, counts.c.plays, counts.c.completions, counts.c.seconds)),
    ).one()
    top = db.session.query(ScienceVideo, counts.c.views).join(counts, counts.c.video_id == ScienceVideo.id).order_by(
        counts.c.views.desc(), ScienceVideo.id.desc()).limit(5).all()
    stats = {
        'total': ScienceVideo.query.count(), 'published': ScienceVideo.public().count(),
        'draft': ScienceVideo.query.filter_by(status='draft').count(),
        'scheduled': ScienceVideo.query.filter(scheduled).count(), 'views': views, 'plays': plays,
        'average': round(seconds / plays, 1) if plays else None,
        'completion': round(100 * ends / plays, 1) if plays else None,
    }
    return render_template('admin/videos/index.html', rows=page, stats=stats, top=top, q=q,
                           filters={key: request.args[key] for key in ('q', 'language', 'status') if request.args.get(key)})


def publication_fields(item, action):
    if not all((item.title, item.description, item.thumbnail, item.author, item.category_id)):
        raise ValueError('Preencha título, descrição, miniatura, autoria e categoria. / Complete title, description, thumbnail, author and category.')
    if item.article and item.article.status != 'published':
        raise ValueError('Publique primeiro o artigo associado. / Publish the linked article first.')
    scheduled = None
    if action == 'schedule':
        scheduled = parse_schedule(request.form.get('scheduled_at'), 'Africa/Maputo')
        if not scheduled or scheduled <= utcnow():
            raise ValueError('Indique uma data futura. / Enter a future date.')
    if not item.published_at or item.status != 'published' or action == 'schedule' or item.published_at > utcnow():
        item.published_at = scheduled or utcnow()
    item.status, item.scheduled_at = 'published', scheduled


def save_fields(item):
    locale = request.form.get('language')
    if locale not in {'pt', 'en'}:
        raise ValueError('Seleccione um idioma. / Choose a language.')
    article_slug = request.form.get('article_slug', '').strip()
    article = Article.query.filter_by(slug=article_slug[:260]).first() if article_slug else None
    if article_slug and (len(article_slug) > 260 or article is None):
        raise ValueError('Artigo desconhecido. / Unknown article.')
    category_id = database_id(request.form.get('category_id'), optional=True)
    if category_id and not db.session.get(Category, category_id):
        raise ValueError('Categoria desconhecida. / Unknown category.')
    source = request.form.get('url', '').strip()
    fields = media_fields(source, legacy=bool(
        (article and source == article.cover_video) or (item.id and source == item.url)))
    values = field_values()
    slug = slugify((request.form.get('slug') or values['title'])[:240])[:160].strip('-')
    if not values['title'] or not slug:
        raise ValueError('Indique um título e um endereço válido. / Enter a title and a valid slug.')
    if item.published_at and (item.slug != slug or item.language != locale):
        raise ValueError('O endereço de um vídeo publicado é permanente. / A published video URL is permanent.')
    translation = database_id(request.form.get('translation_of'), optional=True)
    if translation:
        sibling = db.session.get(ScienceVideo, translation)
        if sibling is None or sibling.id == item.id or sibling.language == locale:
            raise ValueError('Seleccione um vídeo no outro idioma. / Select a video in the other language.')
        if item.id and item.series != sibling.series and ScienceVideo.query.filter_by(series=item.series).count() > 1:
            raise ValueError('Este vídeo já pertence a um grupo bilingue. / This video already has a translation.')
        item.series = sibling.series
    item.title, item.slug, item.language = values['title'], slug, locale
    item.article, item.category_id = article, category_id
    metadata = {name: number(name, maximum) for name, maximum in (
        ('duration', 86400), ('width', 16384), ('height', 16384),
    )}
    for key, value in {**fields, **values, **metadata}.items():
        setattr(item, key, value)
    if not item.thumbnail and item.cloudinary_id:
        from cover_media import cover_poster_url
        item.thumbnail = cover_poster_url('', source)
    thumbnail = request.files.get('thumbnail_file')
    if thumbnail and thumbnail.filename:
        item.thumbnail = https_url(upload_article_image(thumbnail))


@admin_bp.route('/videos/novo', methods=['GET', 'POST'])
@admin_bp.route('/videos/<int:ident>', methods=['GET', 'POST'])
def video_form(ident=None):
    editorial_access()
    item = db.get_or_404(ScienceVideo, ident) if ident else ScienceVideo(status='draft', language='pt')
    if request.method == 'POST':
        validate_csrf()
        action = request.form.get('action')
        if action not in {'save', 'publish', 'schedule', 'withdraw', 'archive', 'delete', 'metadata'}:
            abort(400)
        require(PUBLISH if action not in {'save', 'metadata'} or item.status == 'published' else EDIT)
        if action in {'withdraw', 'archive', 'delete'} and not item.id:
            abort(400)
        if item.id and str(item.revision) != request.form.get('revision'):
            abort(409)
        try:
            if action == 'metadata':
                return render_form(item, metadata=cloudinary_details(request.form.get('url', '').strip()))
            if action in {'save', 'publish', 'schedule'}:
                save_fields(item)
                if action != 'save':
                    publication_fields(item, action)
                elif item.status == 'published':
                    if item.scheduled_at and item.scheduled_at > utcnow():
                        publication_fields(item, 'schedule')
                    else:
                        publication_fields(item, 'publish')
                db.session.add(item)
            elif action == 'delete':
                if item.status != 'archived' or request.form.get('confirm_delete') != 'yes':
                    abort(400, description='Arquive e confirme a eliminação do registo.')
                db.session.query(VideoPlayback).filter_by(video_id=item.id).delete()
                db.session.delete(item)
            else:
                item.status = 'withdrawn' if action == 'withdraw' else 'archived'
                item.scheduled_at = None
            try:
                db.session.flush()
            except (IntegrityError, StaleDataError):
                db.session.rollback()
                abort(409, description='Edição concorrente ou vídeo já registado. / Concurrent edit or duplicate video.')
            audit(f'science_video.{action}', 'science_video', item.id)
            persist()
            flash('Alteração guardada. / Changes saved.', 'success')
            return redirect(admin_url('video_index') if action == 'delete' else admin_url('video_form', ident=item.id))
        except (ValueError, ImageUploadError) as error:
            db.session.rollback()
            flash(str(error), 'error')
            return render_form(item, 400)
    return render_form(item)


def render_form(item, status=200, metadata=None):
    sibling = ScienceVideo.query.filter(ScienceVideo.series == item.series, ScienceVideo.id != item.id).first() if item.series else None
    return render_template('admin/videos/form.html', video=item, video_sibling=sibling,
                           video_categories=Category.query.order_by(Category.name).all(), watch_path=watch_path,
                           video_metadata=metadata or {}), status


@admin_bp.get('/videos/<int:ident>/prever')
def video_preview(ident):
    editorial_access()
    item = db.get_or_404(ScienceVideo, ident)
    return render_template('admin/videos/preview.html', video=item)


def import_candidate_articles():
    return Article.query.filter(
        Article.cover_video.isnot(None), Article.cover_video != '',
        Article.cover_mode != 'image',
        ~db.exists().where(ScienceVideo.article_id == Article.id, ScienceVideo.language == 'pt'),
    ).order_by(Article.id.desc())


@admin_bp.route('/videos/importar', methods=['GET', 'POST'])
def video_import():
    require(EDIT)
    query = import_candidate_articles()
    if request.method == 'POST':
        validate_csrf()
        values = request.form.getlist('articles')
        if len(values) > 30:
            abort(400)
        try:
            ids = {database_id(value) for value in values}
        except ValueError:
            abort(400)
        keys = {
            row.asset_key for row in ScienceVideo.query.filter_by(language='pt').with_entities(ScienceVideo.asset_key)
        }
        count = 0
        for article in query.filter(Article.id.in_(ids)).all():
            try:
                fields = media_fields(article.cover_video, legacy=True)
            except ValueError:
                continue
            if fields['asset_key'] in keys:
                continue
            keys.add(fields['asset_key'])
            defaults = article_defaults(article)
            try:
                defaults['thumbnail'] = https_url(defaults['thumbnail'])
            except ValueError:
                defaults['thumbnail'] = ''
            slug = article.slug[:145].strip('-')
            item = ScienceVideo(language='pt', slug=f'{slug}-{article.id}', article_id=article.id, **defaults, **fields)
            db.session.add(item)
            count += 1
        audit('science_video.import', 'science_video', detail=str(count))
        persist()
        flash(f'{count} vídeo(s) importado(s) como rascunho. / {count} video draft(s) imported.', 'success')
        return redirect(admin_url('video_import'))
    page = query.paginate(page=pagination_page(), per_page=30, error_out=False)
    return render_template('admin/videos/import.html', rows=page)
