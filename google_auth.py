"""Optional GIS authentication. Tokens are verified here, never in the browser."""
import os
import re
import secrets
import time
from functools import lru_cache
from urllib.parse import urlsplit

import click
import requests
from cachecontrol import CacheControl
from flask import Blueprint, current_app, jsonify, request, session
from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from sqlalchemy.exc import IntegrityError

from admin import csrf_token, validate_csrf
from extensions import limiter
from models import db, utcnow
from submission_models import Researcher
from submissions import email_valid, researcher

google_bp = Blueprint('google_auth', __name__, url_prefix='/conta/google')


class GoogleIdentity(db.Model):
    # sub is stable even when Google's e-mail changes. One Google identity per account.
    subject = db.Column(db.String(255), primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('researcher.id'), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


def client_id():
    value = current_app.config.get('GOOGLE_CLIENT_ID', os.getenv('GOOGLE_CLIENT_ID', '')).strip()
    return value if re.fullmatch(r'[A-Za-z0-9_-]+\.apps\.googleusercontent\.com', value) else ''


def profile_picture(value):
    """Only HTTPS Google-hosted images from a verified identity are accepted."""
    if not isinstance(value, str) or len(value) > 2048:
        return ''
    try:
        url = urlsplit(value)
        host = (url.hostname or '').lower()
        if (url.scheme == 'https' and host.endswith('.googleusercontent.com')
                and not url.username and not url.password and url.port in (None, 443)):
            return value
    except ValueError:
        pass
    return ''


@lru_cache(maxsize=1)
def google_transport():
    # Honor Google's certificate Cache-Control; bound upstream request time.
    transport = Request(session=CacheControl(requests.Session()))
    return lambda url, method='GET', body=None, headers=None, **kwargs: transport(
        url, method=method, body=body, headers=headers, timeout=5)


@google_bp.after_request
def private_headers(response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@google_bp.post('/preparar')
@limiter.limit('30 per minute')
def prepare():
    validate_csrf()
    if not client_id():
        return jsonify(ok=False, message='Entrada via Google não configurada.'), 503
    # Reuse a current challenge so parallel/manual initialization does not invalidate it.
    if session.get('google_nonce_until', 0) < time.time():
        session['google_nonce'] = secrets.token_urlsafe(32)
        session['google_nonce_until'] = int(time.time()) + 600
    return jsonify(ok=True, nonce=session['google_nonce'])


@google_bp.post('/entrar')
@limiter.limit('10 per minute')
def login():
    validate_csrf()
    audience = client_id()
    if not audience:
        return jsonify(ok=False, message='Entrada via Google não configurada.'), 503
    credential = request.form.get('credential', '')
    nonce = session.pop('google_nonce', '')
    until = session.pop('google_nonce_until', 0)
    if not nonce or until < time.time() or not 1 <= len(credential) <= 16384:
        return jsonify(ok=False, message='A entrada expirou. Abra novamente Entrar via Google.'), 400
    try:
        claims = id_token.verify_oauth2_token(credential, google_transport(), audience=audience)
        if (claims.get('aud') != audience
                or claims.get('iss') not in ('accounts.google.com', 'https://accounts.google.com')
                or not isinstance(claims.get('exp'), (int, float)) or claims['exp'] <= time.time()
                or not secrets.compare_digest(str(claims.get('nonce', '')), nonce)
                or not isinstance(claims.get('sub'), str) or not 1 <= len(claims['sub']) <= 255
                or claims.get('email_verified') is not True):
            raise ValueError('Invalid identity claims')
        email = claims.get('email', '')
        if not isinstance(email, str) or not email_valid(email):
            raise ValueError('Invalid email')
        email = email.lower()
    except (TransportError, requests.RequestException):
        return jsonify(ok=False, message='Google indisponível. Tente novamente mais tarde.'), 503
    except (ValueError, TypeError, GoogleAuthError):
        return jsonify(ok=False, message='Não foi possível validar a credencial do Google.'), 401

    current = researcher()
    identity = db.session.get(GoogleIdentity, claims['sub'])
    account = db.session.get(Researcher, identity.owner_id) if identity else None
    if identity:
        if not account or not account.active or (current and current.id != account.id):
            return jsonify(ok=False, message='Esta identidade não pode entrar nesta conta.'), 403
    else:
        account = Researcher.query.filter_by(email=email).first()
        authoritative = email.endswith('@gmail.com') or bool(claims.get('hd'))
        # Never auto-link third-party mail or an unverified pre-existing account.
        if account and (not account.active or (current and current.id != account.id)):
            return jsonify(ok=False, message='Esta identidade não pode entrar nesta conta.'), 403
        if account and not (current and current.id == account.id) and not (authoritative and account.verified):
            return jsonify(ok=False, message='Entre primeiro na conta existente e depois use Entrar via Google para a associar.'), 409
        if current and not account:
            return jsonify(ok=False, message='Use o mesmo e-mail da sua conta para associar o Google.'), 409
        if account and GoogleIdentity.query.filter_by(owner_id=account.id).first():
            return jsonify(ok=False, message='A conta já tem outra identidade Google associada.'), 409
        if not account:
            name = claims.get('name')
            name = name.strip()[:180] if isinstance(name, str) else ''
            account = Researcher(name=name or 'Leitor', email=email, password_hash='',
                                 verified=authoritative, token_nonce=secrets.token_hex(24))
            db.session.add(account)
            try:
                db.session.flush()
            except IntegrityError:
                db.session.rollback()
                return jsonify(ok=False, message='Tente novamente para concluir a entrada.'), 409
        db.session.add(GoogleIdentity(subject=claims['sub'], owner_id=account.id))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(ok=False, message='Tente novamente para concluir a entrada.'), 409
    from premium_return import preserve_intent, resume_url
    premium_token=preserve_intent() if request.form.get('premium_return') else None
    session.clear()
    session.permanent = True
    session['researcher_id'], session['researcher_nonce'] = account.id, account.token_nonce
    picture = profile_picture(claims.get('picture'))
    if picture:
        session['google_picture'] = picture
    return jsonify(ok=True, verified=account.verified, csrf=csrf_token(),redirect_to=resume_url(account,premium_token))


def install_google_cli(app):
    @app.cli.command('migrar-login-google')
    def migrate_google():
        """Add only the Google identity and unified article favorite tables."""
        from reader_accounts import ReaderArticle
        db.metadata.create_all(db.engine, tables=[GoogleIdentity.__table__, ReaderArticle.__table__])
        click.echo('Tabelas google_identity e reader_article verificadas; dados existentes preservados.')
