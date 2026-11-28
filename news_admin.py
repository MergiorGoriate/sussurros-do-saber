"""Editorial workflow for each language of a science news story."""
from datetime import datetime, timezone
import re

import markdown
from bs4 import BeautifulSoup
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
    values['sources'] = parse_news_sources(values.pop('sources_text'))

    related_slug = values.pop('related_slug')
    related = Article.query.filter_by(slug=related_slug).first() if related_slug else None
    if related_slug and related is None:
        raise ValueError('O identificador do artigo relacionado não existe.')
    values['related_article_id'] = related.id if related else None
    return values



def parse_news_sources(raw):
    """Import a plain or Markdown bibliography without importing HTML anchors."""
    sources = []
    credits = False
    # Some editors copy Markdown as escaped text rather than as raw Markdown.
    escaped_paste = r'\<a id=' in raw or r'\]\(' in raw or r'\## ' in raw
    if escaped_paste:
        raw = re.sub(r"\\([\*_[\](){}<>#!.:-])", r"\1", raw)
    for number, original in enumerate(raw.splitlines(), 1):
        line = original.strip()
        if escaped_paste and line.endswith('\\'):
            line = line[:-1].rstrip()
        if not line or re.fullmatch(r'<a\s+id=["\'][\w-]+["\']\s*>\s*</a>', line, re.IGNORECASE):
            continue
        heading = re.fullmatch(r'#{1,6}\s+(.+)', line)
        if heading:
            credits = 'créditos' in heading.group(1).casefold() or 'image credits' in heading.group(1).casefold()
            continue
        marker = re.match(r'^(?:[-*+]\s+|\d+[.)]\s+)', line)
        # A credit section may have a prose introduction above its list.
        if (credits and not marker and line.casefold().startswith(('as imagens ', 'the images '))
                and not re.search(r'://|\]\(|\bdoi:|\b10\.\d{4,9}/', line, re.IGNORECASE)):
            continue
        if marker:
            line = line[marker.end():].strip()
        if not line:
            continue
        try:
            sources.append(parse_markdown_news_source(line) if re.search(r'\]\(', line) else parse_news_source(line))
            if credits:
                credits = False
            if len(sources) > 40:
                raise ValueError('Adicione até 40 referências, uma por linha.')
        except ValueError as error:
            raise ValueError(f'Fontes, linha {number}: {error}') from error
    return sources


def parse_markdown_news_source(line):
    """Keep the first link and any additional named links in one source entry."""
    document = BeautifulSoup(markdown.markdown(line), 'html.parser')
    anchors = document.find_all('a', href=True)
    if not anchors:
        raise ValueError('Utilize uma ligação Markdown válida: [texto](https://…).')
    links = []
    for anchor in anchors:
        target = anchor['href']
        # Reuse the same validation for every link, including supplementary ones.
        url = source_link_or_doi(target)
        if not url:
            raise ValueError('Utilize uma ligação HTTPS válida ou um DOI em cada ligação Markdown.')
        title = anchor.get_text(' ', strip=True)
        links.append({'label': title if title and title != url else '', 'url': url})
        anchor.decompose()
    label = document.get_text(' ', strip=True)
    # Drop separators left by removing link nodes, retaining bibliographic punctuation.
    label = re.sub(r'\s+([.,;:])', r'\1', label).strip(' |')
    label = re.sub(r'\.{2,}$', '.', label)
    if links[0]['label'] and '://' not in links[0]['label']:
        title = links[0]['label']
        if not label:
            label = title
        elif title not in label:
            label = f'{label.rstrip(".")}. {title}'
    if '://' in label:
        raise ValueError('Indique as ligações adicionais em Markdown: [texto](https://…).')
    if len(label) > 1500 or any(len(link['label']) > 1500 for link in links):
        raise ValueError('Uma referência excede 1 500 caracteres.')
    result = {'label': label, 'url': links[0]['url']}
    if len(links) > 1:
        result['links'] = links[1:]
    return result


def format_news_sources(sources):
    """Re-create editable plain text, retaining supplementary links on save."""
    lines = []
    for source in sources:
        label, url = source.get('label', ''), source.get('url', '')
        if source.get('links'):
            # Markdown syntax is generated only as editor text, never as rendered HTML.
            def escaped(text):
                return re.sub(r'([\\*_[\]<>])', r'\\\1', text)
            extras = ' '.join(f"[{escaped(link['label'] or link['url'])}](<{link['url']}>)"
                              for link in source['links'])
            lines.append(f'{escaped(label)} [{escaped(url)}](<{url}>) {extras}'.strip())
        else:
            lines.append(' | '.join(part for part in (label, url) if part))
    return '\n'.join(lines)


def source_link_or_doi(value):
    value = value.strip()
    if re.fullmatch(r'(?:doi:\s*)?10\.\d{4,9}/[^\s<>|]+', value, flags=re.IGNORECASE):
        doi = re.sub(r'^doi:\s*', '', value, flags=re.IGNORECASE)
        return validate_link('https://doi.org/' + doi)
    if value.lower().startswith(('http:', 'https:', 'www.', 'doi:')):
        return validate_link(value)
    return None


def parse_news_source(line):
    """Accept a bibliographic reference, optionally with a validated HTTPS link or DOI.

    Retain the existing JSON representation for previously saved URL-only sources.
    Never turn untrusted free text into a hyperlink.
    """
    label, separator, suffix = line.rpartition('|')
    if separator:
        target = source_link_or_doi(suffix)
        if target is None:
            raise ValueError('Depois de «|» indique um DOI ou ligação HTTPS válida.')
        text = label.strip()
        if not text:
            raise ValueError('Escreva a referência antes de «|».')
        if len(text) > 1500:
            raise ValueError('Uma referência excede 1 500 caracteres.')
        return {'label': text, 'url': target}

    target = source_link_or_doi(line)
    if target:
        return {'label': '', 'url': target}

    # Recognise a bibliographic reference followed by an HTTPS URL.
    embedded = re.search(r'https://[^\s<>"|]+$', line, flags=re.IGNORECASE)
    if embedded and embedded.start() > 0:
        label = line[:embedded.start()].strip()
        if label and len(label) <= 1500 and "://" not in label:
            return {"label": label, "url": validate_link(embedded.group(0))}

    if len(line) > 1500:
        raise ValueError("Uma referência excede 1 500 caracteres.")
    if line.startswith(("http://", "https://")) or "://" in line:
        raise ValueError("Utilize uma ligação HTTPS válida, um DOI ou uma referência bibliográfica.")
    return {"label": line, "url": ""}


def validate_link(url):
    if not url or any(character.isspace() or character == '\\' for character in url):
        raise ValueError('Indique uma ligação HTTPS válida por fonte, sem espaços nem credenciais.')
    return safe_url(url)


PUBLICATION_REQUIRED_FIELDS = (
    ('title', 'Título', 'news-title'),
    ('summary', 'Resumo', 'news-summary'),
    ('body', 'Texto da notícia', 'news-body'),
    ('author_id', 'Autoria', 'news-author'),
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
            elif item and action == 'translate_en':
                item = generate_english_draft(item, member)
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
        formatted_sources=format_news_sources(item.sources) if item else '',
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



def generate_english_draft(item, member):
    """Translate a saved Portuguese news version into a separate, unpublished English draft."""
    from dissemination_ai import GenerationError
    from translation_service import translate, configured

    if item.language != 'pt' or not can_edit(item, member):
        abort(403)
    if NewsVersion.query.filter_by(story_id=item.story_id, language='en').first():
        raise ValueError('Já existe uma versão inglesa. Abra-a para a editar; não será substituída.')
    if not item.title.strip() or not item.body.strip():
        raise ValueError('Guarde primeiro o título e o texto da notícia em português.')
    if not configured():
        raise ValueError('O serviço de tradução dos artigos ainda não está configurado.')
    original = {
        'title': item.title, 'summary': item.summary or '',
        'body': item.body, 'image_alt': item.image_alt or '',
    }
    try:
        translated, report = translate(original)
    except GenerationError as exc:
        raise ValueError(str(exc)) from exc
    if not report.get('ready'):
        raise ValueError('A revisão automática detectou problemas na tradução. Corrija o original e tente novamente.')
    english_slug = slugify(translated['title'])[:145].strip('-') or ('news-' + str(item.story_id))
    if NewsVersion.query.filter_by(language='en', slug=english_slug).first():
        english_slug = (english_slug[:140].rstrip('-') + '-' + str(item.story_id))[:160]
    english = NewsVersion(
        story_id=item.story_id, language='en', status='draft',
        slug=english_slug, title=translated['title'], summary=translated['summary'],
        body=translated['body'], image_alt=translated['image_alt'],
        author_id=item.author_id, category_id=item.category_id,
        image=item.image, image_credit=item.image_credit,
        sources=item.sources, evidence=item.evidence, evidence_note=item.evidence_note,
        africa_focus=item.africa_focus, related_article_id=item.related_article_id,
        edited_by=session.get('admin_id'),
    )
    db.session.add(english)
    db.session.flush()
    return english


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
