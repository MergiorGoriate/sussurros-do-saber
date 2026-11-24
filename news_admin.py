"""Editorial workflow for each language of a science news story."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from admin import admin_bp, slugify, validate_csrf
from governance import audit, current_member, eligible, has_permission, require
from models import Article, Author, Category, db, utcnow
from news import EVIDENCE_LABELS
from news_models import NewsStory, NewsVersion
from premium_resources import safe_url
from request_values import database_id, pagination_page
from storage import upload_article_image

EDIT = 'article.edit'
WRITE = 'article.write'
REVIEW = 'article.review'
APPROVE = 'article.approve'
PUBLISH = 'article.publish'
STATUSES = {
    'draft': 'Rascunho', 'review': 'Em revisão', 'reviewed': 'Revista',
    'approved': 'Aprovada', 'published': 'Publicada', 'withdrawn': 'Retirada',
}
TEXT_LIMITS = {
    'title': 240, 'slug': 160, 'summary': 2000, 'body': 400000, 'image': 1000,
    'image_alt': 300, 'image_credit': 300, 'evidence_note': 4000,
    'evidence': 24, 'related_slug': 260, 'sources_text': 24000,
}


SCHEDULE_ZONES = {'Africa/Maputo': 'Moçambique (UTC+02:00)', 'UTC': 'UTC'}


def is_scheduled(item):
    """A future publication is private until published_at, without a background job."""
    return bool(item and item.status == 'published' and item.published_at
                and item.published_at > utcnow())


def scheduling_form_values(item):
    zone = request.form.get('schedule_timezone', 'Africa/Maputo')
    if zone not in SCHEDULE_ZONES:
        zone = 'Africa/Maputo'
    local_time = ''
    if item and is_scheduled(item):
        local_time = item.published_at.replace(tzinfo=timezone.utc).astimezone(
            ZoneInfo(zone)).strftime('%Y-%m-%dT%H:%M')
    return zone, request.form.get('scheduled_at', local_time)


def parse_schedule():
    zone = request.form.get('schedule_timezone', 'Africa/Maputo')
    if zone not in SCHEDULE_ZONES:
        raise ValueError('Seleccione um fuso horário válido para programar a notícia.')
    raw = request.form.get('scheduled_at', '')
    try:
        local_date = datetime.strptime(raw, '%Y-%m-%dT%H:%M')
    except (ValueError, TypeError):
        raise ValueError('Indique uma data e hora válidas para a publicação programada.')
    scheduled_utc = local_date.replace(tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)
    if scheduled_utc <= datetime.now(timezone.utc):
        raise ValueError('A publicação programada deve ter uma data e hora futuras.')
    return scheduled_utc.replace(tzinfo=None)


def assigned_reviewer(item, member):
    return bool(member and member.id == item.reviewer_id and has_permission(REVIEW, member=member))


def can_edit(item, member):
    if item and item.status == 'published':
        return has_permission(PUBLISH) or (
            session.get('admin_superuser') and has_permission(EDIT)
        )
    return has_permission(EDIT) or bool(
        has_permission(WRITE) and member and member.author_id
        and (item is None or (item.author_id == member.author_id and item.status in {'draft', 'withdrawn'}))
    )


def editorial_scope(member):
    query = NewsVersion.query
    if any(has_permission(permission) for permission in (EDIT, APPROVE, PUBLISH)):
        return query
    clauses = []
    if member and member.author_id and has_permission(WRITE):
        clauses.append(NewsVersion.author_id == member.author_id)
    if member and has_permission(REVIEW, member=member):
        clauses.append(NewsVersion.reviewer_id == member.id)
    return query.filter(db.or_(*clauses)) if clauses else query.filter(db.false())


def require_news_access():
    if not any(has_permission(permission) for permission in (EDIT, WRITE, REVIEW, APPROVE, PUBLISH)):
        abort(403)


def read_fields(member):
    values = {name: request.form.get(name, '').strip() for name in TEXT_LIMITS}
    for name, limit in TEXT_LIMITS.items():
        if len(values[name]) > limit:
            raise ValueError('Um dos campos excede o limite permitido.')
    slug = values['slug'] or values['title']
    values['slug'] = slugify(slug)[:160].strip('-')
    if not values['slug']:
        raise ValueError('Indique um título ou um identificador válido para o rascunho.')
    values['author_id'] = database_id(request.form.get('author_id'), optional=True)
    values['category_id'] = database_id(request.form.get('category_id'), optional=True)
    if not has_permission(EDIT) and not has_permission(PUBLISH) and values['author_id'] != member.author_id:
        abort(403)
    if values['author_id'] and db.session.get(Author, values['author_id']) is None:
        raise ValueError('Seleccione uma autoria existente.')
    if values['category_id'] and db.session.get(Category, values['category_id']) is None:
        raise ValueError('Seleccione um tema existente.')

    values['image'] = validate_link(values['image']) if values['image'] else ''
    if values['evidence'] and values['evidence'] not in EVIDENCE_LABELS:
        raise ValueError('Seleccione um estado de evidência válido.')
    values['africa_focus'] = request.form.get('africa_focus') == 'yes'
    lines = [line.strip() for line in values.pop('sources_text').splitlines() if line.strip()]
    if len(lines) > 20:
        raise ValueError('Adicione até 20 fontes.')
    values['sources'] = []
    for line in lines:
        label, separator, url = line.rpartition('|')
        url = validate_link(url.strip())
        label = label.strip() if separator else ''
        if len(label) > 240:
            raise ValueError('O título da fonte excede 240 caracteres.')
        values['sources'].append({'label': label, 'url': url})

    related_slug = values.pop('related_slug')
    related = Article.query.filter_by(slug=related_slug).first() if related_slug else None
    if related_slug and related is None:
        raise ValueError('O identificador do artigo relacionado não existe.')
    values['related_article_id'] = related.id if related else None
    return values


def validate_link(url):
    if not url or any(character.isspace() or character == '\\' for character in url):
        raise ValueError('Indique uma ligação HTTPS válida por fonte, sem espaços nem credenciais.')
    return safe_url(url)


PUBLICATION_REQUIRED_FIELDS = (
    ('title', 'Título', 'news-title'),
    ('summary', 'Resumo', 'news-summary'),
    ('body', 'Texto da notícia', 'news-body'),
    ('author_id', 'Autoria', 'news-author'),
    ('sources', 'Fontes', 'news-sources-text'),
)


def publication_missing_fields(item):
    """Return the missing public fields without altering the draft or its metadata."""
    missing = [(label, field_id) for name, label, field_id in PUBLICATION_REQUIRED_FIELDS
               if not getattr(item, name)]
    if not item.slug:
        missing.append(('Identificador da rota', 'news-slug'))
    if item.image and not item.image_alt:
        missing.append(('Texto alternativo da capa', 'news-image-alt'))
    return missing


def validate_publication(item):
    missing = publication_missing_fields(item)
    if missing:
        labels = ', '.join(label for label, _ in missing)
        raise ValueError('Antes de publicar, preencha: ' + labels + '.')

    # As reservas científicas são apresentadas no corpo editorial da notícia;
    # a nota separada deixou de ser exigida no formulário.
    if item.language == 'en':
        from internationalization import interface_translation

        theme = db.session.get(Category, item.category_id)
        if theme is not None and not interface_translation(theme.name):
            raise ValueError('Publique a tradução inglesa do nome do tema em Internacionalização antes de publicar esta versão.')


def handle_integrity_error():
    db.session.rollback()
    abort(409, description='Conflito de edição. Confirme se já existe uma versão no idioma, um identificador igual ou um destaque concorrente.')


@admin_bp.get('/noticias')
def news_index():
    require_news_access()
    member = current_member()
    page = editorial_scope(member).order_by(NewsVersion.updated_at.desc(), NewsVersion.id.desc()).paginate(
        page=pagination_page(), per_page=30, error_out=False,
    )
    return render_template('admin/news_index.html', rows=page, statuses=STATUSES,
                           can_create=can_edit(None, member), is_scheduled=is_scheduled,
                           news_page_published=sum(item.status == 'published' and not is_scheduled(item)
                                                   for item in page.items),
                           news_page_scheduled=sum(is_scheduled(item) for item in page.items))


@admin_bp.route('/noticias/nova', methods=['GET', 'POST'])
@admin_bp.route('/noticias/grupo/<int:story_id>/nova', methods=['GET', 'POST'])
@admin_bp.route('/noticias/<int:ident>', methods=['GET', 'POST'])
def news_form(story_id=None, ident=None):
    require_news_access()
    member = current_member()
    item = None
    if ident:
        query = editorial_scope(member).filter_by(id=ident)
        item = query.with_for_update().first_or_404() if request.method == 'POST' else query.first_or_404()
        story_id = item.story_id

    versions = editorial_scope(member).filter_by(story_id=story_id).order_by(NewsVersion.language).all() if story_id else []
    if not item and story_id and not versions:
        abort(404)
    editable = can_edit(item, member)
    if not item and not editable:
        abort(403)
    error = None
    if request.method == 'POST':
        validate_csrf()
        if item and request.form.get('revision') != str(item.revision):
            abort(409, description='Este registo mudou. Volte a abrir a notícia antes de guardar.')
        try:
            action = request.form.get('action')
            if action == 'save':
                if not editable:
                    abort(403)
                item = save_version(item, story_id, member)
            elif item:
                transition(item, member, action)
            else:
                abort(400)
            audit_detail = f'{item.language.upper()} · {item.title}'
            if action in {'reviewed', 'changes'}:
                audit_detail += f' · {item.review_note}'
            audit('news.' + action, 'news_version', item.id, audit_detail)
            db.session.commit()
            flash('Notícia actualizada.', 'success')
            return redirect(url_for('admin.news_form', ident=item.id), 303)
        except ValueError as exc:
            db.session.rollback()
            error = str(exc)
        except (IntegrityError, StaleDataError):
            handle_integrity_error()
    reviewers = [
        candidate for candidate in eligible(REVIEW)
        if item and candidate.available and (not item.author_id or candidate.author_id != item.author_id)
        and candidate.admin_id != item.edited_by
    ] if item and has_permission(EDIT) else []
    return render_template(
        'admin/news_form.html', item=item, error=error, editable=editable,
        versions=versions, statuses=STATUSES, reviewers=reviewers,
        can_review=item and assigned_reviewer(item, member), can_add=bool(story_id and can_edit(None, member)),
        authors=Author.query.order_by(Author.name).all(), themes=Category.query.order_by(Category.name).all(),
        evidence_labels=EVIDENCE_LABELS, is_scheduled=is_scheduled,
        schedule_zones=SCHEDULE_ZONES, schedule_form=scheduling_form_values(item),
        publication_missing=publication_missing_fields(item) if error and item
                            and request.form.get('action') in {'publish', 'approve', 'schedule'} else [],
    ), 400 if error else 200


def save_version(item, story_id, member):
    values = read_fields(member)
    # Campo retirado do editor: conservar qualquer nota já guardada.
    if item is not None and 'evidence_note' not in request.form:
        values['evidence_note'] = item.evidence_note or ''
    if item is None:
        locale = request.form.get('language')
        if locale not in {'pt', 'en'}:
            raise ValueError('Escolha português ou inglês.')
        if story_id is None:
            story = NewsStory()
            db.session.add(story)
            db.session.flush()
            story_id = story.id
        item = NewsVersion(story_id=story_id, language=locale, status='draft')
        db.session.add(item)

    image_file = request.files.get('image_file')
    if image_file and image_file.filename:
        if not values['image_alt']:
            raise ValueError('Acrescente texto alternativo à imagem de capa.')
        values['image'] = upload_article_image(image_file)
    changed = any(getattr(item, key) != value for key, value in values.items())
    for key, value in values.items():
        setattr(item, key, value)
    if item.status == 'published':
        validate_publication(item)
        if changed:
            item.revised_at = utcnow()
    elif changed:
        item.status = 'draft'
        item.reviewer_id = None
        item.review_note = ''
    if changed:
        item.edited_by = session.get('admin_id')
    db.session.flush()
    return item


def transition(item, member, action):
    if action == 'assign':
        require(EDIT)
        if item.status not in {'draft', 'review', 'reviewed', 'approved', 'withdrawn'}:
            abort(409)
        reviewer_id = database_id(request.form.get('reviewer_id'))
        reviewer = next((candidate for candidate in eligible(REVIEW) if candidate.id == reviewer_id), None)
        if not reviewer or not reviewer.available or (item.author_id and reviewer.author_id == item.author_id) or reviewer.admin_id == item.edited_by:
            raise ValueError('Escolha um revisor disponível, com mandato activo e independente da autoria e da edição.')
        item.reviewer_id, item.status, item.review_note = reviewer.id, 'review', ''
        return

    if action in {'reviewed', 'changes'}:
        if not assigned_reviewer(item, member) or (item.author_id and member.author_id == item.author_id) or member.admin_id == item.edited_by:
            abort(403)
        if item.status != 'review':
            abort(409)
        note = request.form.get('review_note', '').strip()
        if not 1 <= len(note) <= 4000:
            raise ValueError('Registe o parecer editorial, até 4 000 caracteres.')
        item.review_note = note
        item.status = 'reviewed' if action == 'reviewed' else 'draft'
        return

    if action == 'approve':
        require(APPROVE)
        if item.status != 'reviewed':
            abort(409)
        if member and (member.author_id == item.author_id or member.id == item.reviewer_id):
            abort(403)
        if not item.reviewer or not has_permission(REVIEW, member=item.reviewer):
            raise ValueError('A revisão deixou de ter um mandato válido. Atribua uma nova revisão.')
        validate_publication(item)
        item.status = 'approved'
        return

    require(PUBLISH)
    if action in {'schedule', 'cancel_schedule'}:
        if action == 'cancel_schedule':
            if not is_scheduled(item):
                abort(409)
            item.status = 'draft'
            item.featured = False
            item.published_at = None
            return
        if not (item.status == 'approved' or is_scheduled(item)
                or (session.get('admin_superuser') and item.status in {'draft', 'reviewed', 'withdrawn'})):
            abort(409)
        validate_publication(item)
        item.published_at = parse_schedule()
        item.status = 'published'
        item.featured = False
        return
    if action == 'publish' and (item.status == 'approved' or is_scheduled(item) or (
        session.get('admin_superuser') and item.status in {'draft', 'reviewed', 'withdrawn'}
    )):
        validate_publication(item)
        was_public = item.published_at and item.published_at <= utcnow()
        item.status = 'published'
        if was_public:
            item.revised_at = utcnow()
        else:
            item.published_at = utcnow()
    elif action == 'withdraw' and item.status == 'published':
        item.featured, item.status = False, 'withdrawn'
    elif action in {'feature', 'unfeature'} and item.status == 'published':
        if action == 'feature' and not item.featured:
            NewsVersion.query.filter_by(language=item.language, featured=True).update(
                {NewsVersion.featured: False, NewsVersion.revision: NewsVersion.revision + 1},
                synchronize_session=False,
            )
        item.featured = action == 'feature'
    else:
        abort(409)
