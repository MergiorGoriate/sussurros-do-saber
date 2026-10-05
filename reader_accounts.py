"""Account-backed reading preferences; reuses existing researcher identities."""
import secrets
from flask import Blueprint, jsonify, request, session, render_template, url_for
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload
from werkzeug.security import check_password_hash, generate_password_hash
from admin import validate_csrf, csrf_token
from extensions import limiter
from models import db, Journal, Article, utcnow
from submission_models import Researcher
from submissions import researcher, email_valid, notify, account_link, DUMMY_PASSWORD_HASH

reader_bp = Blueprint('reader', __name__, url_prefix='/conta')


@reader_bp.app_template_filter('reader_article_title')
def reader_article_title(journal):
    title = (journal.article_title or '').strip()
    if title:
        return title
    from app import journal_article_content
    return journal_article_content(journal)[0]


class ReaderJournal(db.Model):
    __table_args__ = (db.UniqueConstraint('owner_id', 'journal_id'),)
    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('researcher.id'), nullable=False, index=True)
    journal_id = db.Column(db.Integer, db.ForeignKey('journal.id'), nullable=False)
    saved = db.Column(db.Boolean, default=False, nullable=False)
    following = db.Column(db.Boolean, default=False, nullable=False)
    followed_at = db.Column(db.DateTime)
    journal = db.relationship('Journal')


class ReaderArticle(db.Model):
    owner_id = db.Column(db.Integer, db.ForeignKey('researcher.id'), primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), primary_key=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    article = db.relationship('Article')


@reader_bp.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@reader_bp.get('/sessao')
def state():
    account = researcher()
    from google_auth import profile_picture
    return jsonify(ok=True, authenticated=bool(account), verified=bool(account and account.verified),
                   csrf=csrf_token(), name=account.name if account else '',
                   picture=profile_picture(session.get('google_picture')) if account else '',
                   notification_count=notification_query(account).count() if account and account.verified else 0,
                   google_prompt_suppressed=bool(session.get('google_prompt_suppressed')),
                   saved_articles=[row.article_id for row in ReaderArticle.query.join(Article).filter(
                       ReaderArticle.owner_id == account.id, Article.status == 'published').all()] if account else [])


@reader_bp.post('/entrar')
@limiter.limit('10 per 15 minutes')
def login():
    validate_csrf()
    email = request.form.get('email', '').strip().lower()[:254]
    password = request.form.get('password', '')[:129]
    account = Researcher.query.filter_by(email=email, active=True).first()
    valid = check_password_hash(account.password_hash if account and account.password_hash else DUMMY_PASSWORD_HASH, password)
    if not account or not account.password_hash or not valid:
        return jsonify(ok=False, message='E-mail ou palavra-passe incorrectos.'), 400
    session.clear()
    session.permanent = True
    session['researcher_id'], session['researcher_nonce'] = account.id, account.token_nonce
    return jsonify(ok=True, verified=account.verified, csrf=csrf_token())


@reader_bp.post('/criar-conta')
@limiter.limit('5 per hour')
def register():
    validate_csrf()
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    if not 2 <= len(name) <= 180 or not email_valid(email) or not 12 <= len(password) <= 128:
        return jsonify(ok=False, message='Informe nome, e-mail válido e uma palavra-passe de 12 a 128 caracteres.'), 400
    account = Researcher(name=name, email=email, password_hash=generate_password_hash(password),
                         token_nonce=secrets.token_hex(24))
    try:
        db.session.add(account)
        db.session.flush()
        notify(account.email, 'Confirme a sua conta — Sussurros do Saber',
               'Confirme a sua conta em até 24 horas:\n' + account_link(account, 'verify'))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    return jsonify(ok=True, message='Se este e-mail puder ser registado, receberá uma ligação de confirmação. Depois de confirmar, entre na sua conta. Se já tem conta, entre ou recupere a palavra-passe.')


def public_journal(slug):
    return Journal.query.filter_by(slug=slug, published=True).first_or_404()


@reader_bp.post('/artigos/<int:ident>')
@limiter.limit('120 per minute')
def article_preference(ident):
    account = researcher()
    if not account:
        return jsonify(ok=False, message='Entre na sua conta para continuar.'), 401
    validate_csrf()
    if ident > 2147483647:
        return jsonify(ok=False, message='Artigo inválido.'), 404
    Article.query.filter_by(id=ident, status='published').first_or_404()
    enabled = request.form.get('enabled')
    if enabled not in ('true', 'false'):
        return jsonify(ok=False, message='Preferência inválida.'), 400
    row = db.session.get(ReaderArticle, (account.id, ident))
    if enabled == 'true' and not row:
        db.session.add(ReaderArticle(owner_id=account.id, article_id=ident))
    elif enabled == 'false' and row:
        db.session.delete(row)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(ok=False, message='Tente novamente para guardar a preferência.'), 409
    return jsonify(ok=True, saved=enabled == 'true')


@reader_bp.post('/importar-favoritos')
@limiter.limit('20 per minute')
def import_favorites():
    account = researcher()
    if not account:
        return jsonify(ok=False, message='Entre na sua conta para continuar.'), 401
    validate_csrf()
    ids = request.form.getlist('article_ids')
    slugs = request.form.getlist('journal_slugs')
    if len(ids) + len(slugs) > 100 or any(len(v) > 300 for v in ids + slugs):
        return jsonify(ok=False, message='Importe até 100 favoritos de cada vez.'), 400
    valid_ids = {int(v) for v in ids if v.isascii() and v.isdigit() and len(v) <= 10 and int(v) <= 2147483647}
    for article in Article.query.filter(Article.id.in_(valid_ids), Article.status == 'published').all():
        if not db.session.get(ReaderArticle, (account.id, article.id)):
            db.session.add(ReaderArticle(owner_id=account.id, article_id=article.id))
    for journal in Journal.query.filter(Journal.slug.in_(set(slugs)), Journal.published.is_(True)).all():
        row = ReaderJournal.query.filter_by(owner_id=account.id, journal_id=journal.id).first()
        if not row:
            row = ReaderJournal(owner_id=account.id, journal_id=journal.id)
            db.session.add(row)
        row.saved = True
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(ok=False, message='Tente novamente para importar os favoritos.'), 409
    return jsonify(ok=True)


@reader_bp.route('/revistas/<slug>', methods=['GET', 'POST'])
@limiter.limit('120 per minute')
def preference(slug):
    account = researcher()
    if not account:
        return jsonify(ok=False, message='Entre na sua conta para continuar.'), 401
    journal = public_journal(slug)
    row = ReaderJournal.query.filter_by(owner_id=account.id, journal_id=journal.id).first()
    if request.method == 'POST':
        validate_csrf()
        action, enabled = request.form.get('action'), request.form.get('enabled')
        if action not in ('saved', 'following') or enabled not in ('true', 'false'):
            return jsonify(ok=False, message='Preferência inválida.'), 400
        if action == 'following' and not account.verified:
            return jsonify(ok=False, message='Confirme o seu e-mail antes de activar notificações.',
                           verify_url=url_for('submissions.verify_notice')), 403
        if not row:
            row = ReaderJournal(owner_id=account.id, journal_id=journal.id)
            db.session.add(row)
        was_following = bool(row.following)
        setattr(row, action, enabled == 'true')
        if action == 'following' and row.following != was_following:
            row.followed_at = utcnow() if row.following else None
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify(ok=False, message='Tente novamente para guardar a preferência.'), 409
    return jsonify(ok=True, saved=bool(row and row.saved), following=bool(row and row.following))


@reader_bp.get('/biblioteca')
def library():
    account = researcher()
    rows = ReaderJournal.query.options(joinedload(ReaderJournal.journal)).join(Journal).filter(
        ReaderJournal.owner_id == account.id, ReaderJournal.saved.is_(True),
        Journal.published.is_(True)
    ).order_by(Journal.updated_at.desc()).all() if account else []
    articles = ReaderArticle.query.options(
        joinedload(ReaderArticle.article).joinedload(Article.category_rel)
    ).join(Article).filter(
        ReaderArticle.owner_id == account.id, Article.status == 'published'
    ).order_by(ReaderArticle.created_at.desc()).all() if account else []
    return render_template('reader_library.html', reader_rows=rows, reader_articles=articles,
                           reader_account=account, notifications=False)


def notification_query(account):
    return ReaderJournal.query.join(Journal).filter(
        ReaderJournal.owner_id == account.id, ReaderJournal.following.is_(True),
        Journal.published.is_(True), Journal.updated_at > ReaderJournal.followed_at
    )


@reader_bp.get('/notificacoes')
def notifications():
    account = researcher()
    rows = notification_query(account).options(joinedload(ReaderJournal.journal)).order_by(Journal.updated_at.desc()).all() if account and account.verified else []
    return render_template('reader_library.html', reader_rows=rows, reader_account=account, notifications=True)
