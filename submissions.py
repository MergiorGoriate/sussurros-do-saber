"""Authenticated submission workflow and editorial administration."""
import io
import json
import os
import re
import secrets
import smtplib
from datetime import datetime
from email.message import EmailMessage
from functools import wraps
import click
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, session, url_for
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import func
from sqlalchemy.orm import defer
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash
from admin import admin_bp, admin_session_valid, login_required, validate_csrf
from extensions import limiter
from models import AdminUser, Journal, db, utcnow
from journal_metadata import normalize_orcid, legacy_author_lines
from journal_article import ARTICLE_FIELD_LIMITS
from PIL import Image
from submission_models import (Researcher, SubmissionSetting, Manuscript, ManuscriptAuthor, ManuscriptVersion,
                               ManuscriptFile, EditorialEvent, EditorialNotification, PublicationAsset)
from submission_uploads import KINDS, MIMES, validate_upload, docx_markdown

submissions_bp = Blueprint('submissions', __name__, url_prefix='/submissoes')
STATES = {'draft': 'Rascunho', 'submitted': 'Submetido', 'screening': 'Triagem editorial',
          'review': 'Em revisão', 'revision_requested': 'Revisões solicitadas', 'revised': 'Manuscrito revisto',
          'reevaluation': 'Reavaliação', 'accepted': 'Aceite', 'rejected': 'Rejeitado',
          'production': 'Produção editorial', 'published': 'Publicado'}
TRANSITIONS = {'submitted': ('screening', 'rejected'), 'screening': ('review', 'revision_requested', 'accepted', 'rejected'),
               'review': ('revision_requested', 'accepted', 'rejected'), 'revision_requested': ('rejected',),
               'revised': ('reevaluation', 'review', 'accepted', 'rejected'),
               'reevaluation': ('review', 'revision_requested', 'accepted', 'rejected'),
               'accepted': (), 'production': (), 'published': (), 'rejected': (), 'draft': ()}
DUMMY_PASSWORD_HASH = generate_password_hash('unavailable-account')
SCIENTIFIC_FIELDS = {'content_markdown': ('Conteúdo do artigo (Markdown)', 400000),
                     'references': ('Referências bibliográficas', 100000),
                     'author_contributions': ('Contribuição dos autores', 20000),
                     'acknowledgements': ('Agradecimentos', 20000), 'notes': ('Notas', 20000)}
STEPS = ('Revista e tipo', 'Autores', 'Informações', 'Ficheiros', 'Declarações', 'Revisão', 'Submissão')
AUTHOR_FIELDS = {'name': ('Nome completo', 180), 'email': ('E-mail', 254), 'orcid': ('ORCID', 180),
                 'affiliation': ('Afiliação', 300), 'department': ('Departamento', 180),
                 'institution': ('Instituição', 300), 'city': ('Cidade', 140), 'country': ('País', 140)}
INFO_FIELDS = {'title': ('Título', 300), 'summary': ('Resumo', 20000), 'keywords': ('Palavras-chave', 2000),
               'abstract': ('Abstract', 20000), 'abstract_keywords': ('Keywords', 2000),
               'editor_comments': ('Comentários ao editor', 20000)}
REQUIRED_DECLARATIONS = {'original': 'O manuscrito é original.', 'exclusive': 'Não está submetido a outra revista.',
                         'authors_agree': 'Todos os autores concordam com a submissão.',
                         'policies': 'Li e aceito as Políticas Editoriais.', 'guidelines': 'Li as Diretrizes para Autores.'}
OPTIONAL_DECLARATIONS = {'conflicts': 'Conflitos de interesse', 'funding': 'Financiamento',
                         'ethics': 'Aprovação ética', 'consent': 'Consentimento informado', 'data': 'Disponibilidade de dados'}


def email_valid(value):
    return bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value)) and len(value) <= 254


def researcher():
    account = db.session.get(Researcher, session.get('researcher_id')) if session.get('researcher_id') else None
    return account if account and account.active and session.get('researcher_nonce') == account.token_nonce else None


def editorial_access(manuscript=None):
    if not admin_session_valid():
        return False
    account = db.session.get(AdminUser, session.get('admin_id')) if session.get('admin_id') else None
    if account is not None and not (account.two_factor_enabled and session.get('admin_2fa_verified') is True):
        return False
    from governance import manuscript_access, has_permission
    return manuscript_access(manuscript) if manuscript else has_permission('manuscript.read')


def author_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not researcher():
            return redirect(url_for('submissions.login'))
        if not researcher().verified:
            return redirect(url_for('submissions.verify_notice'))
        return view(*args, **kwargs)
    return wrapped


@submissions_bp.after_request
def private_headers(response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@submissions_bp.app_context_processor
def context():
    return dict(researcher=researcher(), states=STATES, steps=STEPS, author_fields=AUTHOR_FIELDS,
                info_fields=INFO_FIELDS, scientific_fields=SCIENTIFIC_FIELDS, required_declarations=REQUIRED_DECLARATIONS,
                optional_declarations=OPTIONAL_DECLARATIONS, file_kinds=KINDS)


def notify(recipient, subject, body):
    if email_valid(recipient):
        db.session.add(EditorialNotification(recipient=recipient, subject=re.sub(r'[\r\n]+', ' ', subject)[:300], body=body))


def account_token(account, purpose):
    return URLSafeTimedSerializer(current_app.secret_key, salt='researcher-' + purpose).dumps([account.id, account.token_nonce])


def token_account(token, purpose):
    try:
        ident, nonce = URLSafeTimedSerializer(current_app.secret_key, salt='researcher-' + purpose).loads(token, max_age=3600 if purpose == 'reset' else 86400)
        account = db.session.get(Researcher, ident)
        if not account or not account.active or nonce != account.token_nonce:
            raise ValueError()
        return account
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        abort(400, description='Ligação inválida ou expirada. Solicite uma nova ligação.')


def account_link(account, purpose):
    origin = os.getenv('SITE_URL', 'https://www.sussurrosdosaber.com').rstrip('/')
    endpoint = 'submissions.verify' if purpose == 'verify' else 'submissions.reset_password'
    return origin + url_for(endpoint, token=account_token(account, purpose))


@submissions_bp.route('/criar-conta', methods=['GET', 'POST'])
@limiter.limit('5 per hour')
def register():
    if request.method == 'POST':
        validate_csrf()
        name, email = (request.form.get(key, '').strip() for key in ('name', 'email'))
        password = request.form.get('password', '')
        if not 2 <= len(name) <= 180 or not email_valid(email.lower()) or not 12 <= len(password) <= 128:
            flash('Informe nome, e-mail válido e uma palavra-passe com 12 a 128 caracteres.', 'error')
        else:
            account = Researcher(name=name, email=email.lower(), password_hash=generate_password_hash(password), token_nonce=secrets.token_hex(24))
            try:
                db.session.add(account)
                db.session.flush()
                notify(account.email, 'Confirme a conta de autor', 'Confirme a sua conta em até 24 horas:\n' + account_link(account, 'verify'))
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
            flash('Se este e-mail puder ser registado, receberá uma ligação de confirmação. Se já tem conta, entre ou recupere a palavra-passe.', 'success')
            return redirect(url_for('submissions.login'))
    return render_template('submissions/auth.html', mode='register')


@submissions_bp.route('/entrar', methods=['GET', 'POST'])
@limiter.limit('10 per 15 minutes')
def login():
    if request.method == 'POST':
        validate_csrf()
        email = request.form.get('email', '').strip().lower()[:254]
        password = request.form.get('password', '')[:129]
        account = Researcher.query.filter_by(email=email, active=True).first()
        # Fixed cost for unknown users reduces account-enumeration timing differences.
        valid = check_password_hash(account.password_hash if account and account.password_hash else DUMMY_PASSWORD_HASH, password)
        if account and account.password_hash and valid:
            session.clear()
            session.permanent = True
            session['researcher_id'] = account.id
            session['researcher_nonce'] = account.token_nonce
            return redirect(url_for('submissions.mine' if account.verified else 'submissions.verify_notice'))
        flash('E-mail ou palavra-passe incorretos.', 'error')
    return render_template('submissions/auth.html', mode='login')


@submissions_bp.post('/sair')
def logout():
    validate_csrf()
    session.clear()
    session['google_prompt_suppressed'] = True
    return redirect(url_for('journals'))


@submissions_bp.route('/confirmacao', methods=['GET', 'POST'])
@limiter.limit('4 per hour')
def verify_notice():
    account = researcher()
    if not account:
        return redirect(url_for('submissions.login'))
    if request.method == 'POST':
        validate_csrf()
        notify(account.email, 'Confirme a conta de autor', 'Confirme a sua conta:\n' + account_link(account, 'verify'))
        db.session.commit()
        flash('Ligação de confirmação solicitada.', 'success')
    return render_template('submissions/auth.html', mode='verify')


@submissions_bp.route('/confirmar/<token>', methods=['GET', 'POST'])
def verify(token):
    account = token_account(token, 'verify')
    if request.method == 'POST':
        validate_csrf()
        account.verified = True
        db.session.commit()
        flash('Conta confirmada. Pode entrar e submeter o manuscrito.', 'success')
        return redirect(url_for('submissions.login'))
    return render_template('submissions/auth.html', mode='confirm')


@submissions_bp.route('/recuperar', methods=['GET', 'POST'])
@limiter.limit('4 per hour')
def forgot_password():
    if request.method == 'POST':
        validate_csrf()
        account = Researcher.query.filter_by(email=request.form.get('email', '').strip().lower()[:254], active=True).first()
        if account and account.password_hash:
            notify(account.email, 'Recuperar palavra-passe', 'Ligação válida por uma hora:\n' + account_link(account, 'reset'))
            db.session.commit()
        flash('Se existir uma conta, receberá uma ligação de recuperação.', 'success')
        return redirect(url_for('submissions.login'))
    return render_template('submissions/auth.html', mode='forgot')


@submissions_bp.route('/recuperar/<token>', methods=['GET', 'POST'])
@limiter.limit('10 per hour')
def reset_password(token):
    account = token_account(token, 'reset')
    if not account.password_hash:
        abort(400)
    if request.method == 'POST':
        validate_csrf()
        password = request.form.get('password', '')
        if not 12 <= len(password) <= 128:
            flash('Use uma palavra-passe com 12 a 128 caracteres.', 'error')
        else:
            account.password_hash = generate_password_hash(password)
            account.token_nonce = secrets.token_hex(24)
            db.session.commit()
            session.clear()
            flash('Palavra-passe atualizada. Entre novamente.', 'success')
            return redirect(url_for('submissions.login'))
    return render_template('submissions/auth.html', mode='reset')


def owned(ident, lock=False):
    account = researcher()
    manuscript = db.get_or_404(Manuscript, ident)
    if manuscript.removed_at:abort(410,description='A submissão foi eliminada e mantém apenas o histórico.')
    if not account or manuscript.owner_id != account.id:
        abort(404)
    if lock:
        lock_record(manuscript)
    return manuscript


def lock_record(manuscript):
    # Acquire a write lock before inspecting state, also on SQLite.
    db.session.execute(db.update(Manuscript).where(Manuscript.id == manuscript.id).values(updated_at=Manuscript.updated_at))
    db.session.refresh(manuscript)
    return manuscript


def event(manuscript, action, new_status=None, note='', visible=False):
    previous = manuscript.status
    if new_status:
        manuscript.status = new_status
    actor = ('admin:' + str(session.get('admin_id') or session.get('admin_username') or 'principal')) if request.path.startswith('/admin') else 'autor:' + str(manuscript.owner_id)
    db.session.add(EditorialEvent(manuscript_id=manuscript.id, previous_status=previous, new_status=manuscript.status,
                                 action=action, actor=actor, note=note, visible_to_author=visible))
    if action in {'submitted','revision_submitted','editor_assigned','decision','published','prepared_for_publication','publication_hidden','internal_note'}:
        from internal_notices import dispatch
        dispatch('manuscript.'+('revised' if action=='revision_submitted' else action),'manuscript',manuscript.id)


def types_for(setting):
    return [line.strip() for line in (setting.article_types or '').splitlines() if line.strip()]


def version_for(manuscript):
    return ManuscriptVersion.query.filter_by(manuscript_id=manuscript.id, number=manuscript.current_version).one()


def files_for(manuscript):
    return ManuscriptFile.query.options(defer(ManuscriptFile.payload)).join(ManuscriptVersion).filter(ManuscriptVersion.manuscript_id == manuscript.id).order_by(ManuscriptVersion.number, ManuscriptFile.id).all()


def snapshot(manuscript):
    return {**{key: getattr(manuscript, key) for key in INFO_FIELDS},
            'journal_id': manuscript.journal_id, 'article_type': manuscript.article_type, 'field': manuscript.field,
            'language': manuscript.language, 'declarations': manuscript.declarations, 'scientific_details': manuscript.scientific_details,
            'authors': [{**{key: getattr(author, key) for key in AUTHOR_FIELDS}, 'corresponding': author.corresponding} for author in manuscript.authors]}


def incomplete(manuscript):
    errors = []
    setting = db.session.get(SubmissionSetting, manuscript.journal_id)
    if not setting or not setting.enabled or manuscript.article_type not in types_for(setting):
        errors.append('Selecione uma revista com submissões abertas e um tipo de artigo autorizado.')
    if not manuscript.field or not manuscript.language:
        errors.append('Informe a área científica e o idioma.')
    if not manuscript.authors or any(not author.name or not email_valid(author.email) for author in manuscript.authors) or sum(author.corresponding for author in manuscript.authors) != 1:
        errors.append('Adicione autores e defina exatamente um autor correspondente.')
    if not manuscript.title or not manuscript.summary or not manuscript.keywords:
        errors.append('Preencha título, resumo e palavras-chave.')
    main_files = [file for file in files_for(manuscript) if file.version.number == manuscript.current_version and file.kind == 'main']
    if len(main_files) != 1 or (setting and any(file.original_name.rsplit('.',1)[-1].lower() not in setting.main_formats.split(',') for file in main_files)):
        errors.append('Envie exatamente um manuscrito principal para esta versão.')
    if not all(manuscript.declarations.get(key) is True for key in REQUIRED_DECLARATIONS):
        errors.append('Confirme as declarações obrigatórias.')
    for key in OPTIONAL_DECLARATIONS:
        entry = manuscript.declarations.get(key, {})
        if entry.get('applicable') not in ('yes', 'no') or (entry.get('applicable') == 'yes' and not entry.get('text')):
            errors.append('Indique as declarações aplicáveis e justifique as que forem aplicáveis.')
            break
    return errors


@submissions_bp.get('')
@submissions_bp.get('/')
@author_required
def mine():
    page = request.args.get('page', 1, type=int)
    manuscripts = Manuscript.query.filter_by(owner_id=researcher().id).filter(Manuscript.removed_at.is_(None)).order_by(Manuscript.updated_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('submissions/list.html', manuscripts=manuscripts)


@submissions_bp.route('/nova', methods=['GET', 'POST'])
@author_required
@limiter.limit('20 per hour')
def new():
    settings = SubmissionSetting.query.filter_by(enabled=True).order_by(SubmissionSetting.journal_id).all()
    if request.method == 'POST':
        validate_csrf()
        setting = db.session.get(SubmissionSetting, request.form.get('journal_id', type=int))
        if not setting or not setting.enabled:
            flash('Selecione uma revista com submissões abertas.', 'error')
        elif Manuscript.query.filter_by(owner_id=researcher().id, status='draft').count() >= 20:
            flash('Conclua os rascunhos existentes antes de criar outro.', 'error')
        else:
            manuscript = Manuscript(owner_id=researcher().id, journal_id=setting.journal_id)
            db.session.add(manuscript)
            db.session.flush()
            db.session.add(ManuscriptVersion(manuscript_id=manuscript.id, number=1, uploader_id=researcher().id))
            event(manuscript, 'draft_created', visible=True)
            db.session.commit()
            return redirect(url_for('submissions.edit', ident=manuscript.id, step=1))
    return render_template('submissions/new.html', settings=settings)


def save_step(manuscript, step):
    form = request.form
    if step == 1:
        setting = db.session.get(SubmissionSetting, form.get('journal_id', type=int))
        if not setting or not setting.enabled or form.get('article_type') not in types_for(setting):
            raise ValueError('Selecione uma revista aberta e um tipo autorizado.')
        manuscript.journal_id = setting.journal_id
        for key, limit in (('article_type', 180), ('field', 140), ('language', 80)):
            value = form.get(key, '').strip()
            if (not value and form.get('action') != 'draft') or len(value) > limit:
                raise ValueError('Preencha os campos da revista e do tipo de artigo.')
            setattr(manuscript, key, value)
    elif step == 2:
        names = form.getlist('author_name')
        if not 1 <= len(names) <= 30:
            raise ValueError('Adicione entre 1 e 30 autores.')
        rows = []
        corresponding = form.get('corresponding', type=int)
        for index in range(len(names)):
            values = {}
            for key, (label, limit) in AUTHOR_FIELDS.items():
                column = form.getlist('author_' + key)
                value = column[index].strip() if index < len(column) else ''
                if len(value) > limit:
                    raise ValueError(label + ' excede o limite permitido.')
                values[key] = value
            if (not values['name'] or not email_valid(values['email'])) and form.get('action') != 'draft':
                raise ValueError('Informe nome e e-mail válido de todos os autores.')
            values['orcid'] = normalize_orcid(values['orcid'])
            if values['orcid']:
                identifier = values['orcid'].rsplit('/', 1)[-1].replace('-', '')
                total = 0
                for digit in identifier[:-1]:
                    total = (total + int(digit)) * 2
                check = (12 - total % 11) % 11
                if identifier[-1] != ('X' if check == 10 else str(check)):
                    raise ValueError('O identificador ORCID tem um dígito de verificação inválido.')
            rows.append(ManuscriptAuthor(position=index, corresponding=index == corresponding, **values))
        if (corresponding is None or not 0 <= corresponding < len(rows)) and form.get('action') != 'draft':
            raise ValueError('Selecione o autor correspondente.')
        manuscript.authors = rows
    elif step == 3:
        for key, (label, limit) in INFO_FIELDS.items():
            value = form.get(key, '').strip()
            if len(value) > limit:
                raise ValueError(label + ' excede o limite permitido.')
            setattr(manuscript, key, value)
        details = {}
        for key, (label, limit) in SCIENTIFIC_FIELDS.items():
            value = form.get(key, '').strip()
            if len(value) > limit:
                raise ValueError(label + ' excede o limite permitido.')
            details[key] = value
        manuscript.scientific_details = details
    elif step == 5:
        declarations = {key: form.get(key) == 'on' for key in REQUIRED_DECLARATIONS}
        for key in OPTIONAL_DECLARATIONS:
            text = form.get(key + '_text', '').strip()
            applicable = form.get(key + '_applicable', '')
            if (applicable not in ('yes', 'no') and form.get('action') != 'draft') or len(text) > 20000:
                raise ValueError('Indique o que é aplicável e respeite o limite de 20000 caracteres.')
            declarations[key] = {'applicable': applicable, 'text': text}
        manuscript.declarations = declarations


@submissions_bp.route('/<int:ident>/etapa/<int:step>', methods=['GET', 'POST'])
@author_required
def edit(ident, step):
    if not 1 <= step <= 7:
        abort(404)
    manuscript = owned(ident, lock=request.method == 'POST')
    if manuscript.status != 'draft':
        return redirect(url_for('submissions.detail', ident=ident))
    errors = []
    if request.method == 'POST':
        validate_csrf()
        try:
            save_step(manuscript, step)
            db.session.commit()
            if request.form.get('action') == 'draft':
                flash('Rascunho guardado. Ainda não é uma submissão oficial.', 'success')
                return redirect(url_for('submissions.mine'))
            return redirect(url_for('submissions.edit', ident=ident, step=min(step + 1, 7)))
        except ValueError as error:
            db.session.rollback()
            errors = [str(error)]
    settings = SubmissionSetting.query.filter_by(enabled=True).all()
    author_rows = manuscript.authors
    display_declarations = manuscript.declarations
    if errors and step == 2:
        from types import SimpleNamespace
        author_rows = []
        for index in range(min(len(request.form.getlist('author_name')), 30)):
            values = {key: (request.form.getlist('author_' + key)[index] if index < len(request.form.getlist('author_' + key)) else '') for key in AUTHOR_FIELDS}
            author_rows.append(SimpleNamespace(**values, corresponding=index == request.form.get('corresponding', type=int)))
    if errors and step == 5:
        display_declarations = {key: request.form.get(key) == 'on' for key in REQUIRED_DECLARATIONS}
        display_declarations.update({key: {'applicable': request.form.get(key + '_applicable',''), 'text': request.form.get(key + '_text','')} for key in OPTIONAL_DECLARATIONS})
    return render_template('submissions/edit.html', manuscript=manuscript, step=step, settings=settings,
                           types={setting.journal_id: types_for(setting) for setting in settings}, files=files_for(manuscript), errors=errors, author_rows=author_rows, display_declarations=display_declarations)


@submissions_bp.post('/<int:ident>/ficheiros')
@author_required
@limiter.limit('40 per hour')
def upload(ident):
    validate_csrf()
    manuscript = owned(ident, lock=True)
    if manuscript.status not in ('draft', 'revision_requested'):
        abort(409)
    number = manuscript.current_version + (manuscript.status == 'revision_requested')
    version = ManuscriptVersion.query.filter_by(manuscript_id=ident, number=number).first()
    if not version:
        version = ManuscriptVersion(manuscript_id=ident, number=number, uploader_id=researcher().id)
        db.session.add(version)
        db.session.flush()
    try:
        setting = db.session.get(SubmissionSetting, manuscript.journal_id)
        attachment = request.files.get('file')
        if not attachment or not attachment.filename:
            raise ValueError('Selecione um ficheiro.')
        data = validate_upload(attachment, request.form.get('kind'), setting.main_formats if setting else 'docx,pdf')
        total = db.session.query(func.coalesce(func.sum(ManuscriptFile.size), 0)).join(ManuscriptVersion).join(Manuscript).filter(Manuscript.owner_id == manuscript.owner_id).scalar()
        count = ManuscriptFile.query.filter_by(version_id=version.id).count()
        if total + data['size'] > 100 * 1024 * 1024 or count >= 25:
            raise ValueError('Limite: 25 ficheiros por versão e 100 MB por conta.')
        if data['kind'] == 'main' and ManuscriptFile.query.filter_by(version_id=version.id, kind='main').first():
            raise ValueError('Remova o manuscrito principal desta versão antes de enviar outro.')
        db.session.add(ManuscriptFile(version_id=version.id, **data))
        event(manuscript, 'file_uploaded', note=f"Versão {number}: {data['original_name']}")
        db.session.commit()
        flash('Ficheiro guardado de forma privada.', 'success')
    except ValueError as error:
        db.session.rollback()
        flash(str(error), 'error')
    return redirect(url_for('submissions.edit', ident=ident, step=4) if manuscript.status == 'draft' else url_for('submissions.detail', ident=ident))


@submissions_bp.post('/ficheiros/<int:file_id>/remover')
@author_required
def remove_file(file_id):
    validate_csrf()
    file = db.get_or_404(ManuscriptFile, file_id)
    manuscript = owned(file.version.manuscript_id, lock=True)
    if file.version.finalized_at or manuscript.status not in ('draft', 'revision_requested'):
        abort(409)
    db.session.delete(file)
    event(manuscript, 'file_removed', note=file.original_name)
    db.session.commit()
    return redirect(url_for('submissions.edit', ident=manuscript.id, step=4) if manuscript.status == 'draft' else url_for('submissions.detail', ident=manuscript.id))


@submissions_bp.get('/ficheiros/<int:file_id>')
def download(file_id):
    file = ManuscriptFile.query.options(defer(ManuscriptFile.payload)).filter_by(id=file_id).first_or_404()
    manuscript = db.session.get(Manuscript, file.version.manuscript_id)
    if manuscript.removed_at and not (editorial_access() and session.get('admin_superuser')):abort(410)
    if not (manuscript.removed_at and session.get('admin_superuser')) and not editorial_access(manuscript):
        account = researcher()
        if not account or not account.verified or account.id != manuscript.owner_id:
            abort(404)
    response = send_file(io.BytesIO(file.payload), mimetype='application/octet-stream', as_attachment=True,
                         download_name=file.original_name, max_age=0)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


def confirmation_notifications(manuscript, action):
    corresponding = next(author for author in manuscript.authors if author.corresponding)
    body = f'{manuscript.code}\n{manuscript.title}\nRevista: {manuscript.journal.title}\nEstado: {STATES[manuscript.status]}\nData (UTC): {utcnow():%Y-%m-%d %H:%M}\nAcompanhe em https://www.sussurrosdosaber.com/submissoes/{manuscript.id}'
    notify(corresponding.email, action + ' — ' + manuscript.code, body)
    if corresponding.email != manuscript.owner.email:
        notify(manuscript.owner.email, action + ' — ' + manuscript.code, body)
    setting = db.session.get(SubmissionSetting, manuscript.journal_id)
    if setting and setting.editorial_email:
        notify(setting.editorial_email, action + ' — ' + manuscript.code, body)


@submissions_bp.post('/<int:ident>/confirmar')
@author_required
def submit(ident):
    validate_csrf()
    manuscript = owned(ident, lock=True)
    if manuscript.status != 'draft':
        return redirect(url_for('submissions.detail', ident=ident))
    errors = incomplete(manuscript)
    if request.form.get('confirm') != 'on':
        errors.append('Confirme o envio definitivo.')
    if errors:
        db.session.rollback()
        for error in errors:
            flash(error, 'error')
        return redirect(url_for('submissions.edit', ident=ident, step=6))
    manuscript.code = f'RSS-{utcnow().year}-{manuscript.id:06d}'
    manuscript.submitted_at = utcnow()
    version = version_for(manuscript)
    version.snapshot = snapshot(manuscript)
    version.finalized_at = utcnow()
    event(manuscript, 'submitted', 'submitted', visible=True)
    confirmation_notifications(manuscript, 'Submissão recebida')
    db.session.commit()
    flash('Submissão recebida. A versão oficial foi preservada.', 'success')
    return redirect(url_for('submissions.detail', ident=ident))


@submissions_bp.get('/<int:ident>')
@author_required
def detail(ident):
    manuscript = owned(ident)
    return render_template('submissions/detail.html', manuscript=manuscript, files=files_for(manuscript),
                           events=[entry for entry in manuscript.events if entry.visible_to_author])


@submissions_bp.post('/<int:ident>/nova-versao')
@author_required
def revised(ident):
    validate_csrf()
    manuscript = owned(ident, lock=True)
    if manuscript.status != 'revision_requested':
        return redirect(url_for('submissions.detail', ident=ident))
    version = ManuscriptVersion.query.filter_by(manuscript_id=ident, number=manuscript.current_version + 1).first()
    response = request.form.get('response_to_editor', '').strip()
    if not version or not any(file.kind == 'main' for file in version.files) or not response or len(response) > 20000:
        flash('Envie o manuscrito revisto e uma resposta ao editor com até 20000 caracteres.', 'error')
        return redirect(url_for('submissions.detail', ident=ident))
    manuscript.current_version = version.number
    version.response_to_editor = response
    version.snapshot = snapshot(manuscript)
    version.finalized_at = utcnow()
    event(manuscript, 'revision_submitted', 'revised', note='Versão ' + str(version.number), visible=True)
    confirmation_notifications(manuscript, 'Versão revista recebida')
    db.session.commit()
    return redirect(url_for('submissions.detail', ident=ident))


@admin_bp.get('/submissoes')
@login_required
def submissions_list():
    from governance import scope_manuscripts, has_any_permission, MANUSCRIPT_ACCESS_PERMISSIONS
    if not any(has_any_permission(p) for p in MANUSCRIPT_ACCESS_PERMISSIONS+('submissions.configure',)):
        abort(403)
    query = scope_manuscripts(Manuscript.query.filter(Manuscript.status != 'draft'))
    search = request.args.get('q', '').strip()[:300]
    if search:
        query = query.filter(db.or_(Manuscript.title.ilike('%' + search + '%'), Manuscript.code.ilike('%' + search + '%')))
    for key, column in (('journal_id', Manuscript.journal_id), ('status', Manuscript.status), ('type', Manuscript.article_type)):
        value = request.args.get(key, '')
        if value:
            query = query.filter(column == value)
    for key, operator in (('from', 'ge'), ('to', 'le')):
        raw = request.args.get(key)
        if raw:
            try:
                date = datetime.strptime(raw, '%Y-%m-%d')
                if operator == 'le':
                    from datetime import timedelta
                    query = query.filter(Manuscript.submitted_at < date + timedelta(days=1))
                else:
                    query = query.filter(Manuscript.submitted_at >= date)
            except ValueError:
                flash('Use datas válidas nos filtros.', 'error')
    order = request.args.get('order', 'newest')
    ordering = Manuscript.title.asc() if order == 'title' else Manuscript.submitted_at.asc() if order == 'oldest' else Manuscript.submitted_at.desc()
    rows = query.order_by(ordering, Manuscript.id.desc()).paginate(page=request.args.get('page', 1, type=int), per_page=25, error_out=False)
    from governance import has_permission
    pending = EditorialNotification.query.filter_by(sent_at=None).count() if has_permission('submissions.configure') else 0
    return render_template('admin/submissions.html', manuscripts=rows, states=STATES, journals=[j for j in Journal.query.order_by(Journal.title).all() if any(has_permission(p,j.id) for p in MANUSCRIPT_ACCESS_PERMISSIONS+('submissions.configure',))], pending_notifications=pending)


@admin_bp.route('/submissoes/configuracao', methods=['GET', 'POST'])
@login_required
def submission_settings():
    from governance import require, has_any_permission, has_permission
    if not has_any_permission('submissions.configure'):
        abort(403)
    if request.method == 'POST':
        validate_csrf()
        journal = db.get_or_404(Journal, request.form.get('journal_id', type=int))
        require('submissions.configure',journal.id)
        setting = db.session.get(SubmissionSetting, journal.id) or SubmissionSetting(journal_id=journal.id)
        types = [line.strip() for line in request.form.get('article_types', '').splitlines() if line.strip()]
        formats = request.form.getlist('main_formats')
        email = request.form.get('editorial_email', '').strip().lower()
        if not 1 <= len(types) <= 30 or any(len(line) > 180 for line in types) or not formats or not set(formats) <= {'docx', 'pdf', 'txt'} or not email_valid(email):
            flash('Informe tipos de artigo, formatos autorizados e e-mail editorial válido.', 'error')
        else:
            setting.enabled = request.form.get('enabled') == 'on'
            setting.article_types = '\n'.join(dict.fromkeys(types))
            setting.main_formats = ','.join(sorted(set(formats)))
            setting.editorial_email = email
            db.session.add(setting)
            db.session.commit()
            flash('Configuração de submissões guardada.', 'success')
            return redirect(url_for('admin.submission_settings', journal_id=journal.id))
    journal_id = request.args.get('journal_id', type=int) or request.form.get('journal_id', type=int)
    if journal_id:
        require('submissions.configure',journal_id)
    return render_template('admin/submission_settings.html', journals=[j for j in Journal.query.order_by(Journal.title).all() if has_permission('submissions.configure',j.id)],
                           selected=db.session.get(SubmissionSetting, journal_id) if journal_id else None, selected_id=journal_id)


@admin_bp.route('/submissoes/<int:ident>', methods=['GET', 'POST'])
@login_required
def submission_detail(ident):
    manuscript = db.get_or_404(Manuscript, ident)
    from governance import manuscript_access, audit, eligible, conflicts, has_permission
    if manuscript.status == 'draft' or not manuscript_access(manuscript):
        abort(404)
    if request.method == 'POST':
        validate_csrf()
        lock_record(manuscript)
        action = request.form.get('action')
        note = request.form.get('note', '').strip()
        if len(note) > 20000:
            abort(400)
        permission = 'manuscript.assign' if action == 'assign' else 'manuscript.decide' if action in {'accepted','rejected'} else 'manuscript.edit'
        if not manuscript_access(manuscript,permission):
            abort(403)
        if action == 'note' and note:
            event(manuscript, 'internal_note', note=note)
        elif action == 'assign':
            editor = db.session.get(AdminUser, request.form.get('editor_id', type=int))
            allowed = eligible('manuscript.edit',manuscript.journal_id)
            member = next((m for m in allowed if m.admin_id == (editor.id if editor else None)),None)
            if not editor or not editor.active or (not editor.is_superadmin and (not member or conflicts(member,manuscript))):
                abort(400)
            if manuscript.editor_id==editor.id:return redirect(url_for('admin.submission_detail',ident=ident))
            previous_editor_id=manuscript.editor_id
            manuscript.editor_id = editor.id
            previous_editor=next((m for m in allowed if m.admin_id==previous_editor_id),None)
            if previous_editor and previous_editor.admin_id and not conflicts(previous_editor,manuscript):
                from internal_notices import emit
                emit(previous_editor.admin_id,'Responsabilidade editorial reatribuída','A submissão '+manuscript.code+' foi atribuída a outro editor.',resource=('manuscript',manuscript.id))
            event(manuscript, 'editor_assigned', note='Editor: ' + editor.display_name)
        elif action in TRANSITIONS.get(manuscript.status, ()) and note:
            event(manuscript, 'decision', action, note=note, visible=True)
            confirmation_notifications(manuscript, 'Atualização editorial')
            corresponding = next(author for author in manuscript.authors if author.corresponding)
            notify(corresponding.email, 'Decisão editorial — ' + manuscript.code, note)
        else:
            flash('Ação indisponível. As decisões e notas devem ter uma observação.', 'error')
            db.session.rollback()
            return redirect(url_for('admin.submission_detail', ident=ident))
        audit('editorial.logged','editorial',ident,manuscript.status)
        db.session.commit()
        return redirect(url_for('admin.submission_detail', ident=ident))
    can_decide=manuscript_access(manuscript,'manuscript.decide')
    can_edit=manuscript_access(manuscript,'manuscript.edit')
    transitions=[s for s in TRANSITIONS.get(manuscript.status,()) if (can_decide if s in {'accepted','rejected'} else can_edit)]
    return render_template('admin/submission_detail.html', manuscript=manuscript, files=files_for(manuscript), states=STATES,
                           transitions=transitions, admins=[m.admin for m in eligible('manuscript.edit',manuscript.journal_id) if m.admin and not conflicts(m,manuscript)],
                           can_assign=manuscript_access(manuscript,'manuscript.assign'),can_edit=can_edit,can_produce=manuscript_access(manuscript,'manuscript.production'),
                           info_fields=INFO_FIELDS, file_kinds=KINDS)


@admin_bp.post('/submissoes/<int:ident>/preparar')
@login_required
def prepare_publication(ident):
    validate_csrf()
    manuscript = lock_record(db.get_or_404(Manuscript, ident))
    from governance import manuscript_access, audit
    if not manuscript_access(manuscript,'manuscript.production'):
        abort(403)
    if manuscript.publication_id:
        return redirect(url_for('admin.journal_form', journal_id=manuscript.publication_id))
    if manuscript.status != 'accepted':
        abort(409)
    source = manuscript.journal
    publication = Journal(title=source.title, slug='artigo-' + manuscript.code.lower(), field=manuscript.field,
                          description=manuscript.summary[:4000], article_title=manuscript.title,
                          summary=manuscript.summary, keywords=manuscript.keywords, abstract=manuscript.abstract,
                          abstract_keywords=manuscript.abstract_keywords, published=False,
                          issn=source.issn, abbreviation=source.abbreviation, frequency=source.frequency,
                          current_issue=source.current_issue, cover_image=source.cover_image, cover_alt=source.cover_alt,
                          copyright_policy=source.copyright_policy, license_info=source.license_info)
    authors = [{'name': author.name, 'orcid': author.orcid,
                'description': ', '.join(filter(None, [author.affiliation, author.department, author.institution, author.city, author.country]))}
               for author in manuscript.authors]
    publication.authors_data = json.dumps(authors, ensure_ascii=False)
    publication.authors_orcid = legacy_author_lines(authors)
    corresponding = next(author for author in manuscript.authors if author.corresponding)
    publication.corresponding_author = corresponding.name + ' — ' + corresponding.email
    for declaration, field in (('conflicts', 'conflicts_of_interest'), ('funding', 'funding'), ('ethics', 'ethics_approval'),
                               ('consent', 'informed_consent'), ('data', 'data_availability')):
        value = manuscript.declarations.get(declaration, {})
        if value.get('applicable') == 'yes':
            setattr(publication, field, value.get('text', ''))
    official_files = [file for file in files_for(manuscript) if file.version.number == manuscript.current_version]
    main = next(file for file in official_files if file.kind == 'main')
    if main.original_name.lower().endswith('.docx'):
        publication.content_markdown = docx_markdown(main.payload)
    elif main.original_name.lower().endswith('.txt'):
        publication.content_markdown = main.payload.decode('utf-8-sig')[:400000]
    else:
        publication.content_markdown = ''
    for key in SCIENTIFIC_FIELDS:
        value = manuscript.scientific_details.get(key, '')
        if value:
            setattr(publication, key, value)
    publication.submission_history = '\n'.join(f'{entry.created_at:%d/%m/%Y}: {STATES[entry.new_status]}' for entry in manuscript.events if entry.visible_to_author and entry.previous_status != entry.new_status)
    db.session.add(publication)
    db.session.flush()
    manuscript.publication_id = publication.id
    import_publication_figures(publication, official_files, main)
    event(manuscript, 'prepared_for_publication', 'production', visible=True)
    audit('publication.prepared','manuscript',manuscript.id)
    db.session.commit()
    flash('Rascunho editorial criado. Confira o conteúdo, figuras e metadados antes de publicar. O original continua privado.', 'success')
    return redirect(url_for('admin.journal_form', journal_id=publication.id))


def publication_saved(journal):
    # A new standalone journal has no ID until flush; NULL must not match unlinked submissions.
    if not journal.id:db.session.flush()
    if not journal.id:return
    manuscript = Manuscript.query.filter_by(publication_id=journal.id).first()
    if not manuscript:
        return
    lock_record(manuscript)
    from governance import manuscript_access, audit
    if not manuscript_access(manuscript,'manuscript.production') and not manuscript_access(manuscript,'journal.publish'):
        abort(403)
    audit('publication.saved','manuscript',manuscript.id)
    if journal.published and manuscript.status == 'production':
        if not journal.content_markdown.strip():
            abort(400, description='Insira e confira o conteúdo do artigo antes de publicar.')
        event(manuscript, 'published', 'published', visible=True)
        confirmation_notifications(manuscript, 'Artigo publicado')
    elif not journal.published and manuscript.status == 'published':
        event(manuscript, 'publication_hidden', 'production', visible=True)


def install_submission_cli(app):
    @app.cli.command('enviar-notificacoes')
    @click.option('--limit', default=50, type=click.IntRange(1, 500))
    def deliver_notifications(limit):
        """Deliver the transactional outbox; run every minute in a single worker."""
        host, sender = os.getenv('SMTP_HOST', ''), os.getenv('SMTP_FROM', '')
        if not host or not email_valid(sender):
            raise click.ClickException('Configure SMTP_HOST e SMTP_FROM. As notificações permanecem pendentes.')
        tls = os.getenv('SMTP_TLS', 'true').lower() == 'true'
        ssl = os.getenv('SMTP_SSL', 'false').lower() == 'true'
        if not tls and not ssl and not app.testing:
            raise click.ClickException('É obrigatório utilizar SMTP_TLS ou SMTP_SSL.')
        rows = EditorialNotification.query.filter_by(sent_at=None).order_by(EditorialNotification.id).limit(limit).with_for_update(skip_locked=True).all()
        delivered = 0
        try:
            factory = smtplib.SMTP_SSL if ssl else smtplib.SMTP
            with factory(host, int(os.getenv('SMTP_PORT', '465' if ssl else '587')), timeout=15) as smtp:
                if tls and not ssl:
                    smtp.starttls()
                if os.getenv('SMTP_USERNAME'):
                    smtp.login(os.environ['SMTP_USERNAME'], os.environ.get('SMTP_PASSWORD', ''))
                for row in rows:
                    row.attempts += 1
                    message = EmailMessage()
                    message['From'], message['To'], message['Subject'] = sender, row.recipient, row.subject
                    message['Message-ID'] = f'<editorial-{row.id}@sussurrosdosaber.com>'
                    message.set_content(row.body)
                    try:
                        smtp.send_message(message)
                        row.sent_at, row.last_error = utcnow(), ''
                        delivered += 1
                    except smtplib.SMTPException:
                        row.last_error = 'Falha no envio SMTP; será tentado novamente.'
            db.session.commit()
        except (OSError, smtplib.SMTPException, ValueError) as error:
            db.session.rollback()
            raise click.ClickException('Falha na ligação SMTP. Notificações preservadas para nova tentativa.') from error
        click.echo(f'{delivered} notificações enviadas; restantes preservadas na fila.')


def import_publication_figures(publication, files, main):
    """Copy only decoded bitmap figures to the editorial draft; never expose original files."""
    from submission_uploads import office_archive
    images = [(file.original_name, file.payload) for file in files if file.kind == 'figure' and file.mime in ('image/png', 'image/jpeg')]
    if main.original_name.lower().endswith('.docx'):
        with office_archive(main.payload, 'docx') as archive:
            for name in archive.namelist():
                if name.startswith('word/media/') and name.lower().endswith(('.png', '.jpg', '.jpeg')):
                    images.append((name.rsplit('/', 1)[-1], archive.read(name)))
    for index, (name, data) in enumerate(images[:50], 1):
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > 20000000:
                    continue
                cleaned = io.BytesIO()
                image.convert('RGB').save(cleaned, format='PNG')
            asset = PublicationAsset(journal_id=publication.id, name=name, payload=cleaned.getvalue())
            db.session.add(asset)
            db.session.flush()
            publication.content_markdown += f'\n\n![Figura {index}](https://www.sussurrosdosaber.com/submissoes/figuras/{asset.id})'
        except (OSError, Image.DecompressionBombError):
            flash('Uma figura não pôde ser importada. Consulte os ficheiros originais.', 'warning')


@submissions_bp.get('/figuras/<int:asset_id>')
def publication_figure(asset_id):
    asset = PublicationAsset.query.options(defer(PublicationAsset.payload)).filter_by(id=asset_id).first_or_404()
    journal = db.session.get(Journal, asset.journal_id)
    if not journal or (not journal.published and not editorial_access(Manuscript.query.filter_by(publication_id=journal.id).first())):
        abort(404)
    return send_file(io.BytesIO(asset.payload), mimetype='image/png', download_name='figura.png', max_age=0)




@submissions_bp.route('/notificacoes',methods=['GET','POST'])
@author_required
def internal_notifications():
    from internal_notices import active_inbox, mutate
    from governance_models import StaffNotice
    if request.method=='POST':
        validate_csrf();mutate(request.form.get('action','read'),request.form.get('id',type=int),public=True)
        return redirect(url_for('submissions.internal_notifications'),code=303)
    from reader_accounts import sync_internal_updates
    sync_internal_updates(researcher())
    query=active_inbox(public=True)
    page=query.order_by(StaffNotice.created_at.desc(),StaffNotice.id.desc()).paginate(page=request.args.get('page',1,type=int),per_page=30,error_out=False)
    return render_template('submissions/notices.html',notices=page.items,pagination=page,unread=query.filter(StaffNotice.read_at.is_(None)).count())


@submissions_bp.get('/notificacoes/<int:ident>/abrir')
@author_required
def open_internal_notice(ident):
    from internal_notices import active_inbox, resource_url
    item=active_inbox(public=True).filter_by(id=ident).first_or_404()
    target=resource_url(item,public=True)
    if not target:
        flash('O recurso foi eliminado ou já não está acessível.','warning')
        return redirect(url_for('submissions.internal_notifications'))
    return redirect(target)


@submissions_bp.app_context_processor
def researcher_notifications_context():
    if not request.path.startswith('/submissoes'):return {}
    from internal_notices import active_inbox
    from governance_models import StaffNotice
    account=researcher() if request.path.startswith('/submissoes') else None
    return dict(researcher_notice_unread=active_inbox(public=True).filter(StaffNotice.read_at.is_(None)).count() if account else 0, notice_public=True, notice_unread=active_inbox(public=True).filter(StaffNotice.read_at.is_(None)).count() if account else 0, notice_recent=active_inbox(public=True).order_by(StaffNotice.created_at.desc(),StaffNotice.id.desc()).limit(5).all() if account else [])


@submissions_bp.get('/api/notificacoes')
@author_required
def internal_notice_summary():
    from flask import jsonify
    from internal_notices import summary
    return jsonify(summary(public=True))
