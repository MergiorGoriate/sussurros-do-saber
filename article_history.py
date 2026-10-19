"""Private article revisions and explicit draft restoration."""
from difflib import unified_diff
from datetime import timedelta
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for, jsonify
from admin import login_required, validate_csrf, enforce_admin_authentication, protect_admin_responses
from models import Article, db, utcnow
from governance_models import ArticleRevision, ArticleWorkflow
from extensions import limiter

history_bp = Blueprint('article_history', __name__, url_prefix='/admin/artigos')
history_bp.before_request(enforce_admin_authentication)
history_bp.after_request(protect_admin_responses)
CONTENT_FIELDS = ('title', 'summary', 'body', 'references', 'keywords', 'doi', 'image', 'cover_video', 'read_minutes', 'featured')
FIELD_LABELS = {'title':'Título', 'summary':'Resumo', 'body':'Texto', 'references':'Referências', 'keywords':'Palavras-chave', 'doi':'DOI', 'image':'Imagem de capa', 'cover_video':'Vídeo de capa', 'read_minutes':'Tempo de leitura', 'featured':'Destaque'}


def snapshot(article):
    return {name: getattr(article, name) for name in CONTENT_FIELDS}


def record_revision(article, *, content=None, reason='Alteração editorial', baseline=False, created_at=None):
    content = content if content is not None else snapshot(article)
    latest = ArticleRevision.query.filter_by(article_id=article.id).order_by(ArticleRevision.number.desc()).first()
    if latest and latest.snapshot == content:
        return latest
    item = ArticleRevision(article_id=article.id, number=latest.number+1 if latest else 1,
        snapshot=content, actor_id=None if baseline else session.get('admin_id'),
        actor_name='Alteração anterior sem responsável registado' if baseline else session.get('admin_username', 'Administrador principal'),
        reason=reason, created_at=created_at or utcnow())
    db.session.add(item)
    db.session.flush()
    return item


def permitted_article(ident, *, lock=False):
    from governance import article_edit_access
    query = Article.query.filter_by(id=ident)
    article = query.with_for_update().populate_existing().first_or_404() if lock else query.first_or_404()
    article_edit_access(article)
    return article


def bounded_diff(old, new):
    # Content can be 400 KB; keep comparison work and HTML bounded.
    before = str(old if old is not None else '')[:20000].splitlines()[:400]
    after = str(new if new is not None else '')[:20000].splitlines()[:400]
    lines = list(unified_diff(before, after, fromfile='Versão seleccionada', tofile='Comparação', lineterm=''))[:800]
    return '\n'.join(lines) or 'Sem diferenças neste excerto.'


@history_bp.get('/<int:ident>/historico')
@login_required
def history(ident):
    article = permitted_article(ident)
    revisions = ArticleRevision.query.filter_by(article_id=ident).order_by(ArticleRevision.number.desc())
    pagination = revisions.paginate(page=request.args.get('page', 1, type=int), per_page=20, error_out=False)
    version_id = request.args.get('version', type=int)
    selected = revisions.filter_by(id=version_id).first_or_404() if version_id else (pagination.items[0] if pagination.items else None)
    against_id = request.args.get('against', type=int)
    against = revisions.filter_by(id=against_id).first_or_404() if against_id else None
    current = against.snapshot if against else snapshot(article)
    changes = []
    if selected:
        for field in CONTENT_FIELDS:
            old, new = selected.snapshot.get(field), current.get(field)
            if old != new:
                changes.append((FIELD_LABELS[field], bounded_diff(old, new)))
    return render_template('admin/article_history.html', article=article, pagination=pagination,
                           selected=selected, against=against, changes=changes)


@history_bp.post('/<int:ident>/historico/<int:revision_id>/recuperar')
@login_required
def restore(ident, revision_id):
    validate_csrf()
    article = permitted_article(ident, lock=True)
    revision = ArticleRevision.query.filter_by(article_id=ident, id=revision_id).first_or_404()
    if request.form.get('confirm') != 'yes':
        abort(400, description='Confirme a recuperação da versão como rascunho.')
    if request.form.get('version_token') != article.updated_at.isoformat():
        abort(409, description='O artigo mudou entretanto. Abra novamente o histórico antes de recuperar a versão.')
    from governance import article_save_guard, audit
    record_revision(article, reason='Antes da recuperação')
    article_save_guard(article, 'draft', article.author_id)
    for field in CONTENT_FIELDS:
        if field in revision.snapshot:
            setattr(article, field, revision.snapshot[field])
    article.status = 'draft'
    article.scheduled_at = None
    article.updated_at = utcnow()
    record_revision(article, reason=f'Recuperada a versão {revision.number}')
    audit('article.restored', 'article', ident, f'Versão {revision.number}; exige nova revisão.')
    db.session.commit()
    flash('Versão recuperada como rascunho. Submeta o artigo a nova revisão antes de publicar.', 'success')
    return redirect(url_for('admin.article_form', article_id=ident), code=303)


AUTOSAVE_LIMITS = {'title':240, 'summary':2000, 'body':400000, 'references':100000, 'keywords':500, 'doi':180}


@history_bp.post('/<int:ident>/rascunho')
@login_required
@limiter.limit('12 per minute', key_func=lambda: str(session.get('admin_id') or session.get('admin_username')), override_defaults=True)
def autosave(ident):
    validate_csrf()
    if request.content_length and request.content_length > 8000000:
        abort(413)
    article = permitted_article(ident, lock=True)
    workflow = db.session.get(ArticleWorkflow, ident)
    if article.status != 'draft' or (workflow and workflow.stage not in {'draft', 'changes'}):
        return jsonify(ok=False, code='state', error='A gravação automática só está disponível em rascunhos. Guarde manualmente como rascunho para continuar.'), 409
    if not request.form.get('version_token') or request.form['version_token'] != article.updated_at.isoformat():
        return jsonify(ok=False, code='conflict', error='O artigo foi alterado noutra sessão. O seu texto continua no editor. Consulte o histórico antes de voltar a guardar.'), 409
    if request.files or any(name not in request.form for name in (*AUTOSAVE_LIMITS, 'read_minutes')):
        return jsonify(ok=False, code='validation', error='O pedido de gravação está incompleto.'), 400
    values = {name:request.form[name].strip() for name in AUTOSAVE_LIMITS}
    if any(len(values[name]) > limit for name,limit in AUTOSAVE_LIMITS.items()) or len(values['title']) < 5 or len(values['summary']) < 10:
        return jsonify(ok=False, code='validation', error='Reveja o título, o resumo e os limites dos campos antes de guardar.'), 422
    try:
        values['read_minutes'] = int(request.form['read_minutes'])
        if not 1 <= values['read_minutes'] <= 120:
            raise ValueError()
    except (ValueError,TypeError):
        return jsonify(ok=False, code='validation', error='O tempo de leitura deve estar entre 1 e 120 minutos.'), 422
    previous = snapshot(article)
    previous_time = article.updated_at
    if any(previous[name] != value for name,value in values.items()):
        now = max(utcnow(), previous_time + timedelta(microseconds=1))
        # The predicate also protects SQLite, where SELECT FOR UPDATE is ignored.
        changed = Article.query.filter_by(id=ident, status='draft', updated_at=previous_time).update(
            dict(values, updated_at=now), synchronize_session=False)
        if changed != 1:
            db.session.rollback()
            return jsonify(ok=False, code='conflict', error='O artigo mudou entretanto. O seu texto continua no editor.'), 409
        db.session.refresh(article)
        from governance import article_save_guard
        article_save_guard(article, 'draft', article.author_id)
        if not ArticleRevision.query.with_entities(ArticleRevision.id).filter_by(article_id=ident).first():
            record_revision(article, content=previous, baseline=True,
                            reason='Conteúdo anterior ao primeiro registo', created_at=previous_time)
        record_revision(article, reason='Gravação automática de rascunho')
        db.session.commit()
    return jsonify(ok=True, version_token=article.updated_at.isoformat(), saved_at=article.updated_at.isoformat())
