import base64
import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import struct
import time
import unicodedata
from datetime import datetime
from functools import wraps
from urllib.parse import quote
import requests
from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.exceptions import BadRequest
from extensions import limiter
from journal_article import ARTICLE_FIELD_LIMITS
from journal_metadata import EDITORIAL_FIELDS, journal_authors, legacy_author_lines, submitted_author_rows, validate_authors
from models import AdminUser, Article, Author, Category, Comment, ContactMessage, Journal, Subscriber, EditorialPolicy, db, utcnow
from storage import VideoUploadError, upload_article_video, ImageUploadError, upload_article_image, upload_author_photo, upload_journal_cover

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.after_request
def protect_admin_responses(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def slugify(value):
    value = unicodedata.normalize("NFKD", (value or "").strip())
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:260]


def admin_security_stamp(administrator=None):
    """Bind cookies to current credentials without exposing credential hashes."""
    if administrator is not None:
        values = [administrator.id, administrator.security_version,
                  administrator.username, administrator.password_hash,
                  administrator.active, administrator.is_superadmin,
                  administrator.two_factor_enabled, administrator.totp_secret]
    else:
        values = [os.getenv(name, "") for name in (
            "ADMIN_USERNAME", "ADMIN_PASSWORD_HASH", "ADMIN_TOTP_SECRET",
            "ADMIN_SECURITY_VERSION",
        )]
        values.append(None if production_mode() else os.getenv("ADMIN_PASSWORD", ""))
    return hmac.new(current_app.secret_key.encode(),
                    json.dumps(values).encode(), hashlib.sha256).hexdigest()


def admin_session_valid():
    if not session.get("admin_authenticated"):
        return False
    try:
        idle_timeout = max(1, min(120, int(os.getenv("ADMIN_IDLE_TIMEOUT_MINUTES", "15")))) * 60
    except ValueError:
        idle_timeout = 15 * 60
    now = time.time()
    last_activity = session.get("admin_last_activity_at")
    if not isinstance(last_activity, (int, float)) or now - last_activity > idle_timeout:
        return False

    administrator_id = session.get("admin_id")
    if administrator_id is not None:
        administrator = db.session.get(AdminUser, administrator_id)
        if not administrator or not administrator.active:
            return False
        from governance_models import TeamMember
        member=TeamMember.query.filter_by(admin_id=administrator.id).first()
        if member and member.removed_at:
            return False
        if session.get("admin_security_stamp") != admin_security_stamp(administrator):
            return False
        session["admin_superuser"] = bool(administrator.is_superadmin)
        if administrator.two_factor_enabled and not session.get("admin_2fa_verified"):
            return False
    else:
        configured_totp = os.getenv("ADMIN_TOTP_SECRET", "").strip()
        if (not os.getenv("ADMIN_USERNAME", "").strip() or not configured_totp
                or session.get("admin_security_stamp") != admin_security_stamp()):
            return False
        session["admin_superuser"] = True
        if configured_totp and not session.get("admin_2fa_verified"):
            return False

    session["admin_last_activity_at"] = now
    return True


PUBLIC_ADMIN_ENDPOINTS = {"admin.login", "admin.verify_two_factor"}


def require_admin_enrollment():
    administrator_id = session.get("admin_id")
    administrator = db.session.get(AdminUser, administrator_id) if administrator_id else None
    if (administrator is not None and not administrator.two_factor_enabled
            and request.endpoint not in {"admin.two_factor_settings", "admin.logout"}):
        if request.path.startswith("/admin/api/") or request.endpoint == "journal_markdown_preview":
            return jsonify(ok=False, error="Conclua a configuração de dois fatores."), 403
        flash("A autenticação de dois fatores é obrigatória. Conclua a configuração para continuar.", "warning")
        return redirect(url_for("admin.two_factor_settings"))
    return None


@admin_bp.before_request
def enforce_admin_authentication():
    """Protege centralmente todas as rotas administrativas presentes e futuras."""
    if request.endpoint in PUBLIC_ADMIN_ENDPOINTS:
        return None
    if admin_session_valid():
        enrollment = require_admin_enrollment()
        if enrollment is not None:
            return enrollment
        from governance import guard_existing_endpoint
        return guard_existing_endpoint()
    session.clear()
    if request.path.startswith("/admin/api/"):
        return jsonify(
            ok=False,
            error="Autenticação administrativa necessária.",
        ), 401
    return redirect(url_for("admin.login", next=request.path))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not admin_session_valid():
            session.clear()
            if request.path.startswith("/admin/api/"):
                return jsonify(
                    ok=False,
                    error="Autenticação administrativa necessária.",
                ), 401
            return redirect(url_for("admin.login", next=request.path))
        enrollment = require_admin_enrollment()
        if enrollment is not None:
            return enrollment
        from governance import guard_existing_endpoint
        guard_existing_endpoint()
        return view(*args, **kwargs)
    return wrapped


def superadmin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not admin_session_valid():
            session.clear()
            return redirect(url_for("admin.login", next=request.path))
        if not session.get("admin_superuser"):
            abort(403)
        enrollment = require_admin_enrollment()
        if enrollment is not None:
            return enrollment
        return view(*args, **kwargs)
    return wrapped


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def validate_csrf():
    sent = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not sent or not expected or not hmac.compare_digest(sent, expected):
        abort(400)


def recover_authentication_csrf(template):
    """Reject a stale login form while allowing a fresh, protected attempt."""
    try:
        validate_csrf()
    except BadRequest:
        session.pop("csrf_token", None)
        flash(
            "O formulário de entrada expirou ou a sessão mudou. "
            "Preencha novamente este formulário para continuar com segurança.",
            "warning",
        )
        return render_template(template), 400
    return None


@admin_bp.app_context_processor
def admin_context():
    return {
        "csrf_token": csrf_token,
        "turnstile_site_key": os.getenv("TURNSTILE_SITE_KEY", ""),
        "current_admin_id": session.get("admin_id"),
        "current_admin_is_primary": bool(session.get("admin_superuser")),
    }


def production_mode():
    return (
        os.getenv("RENDER", "").lower() == "true"
        or os.getenv("FLASK_ENV", "").lower() == "production"
    )


def turnstile_valid():
    secret = os.getenv("TURNSTILE_SECRET_KEY", "").strip()
    site_key = os.getenv("TURNSTILE_SITE_KEY", "").strip()
    # Produção continua segura por omissão, mas permite recuperação controlada
    # quando REQUIRE_TURNSTILE=false for definido explicitamente.
    required = os.getenv(
        "REQUIRE_TURNSTILE",
        "true" if production_mode() else "false",
    ).lower() == "true"
    if not secret or not site_key:
        return not required
    try:
        response = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": secret, "response": request.form.get("cf-turnstile-response", ""), "remoteip": request.remote_addr},
            timeout=8,
        )
        return bool(response.json().get("success"))
    except (requests.RequestException, ValueError):
        return False


def generate_totp_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret, timestamp=None):
    cleaned = re.sub(r"[^A-Z2-7]", "", (secret or "").upper())
    if not cleaned:
        return ""
    padded = cleaned + "=" * ((8 - len(cleaned) % 8) % 8)
    try:
        key = base64.b32decode(padded, casefold=True)
    except (ValueError, TypeError):
        return ""
    counter = int((timestamp if timestamp is not None else time.time()) // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{number:06d}"


def verify_totp(secret, value, window=1):
    candidate = re.sub(r"\D", "", value or "")
    if len(candidate) != 6:
        return False
    now = time.time()
    return any(
        hmac.compare_digest(totp_code(secret, now + offset * 30), candidate)
        for offset in range(-window, window + 1)
    )


def generate_recovery_codes(count=8):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return [
        "-".join(
            "".join(secrets.choice(alphabet) for _ in range(4))
            for _ in range(3)
        )
        for _ in range(count)
    ]


def consume_recovery_code(administrator, candidate):
    normalized = (candidate or "").strip().upper()
    if not normalized:
        return False
    try:
        hashes = json.loads(administrator.recovery_code_hashes or "[]")
    except (TypeError, ValueError):
        hashes = []
    for index, stored_hash in enumerate(hashes):
        if check_password_hash(stored_hash, normalized):
            hashes.pop(index)
            administrator.recovery_code_hashes = json.dumps(hashes)
            db.session.commit()
            return True
    return False


def complete_admin_login(administrator=None, *, username=None, superuser=False):
    if administrator is not None:
        administrator.last_login_at = utcnow()
        db.session.commit()
        username = administrator.username
        superuser = bool(administrator.is_superadmin)
    session.clear()
    session.permanent = False
    session["admin_authenticated"] = True
    session["admin_id"] = administrator.id if administrator is not None else None
    session["admin_username"] = username
    session["admin_superuser"] = superuser
    session["admin_security_stamp"] = admin_security_stamp(administrator)
    session["admin_2fa_verified"] = bool(
        administrator.two_factor_enabled if administrator is not None
        else os.getenv("ADMIN_TOTP_SECRET", "").strip()
    )
    session["admin_last_activity_at"] = time.time()
    session["csrf_token"] = secrets.token_urlsafe(32)
    return redirect(url_for("admin.dashboard"))


def begin_two_factor_challenge(*, administrator=None, username=None, superuser=False):
    session.clear()
    session.permanent = False
    session["pending_2fa_admin_id"] = administrator.id if administrator is not None else None
    session["pending_2fa_username"] = username
    session["pending_2fa_superuser"] = superuser
    session["pending_2fa_expires_at"] = time.time() + 300
    session["pending_2fa_security_stamp"] = admin_security_stamp(administrator)
    session["csrf_token"] = secrets.token_urlsafe(32)
    return redirect(url_for("admin.verify_two_factor"))


@admin_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute; 20 per hour")
def login():
    if session.get("admin_authenticated"):
        return redirect(url_for("admin.dashboard"))
    if request.method == "POST":
        csrf_error = recover_authentication_csrf("admin/login.html")
        if csrf_error is not None:
            return csrf_error
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        database_admin = AdminUser.query.filter(
            db.func.lower(AdminUser.username) == username,
            AdminUser.active.is_(True),
        ).first()
        configured_user = os.getenv("ADMIN_USERNAME")
        # Palavra-passe simples é aceite apenas no desenvolvimento local.
        configured_password = None if production_mode() else os.getenv("ADMIN_PASSWORD")
        configured_password_hash = os.getenv("ADMIN_PASSWORD_HASH")
        if not turnstile_valid():
            flash("A verificação de segurança falhou. Actualize a página e tente novamente.", "error")
        elif database_admin and check_password_hash(database_admin.password_hash, password):
            if database_admin.two_factor_enabled and database_admin.totp_secret:
                return begin_two_factor_challenge(administrator=database_admin)
            flash("Ative a autenticação de dois fatores na área Segurança.", "warning")
            return complete_admin_login(database_admin)
        elif not configured_user or not (configured_password_hash or configured_password):
            flash("As credenciais administrativas ainda não estão configuradas.", "error")
        elif hmac.compare_digest(username, configured_user.lower()) and (
            (configured_password_hash and check_password_hash(configured_password_hash, password))
            or (configured_password and hmac.compare_digest(password, configured_password))
        ):
            env_totp_secret = os.getenv("ADMIN_TOTP_SECRET", "").strip()
            if not env_totp_secret:
                flash(
                    "A conta principal exige 2FA. Configure ADMIN_TOTP_SECRET no Coolify.",
                    "error",
                )
            else:
                return begin_two_factor_challenge(
                    username=configured_user,
                    superuser=True,
                )
        else:
            flash("Utilizador ou palavra-passe inválidos.", "error")
    return render_template("admin/login.html")


@admin_bp.route("/verificar-2fa", methods=["GET", "POST"])
@limiter.limit("6 per minute; 20 per hour")
def verify_two_factor():
    pending_id = session.get("pending_2fa_admin_id")
    pending_username = session.get("pending_2fa_username")
    if pending_id is None and not pending_username:
        return redirect(url_for("admin.login"))
    administrator = db.session.get(AdminUser, pending_id) if pending_id is not None else None
    expires_at = session.get("pending_2fa_expires_at")
    if (not isinstance(expires_at, (int, float)) or time.time() >= expires_at
            or (pending_id is not None and (administrator is None or not administrator.active
                                          or not administrator.two_factor_enabled))
            or session.get("pending_2fa_security_stamp") != admin_security_stamp(administrator)):
        session.clear()
        flash("O pedido de autenticação expirou ou as credenciais mudaram. Entre novamente.", "warning")
        return redirect(url_for("admin.login"))
    if request.method == "POST":
        csrf_error = recover_authentication_csrf("admin/verify_2fa.html")
        if csrf_error is not None:
            return csrf_error
        code = request.form.get("code", "").strip()
        if pending_id is not None:
            administrator = db.session.get(AdminUser, pending_id)
            valid = bool(
                administrator
                and administrator.active
                and (
                    verify_totp(administrator.totp_secret, code)
                    or consume_recovery_code(administrator, code)
                )
            )
            if valid:
                return complete_admin_login(administrator)
        else:
            env_secret = os.getenv("ADMIN_TOTP_SECRET", "").strip()
            if env_secret and verify_totp(env_secret, code):
                return complete_admin_login(
                    username=pending_username,
                    superuser=bool(session.get("pending_2fa_superuser")),
                )
        flash("Código de autenticação inválido ou expirado.", "error")
    return render_template("admin/verify_2fa.html")


@admin_bp.route("/seguranca/2fa", methods=["GET", "POST"])
@login_required
def two_factor_settings():
    administrator = db.session.get(AdminUser, session.get("admin_id")) if session.get("admin_id") else None
    if administrator is None:
        return render_template(
            "admin/two_factor.html",
            environment_managed=True,
            enabled=bool(os.getenv("ADMIN_TOTP_SECRET", "").strip()),
        )

    recovery_codes = None
    setup_secret = None
    if not administrator.two_factor_enabled:
        setup_secret = session.get("totp_setup_secret") or generate_totp_secret()
        session["totp_setup_secret"] = setup_secret

    if request.method == "POST":
        validate_csrf()
        action = request.form.get("action", "enable")
        password = request.form.get("password", "")
        code = request.form.get("code", "")
        if not check_password_hash(administrator.password_hash, password):
            flash("A palavra-passe atual está incorreta.", "error")
        elif action == "enable":
            secret = session.get("totp_setup_secret")
            if not secret or not verify_totp(secret, code):
                flash("O código do autenticador é inválido ou expirou.", "error")
            else:
                recovery_codes = generate_recovery_codes()
                administrator.totp_secret = secret
                administrator.two_factor_enabled = True
                administrator.recovery_code_hashes = json.dumps([
                    generate_password_hash(item) for item in recovery_codes
                ])
                db.session.commit()
                session.pop("totp_setup_secret", None)
                session["admin_2fa_verified"] = True
                session["admin_security_stamp"] = admin_security_stamp(administrator)
                setup_secret = None
                flash("Autenticação de dois fatores ativada.", "success")
        elif action == "regenerate":
            if not administrator.two_factor_enabled or not verify_totp(administrator.totp_secret, code):
                flash("Confirme a operação com um código válido do autenticador.", "error")
            else:
                recovery_codes = generate_recovery_codes()
                administrator.recovery_code_hashes = json.dumps([
                    generate_password_hash(item) for item in recovery_codes
                ])
                db.session.commit()
                flash("Novos códigos de recuperação criados. Os anteriores foram invalidados.", "success")
        elif action == "disable":
            flash("A autenticação de dois fatores é obrigatória para todas as contas administrativas e não pode ser desativada.", "error")

    issuer = "Sussurros do Saber"
    account_label = administrator.email or administrator.username
    otpauth_uri = (
        f"otpauth://totp/{quote(issuer)}:{quote(account_label)}"
        f"?secret={setup_secret}&issuer={quote(issuer)}&digits=6&period=30"
        if setup_secret else None
    )
    return render_template(
        "admin/two_factor.html",
        administrator=administrator,
        environment_managed=False,
        enabled=administrator.two_factor_enabled,
        setup_secret=setup_secret,
        otpauth_uri=otpauth_uri,
        recovery_codes=recovery_codes,
    )


@admin_bp.post("/logout")
@login_required
def logout():
    validate_csrf()
    session.clear()
    return redirect(url_for("admin.login"))


@admin_bp.route("/politicas-editoriais", methods=["GET", "POST"])
@login_required
def editorial_policies():
    policy = EditorialPolicy.query.first()
    fields = ("page_title", "page_description", "page_content", "author_guidelines", "reviewer_guidelines", "ethics_policy", "ai_policy", "data_policy", "fees_policy", "open_access_policy")
    if request.method == "POST":
        validate_csrf()
        values = {field: request.form[field].strip() for field in fields if field in request.form}
        if any(len(value) > 100000 for value in values.values()):
            flash("Cada política deve ter até 100000 caracteres. Reduza o texto e tente novamente.", "error")
        else:
            if policy is None:
                policy = EditorialPolicy()
                db.session.add(policy)
            for field, value in values.items():
                setattr(policy, field, value)
            db.session.commit()
            flash("Políticas editoriais guardadas com sucesso.", "success")
            return redirect(url_for("admin.editorial_policies"))
    return render_template("admin/editorial_policies.html", policy=policy)


@admin_bp.post("/politicas-editoriais/previsualizar")
@login_required
@limiter.limit("60 per minute")
def preview_author_guidelines():
    validate_csrf()
    content = request.form.get("author_guidelines", "").strip()
    if len(content) > 100000:
        return jsonify(error="As diretrizes devem ter até 100000 caracteres."), 400
    from app import render_markdown
    from editorial_content import prepare_guidelines
    html = render_markdown(content) if content else render_template("partials/author_guidelines_default.html")
    html, _ = prepare_guidelines(html)
    return jsonify(html=str(html), default=not bool(content))


@admin_bp.get("/docs")
@login_required
def docs():
    return render_template("admin/docs.html")


@admin_bp.get("")
@login_required
def dashboard():
    from governance import current_member
    account=db.session.get(AdminUser,session.get('admin_id')) if session.get('admin_id') else None
    if not session.get('admin_superuser') and (current_member() or (account and account.governance_managed)):
        return redirect(url_for('staff.workspace'))
    return render_template("admin/dashboard.html", article_count=Article.query.count(), draft_count=Article.query.filter_by(status="draft").count(), scheduled_count=Article.query.filter_by(status="scheduled").count(), contact_count=ContactMessage.query.filter_by(read=False).count(), subscriber_count=Subscriber.query.filter_by(active=True).count(), recent_articles=Article.query.order_by(Article.updated_at.desc()).limit(6).all())


@admin_bp.route("/administradores", methods=["GET", "POST"])
@superadmin_required
def administrators():
    from governance import parse_identifier
    from governance_models import TeamMember
    member_id=parse_identifier((request.form if request.method=='POST' else request.args).get('member_id'))
    selected_member=None
    if member_id:
        query=TeamMember.query.filter_by(id=member_id)
        selected_member=query.with_for_update().populate_existing().first_or_404() if request.method=='POST' else query.first_or_404()
        if selected_member.removed_at or selected_member.admin_id:
            abort(409,description='Escolha um colaborador não removido e sem conta associada.')
    if request.method == "POST":
        validate_csrf()
        username = request.form.get("username", "").strip().lower()
        display_name = request.form.get("display_name", "").strip()
        email = request.form.get("email", "").strip().lower() or None
        password = request.form.get("password", "")
        password_confirmation = request.form.get("password_confirmation", "")
        duplicate_username = AdminUser.query.filter(db.func.lower(AdminUser.username) == username).first()
        duplicate_email = email and AdminUser.query.filter(db.func.lower(AdminUser.email) == email).first()
        if not re.fullmatch(r"[a-z0-9._-]{3,60}", username):
            flash("O utilizador deve ter 3 a 60 caracteres: letras, números, ponto, hífen ou sublinhado.", "error")
        elif not 2 <= len(display_name) <= 120:
            flash("Informe o nome do administrador.", "error")
        elif email and (len(email) > 180 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
            flash("Informe um endereço de e-mail válido.", "error")
        elif len(password) < 14:
            flash("A palavra-passe deve ter pelo menos 14 caracteres.", "error")
        elif password != password_confirmation:
            flash("A confirmação da palavra-passe não corresponde.", "error")
        elif duplicate_username or duplicate_email:
            flash("Já existe um administrador com esse utilizador ou e-mail.", "error")
        else:
            administrator = AdminUser(
                username=username,
                display_name=display_name,
                email=email,
                password_hash=generate_password_hash(password),
                is_superadmin=False, governance_managed=True,
            )
            db.session.add(administrator)
            db.session.flush()
            from governance import audit
            invited_member=selected_member or TeamMember(name=display_name,email=email or '',status='invited')
            invited_member.admin=administrator
            db.session.add(invited_member);db.session.flush()
            audit('member.saved' if selected_member else 'member.invited','member',invited_member.id,'Conta administrativa associada' if selected_member else '')
            audit('account.created','admin',administrator.id)
            db.session.commit()
            flash("Novo administrador criado com sucesso.", "success")
            return redirect(url_for("admin.administrators"))
    return render_template(
        "admin/administrators.html",
        administrators=AdminUser.query.filter(~db.exists().where(
            TeamMember.admin_id == AdminUser.id, TeamMember.removed_at.is_not(None)
        )).order_by(AdminUser.is_superadmin.desc(), AdminUser.created_at.desc()).all(),
        available_members=TeamMember.query.filter(TeamMember.admin_id.is_(None),TeamMember.removed_at.is_(None)).order_by(TeamMember.name).all(),
        selected_member=selected_member,
        configured_primary=os.getenv("ADMIN_USERNAME"),
    )


@admin_bp.post("/administradores/<int:administrator_id>/editar")
@superadmin_required
def edit_administrator(administrator_id):
    validate_csrf()
    administrator = db.get_or_404(AdminUser, administrator_id)
    from governance_models import TeamMember
    if TeamMember.query.filter_by(admin_id=administrator.id).filter(TeamMember.removed_at.is_not(None)).first():
        abort(409, description='Esta conta foi removida. Consulte o histórico de remoções.')
    username = request.form.get("username", "").strip().lower()
    display_name = request.form.get("display_name", "").strip()
    email = request.form.get("email", "").strip().lower() or None
    password = request.form.get("password", "")
    password_confirmation = request.form.get("password_confirmation", "")
    active = request.form.get("active") == "on"
    duplicate_username = AdminUser.query.filter(
        db.func.lower(AdminUser.username) == username,
        AdminUser.id != administrator.id,
    ).first()
    duplicate_email = email and AdminUser.query.filter(
        db.func.lower(AdminUser.email) == email,
        AdminUser.id != administrator.id,
    ).first()

    if not re.fullmatch(r"[a-z0-9._-]{3,60}", username):
        flash("O utilizador deve ter 3 a 60 caracteres: letras, números, ponto, hífen ou sublinhado.", "error")
    elif not 2 <= len(display_name) <= 120:
        flash("Informe o nome do administrador.", "error")
    elif email and (len(email) > 180 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)):
        flash("Informe um endereço de e-mail válido.", "error")
    elif password and len(password) < 14:
        flash("A nova palavra-passe deve ter pelo menos 14 caracteres.", "error")
    elif password != password_confirmation:
        flash("A confirmação da palavra-passe não corresponde.", "error")
    elif duplicate_username or duplicate_email:
        flash("Já existe um administrador com esse utilizador ou e-mail.", "error")
    elif administrator.is_superadmin and not active:
        flash("O Administrador principal não pode ser desativado.", "error")
    elif session.get("admin_id") == administrator.id and not active:
        flash("Não pode desativar a conta que está a utilizar.", "error")
    else:
        administrator.username = username
        administrator.display_name = display_name
        administrator.email = email
        administrator.active = active
        if password:
            administrator.password_hash = generate_password_hash(password)
        from governance import audit
        audit('account.updated','admin',administrator.id,'Activo: '+str(active))
        db.session.commit()
        if session.get("admin_id") == administrator.id:
            session["admin_username"] = administrator.username
        flash("Administrador atualizado com sucesso.", "success")
    return redirect(url_for("admin.administrators"))


@admin_bp.route("/administradores/<int:administrator_id>/eliminar", methods=["GET", "POST"])
@superadmin_required
def delete_administrator(administrator_id):
    from governance_models import TeamMember
    from governance import audit
    query = AdminUser.query.filter_by(id=administrator_id)
    administrator = query.with_for_update().populate_existing().first_or_404() if request.method == 'POST' else query.first_or_404()
    if administrator.is_superadmin or session.get('admin_id') == administrator.id:
        abort(403, description='Não pode eliminar a conta principal nem a conta que está a utilizar.')
    member = TeamMember.query.filter_by(admin_id=administrator.id).first()
    if request.method == 'GET':
        if member and member.removed_at:
            return redirect(url_for('admin.administrators'))
        return render_template('admin/remove_administrator.html', administrator=administrator)
    validate_csrf()
    if request.form.get('confirm') != 'yes':
        abort(400, description='Confirme a remoção do administrador.')
    if not member:
        # Legacy accounts may predate staff governance. Preserve their identity
        # and foreign keys in the same removal history as current accounts.
        member = TeamMember(admin=administrator, name=administrator.display_name,
                            email=administrator.email or '', status='ended')
        db.session.add(member)
        db.session.flush()
    if not member.removed_at:
        member.removed_at = utcnow()
        member.status = 'ended'
        member.available = False
        member.public_visible = False
        for mandate in member.appointments:
            mandate.active = False
        administrator.active = False
        administrator.governance_managed = True
        administrator.security_version += 1
        audit('account.removed', 'admin', administrator.id, administrator.display_name)
        audit('member.removed', 'member', member.id, member.name)
        db.session.commit()
    flash('Administrador removido. O acesso e os mandatos foram revogados; o histórico foi preservado.', 'success')
    return redirect(url_for('admin.administrators'), code=303)


@admin_bp.get("/artigos")
@login_required
def articles():
    from governance import article_scope
    return render_template('admin/articles.html',articles=article_scope(Article.query).order_by(Article.updated_at.desc()).all())


def parse_datetime(value):
    return datetime.fromisoformat(value) if value else None


@admin_bp.post("/api/videos")
@login_required
@limiter.limit("10 per hour")
def upload_inline_video():
    validate_csrf()
    try:
        video_url = upload_article_video(request.files.get("video"))
    except VideoUploadError as error:
        return jsonify(ok=False, error=str(error)), 400
    return jsonify(ok=True, url=video_url)


@admin_bp.post("/api/imagens")
@login_required
@limiter.limit("20 per hour")
def upload_inline_image():
    validate_csrf()
    image_file = request.files.get("image")
    if not image_file or not image_file.filename:
        return jsonify(ok=False, error="Seleccione uma imagem para carregar."), 400
    try:
        image_url = upload_article_image(image_file)
    except ImageUploadError as error:
        return jsonify(ok=False, error=str(error)), 400
    return jsonify(ok=True, url=image_url)


@admin_bp.route("/artigos/novo", methods=["GET", "POST"])
@admin_bp.route("/artigos/<int:article_id>/editar", methods=["GET", "POST"])
@login_required
def article_form(article_id=None):
    article = (Article.query.filter_by(id=article_id).with_for_update().populate_existing().first() if request.method=='POST' else db.session.get(Article,article_id)) if article_id else Article()
    if article_id and not article:
        abort(404)
    from governance import article_edit_access, article_save_guard, article_saved
    article_edit_access(article)
    from article_history import snapshot, record_revision
    from governance_models import ArticleRevision
    previous_content = snapshot(article) if article.id else None
    previous_updated_at = article.updated_at
    if request.method == "POST":
        validate_csrf()
        if article.id and request.form.get('version_token') and request.form['version_token'] != article.updated_at.isoformat():
            flash('O artigo foi alterado por outra pessoa. Guarde uma cópia do seu texto e consulte o histórico antes de voltar a guardar.', 'error')
            return render_template('admin/article_form.html', article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all()), 409
        title = request.form.get("title", "").strip()
        if not 5 <= len(title) <= 240:
            flash("O título deve ter entre 5 e 240 caracteres.", "error")
        else:
            summary = request.form.get("summary", "").strip()
            body = request.form.get("body", "").strip()
            status = request.form.get("status", "draft")
            try:
                author_id = int(request.form.get("author_id", ""))
                category_id = int(request.form.get("category_id", ""))
                read_minutes = max(1, min(120, int(request.form.get("read_minutes") or 5)))
                scheduled_at = parse_datetime(request.form.get("scheduled_at"))
            except (TypeError, ValueError):
                flash("Revise autor, categoria, tempo de leitura e data programada.", "error")
                return render_template("admin/article_form.html", article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all())
            if not 10 <= len(summary) <= 2000 or status not in {"draft", "review", "approved", "published", "scheduled"}:
                flash("O resumo deve ter entre 10 e 2000 caracteres e o estado deve ser válido.", "error")
                return render_template("admin/article_form.html", article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all())
            if status in {"approved", "published", "scheduled"} and len(body) < 50:
                flash("Artigos aprovados, publicados ou programados precisam de conteúdo completo.", "error")
                return render_template("admin/article_form.html", article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all())
            limits = {"body": 400000, "references": 100000, "keywords": 500, "doi": 180, "slug": 260}
            if any(len(request.form.get(name, "")) > maximum for name, maximum in limits.items()):
                flash("Um dos campos excede o limite permitido. Reduza o conteúdo e tente novamente.", "error")
                return render_template("admin/article_form.html", article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all())
            if status == "scheduled" and not scheduled_at:
                flash("Informe a data e hora da publicação programada.", "error")
                return render_template("admin/article_form.html", article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all())
            if not db.session.get(Author, author_id) or not db.session.get(Category, category_id):
                flash("Selecione um autor e uma categoria existentes.", "error")
                return render_template("admin/article_form.html", article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all())
            article_save_guard(article,status,author_id)
            from app import article_cover_video
            cover_video = request.form.get("cover_video", "").strip()
            video_file = request.files.get("cover_video_file")
            if video_file and video_file.filename:
                try:
                    cover_video = upload_article_video(video_file)
                except VideoUploadError as error:
                    flash(str(error), "error")
                    return render_template("admin/article_form.html", article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all())
            if cover_video and (len(cover_video) > 1000 or not article_cover_video(cover_video, title)):
                flash("Use uma URL válida do YouTube, Vimeo ou de um vídeo MP4, WebM ou OGG.", "error")
                return render_template("admin/article_form.html", article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all())
            article.cover_video = cover_video
            article.title = title
            base_slug = slugify(request.form.get("slug") or title) or f"artigo-{article.id or int(datetime.now().timestamp())}"
            candidate, number = base_slug, 2
            while Article.query.filter(Article.slug == candidate, Article.id != article.id).first():
                candidate, number = f"{base_slug}-{number}", number + 1
            article.slug = candidate
            article.summary = summary
            article.body = body
            article.references = request.form.get("references", "").strip()
            article.keywords = request.form.get("keywords", "").strip()
            article.doi = request.form.get("doi", "").strip()
            image_file = request.files.get("image_file")
            try:
                article.image = upload_article_image(image_file) if image_file and image_file.filename else request.form.get("image", "").strip()
            except ImageUploadError as error:
                flash(str(error), "error")
                return render_template("admin/article_form.html", article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all())
            article.read_minutes = read_minutes
            article.author_id = author_id
            article.category_id = category_id
            article.featured = request.form.get("featured") == "on"
            article.status = status
            article.scheduled_at = scheduled_at
            if article.status == "published" and not article.published_at:
                article.published_at = utcnow()
            if article.status == "scheduled" and not article.scheduled_at:
                flash("Informe a data e hora da publicação programada.", "error")
                return render_template("admin/article_form.html", article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all())
            if not article.id:
                db.session.add(article)
            db.session.flush()
            article_saved(article)
            if previous_content and not ArticleRevision.query.with_entities(ArticleRevision.id).filter_by(article_id=article.id).first():
                record_revision(article, content=previous_content, baseline=True,
                                reason='Conteúdo anterior ao primeiro registo', created_at=previous_updated_at)
            record_revision(article)
            db.session.commit()
            flash("Artigo guardado com sucesso.", "success")
            if request.form.get("save_mode") == "continue":
                return redirect(url_for("admin.article_form", article_id=article.id))
            return redirect(url_for("admin.articles"))
    return render_template("admin/article_form.html", article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all())


@admin_bp.post("/artigos/<int:article_id>/eliminar")
@login_required
def delete_article(article_id):
    validate_csrf()
    article = db.get_or_404(Article, article_id)
    from governance_models import ArticleWorkflow, PortalReview
    if PortalReview.query.filter_by(article_id=article.id).first():
        abort(409,description="Este artigo tem pareceres registados. Reabra-o como rascunho para o retirar da publicação.")
    from governance import audit
    from reader_accounts import ReaderArticle
    ReaderArticle.query.filter_by(article_id=article.id).delete(synchronize_session=False)
    ArticleWorkflow.query.filter_by(article_id=article.id).delete()
    audit('article.deleted','article',article.id)
    db.session.delete(article)
    db.session.commit()
    flash("Artigo eliminado.", "success")
    return redirect(url_for("admin.articles"))


@admin_bp.route("/autores", methods=["GET", "POST"])
@login_required
def authors():
    if request.method == "POST":
        validate_csrf()
        name = request.form.get("name", "").strip()
        author_id = request.form.get("author_id")
        try:
            parsed_author_id = int(author_id) if author_id else None
        except (TypeError, ValueError):
            flash("Identificador de autor inválido.", "error")
            return redirect(url_for("admin.authors"))
        author = db.session.get(Author, parsed_author_id) if parsed_author_id else Author()
        if parsed_author_id and not author:
            abort(404)

        requested_slug = slugify(request.form.get("slug", "").strip() or name)
        email = request.form.get("email", "").strip() or None
        headline = request.form.get("headline", "").strip()
        role = request.form.get("role", "").strip()
        institution = request.form.get("institution", "").strip()
        google_scholar = request.form.get("google_scholar", "").strip()
        researchgate = request.form.get("researchgate", "").strip()
        orcid = request.form.get("orcid", "").strip()
        if orcid:
            orcid = re.sub(r"^https?://orcid\.org/", "", orcid, flags=re.I)
        photo_url = request.form.get("photo_url", "").strip()
        photo_file = request.files.get("photo_file")
        duplicate_slug = Author.query.filter(Author.slug == requested_slug, Author.id != author.id).first()
        duplicate_email = email and Author.query.filter(Author.email == email, Author.id != author.id).first()

        if not name:
            flash("Informe o nome do autor.", "error")
        elif not requested_slug:
            flash("Informe uma URL válida para o perfil.", "error")
        elif duplicate_slug:
            flash("Esta URL de autor já está em uso.", "error")
        elif duplicate_email:
            flash("Este e-mail já pertence a outro autor.", "error")
        elif email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            flash("Informe um e-mail válido.", "error")
        elif orcid and not re.fullmatch(r"\d{4}-\d{4}-\d{4}-[\dX]{4}", orcid, re.I):
            flash("Informe o ORCID no formato 0000-0000-0000-0000.", "error")
        elif google_scholar and not re.fullmatch(r"https?://[^\s]+", google_scholar, re.I):
            flash("Informe um endereço válido do Google Scholar.", "error")
        elif researchgate and not re.fullmatch(r"https?://[^\s]+", researchgate, re.I):
            flash("Informe um endereço válido do ResearchGate.", "error")
        elif photo_url and not re.fullmatch(r"https?://[^\s]+", photo_url, re.I):
            flash("Informe um endereço válido para a fotografia.", "error")
        else:
            try:
                if request.form.get("remove_photo") == "on":
                    author.photo = ""
                if photo_url:
                    author.photo = photo_url
                if photo_file and photo_file.filename:
                    author.photo = upload_author_photo(photo_file)
            except ImageUploadError as error:
                flash(str(error), "error")
                return redirect(url_for("admin.authors"))

            author.name = name
            author.slug = requested_slug
            author.email = email
            author.role = role[:140]
            author.headline = headline[:220]
            author.academic_background = request.form.get("academic_background", "").strip()
            author.institution = institution[:220]
            author.bio = request.form.get("bio", "").strip()
            author.interests = request.form.get("interests", "").strip()
            author.projects = request.form.get("projects", "").strip()
            author.orcid = orcid.upper()
            author.google_scholar = google_scholar
            author.researchgate = researchgate
            author.publications = request.form.get("publications", "").strip()
            author.editorial_experience = request.form.get("editorial_experience", "").strip()
            author.display_order = max(0, request.form.get("display_order", 100, type=int) or 100)
            if request.form.get("active_present") == "1":
                author.active = request.form.get("active") == "on"
            elif not author.id:
                author.active = True
            if not author.id:
                db.session.add(author)
            db.session.commit()
            flash("Perfil do autor guardado com sucesso.", "success")
            return redirect(url_for("admin.authors"))
    return render_template("admin/authors.html", authors=Author.query.order_by(Author.name).all())


@admin_bp.post("/autores/<int:author_id>/eliminar")
@login_required
def delete_author(author_id):
    validate_csrf()
    author = db.get_or_404(Author, author_id)
    from governance_models import TeamMember
    if author.articles or TeamMember.query.filter_by(author_id=author_id).first():
        flash("Não é possível eliminar um autor que possui artigos.", "error")
    else:
        db.session.delete(author); db.session.commit(); flash("Autor eliminado.", "success")
    return redirect(url_for("admin.authors"))


@admin_bp.route("/categorias", methods=["GET", "POST"])
@login_required
def categories():
    if request.method == "POST":
        validate_csrf()
        name = request.form.get("name", "").strip()
        category_id = request.form.get("category_id")
        try:
            parsed_category_id = int(category_id) if category_id else None
        except (TypeError, ValueError):
            flash("Identificador de categoria inválido.", "error")
            return redirect(url_for("admin.categories"))
        category = db.session.get(Category, parsed_category_id) if parsed_category_id else Category()
        if parsed_category_id and not category:
            abort(404)
        duplicate = Category.query.filter(Category.name == name, Category.id != category.id).first()
        if name and not duplicate:
            category.name = name; category.slug = slugify(name)
            if not category.id:
                db.session.add(category)
            db.session.commit(); flash("Categoria guardada.", "success")
    return render_template("admin/categories.html", categories=Category.query.order_by(Category.name).all())


@admin_bp.post("/categorias/<int:category_id>/eliminar")
@login_required
def delete_category(category_id):
    validate_csrf()
    category = db.get_or_404(Category, category_id)
    if category.articles:
        flash("Não é possível eliminar uma categoria que possui artigos.", "error")
    else:
        db.session.delete(category); db.session.commit(); flash("Categoria eliminada.", "success")
    return redirect(url_for("admin.categories"))


@admin_bp.get("/revistas")
@login_required
def journals():
    from governance import has_any_permission, journal_scope
    if not any(has_any_permission(p) for p in ('journal.manage','journal.publish','manuscript.production')):
        abort(403)
    return render_template(
        "admin/journals.html",
        journals=journal_scope(Journal.query).order_by(Journal.updated_at.desc()).all(),
    )


def render_journal_form(journal):
    authors = submitted_author_rows(request.form) if request.method == "POST" and ("authors_structured" in request.form or "author_name" in request.form) else journal_authors(journal)
    return render_template("admin/journal_form.html", journal=journal, journal_authors=authors)


@admin_bp.route("/revistas/nova", methods=["GET", "POST"])
@admin_bp.route("/revistas/<int:journal_id>/editar", methods=["GET", "POST"])
@login_required
def journal_form(journal_id=None):
    from governance import journal_access
    journal_access(journal_id)
    journal = db.session.get(Journal, journal_id) if journal_id else Journal()
    if journal_id and not journal:
        abort(404)

    if request.method == "POST":
        validate_csrf()
        title = request.form.get("title", "").strip()
        field = request.form.get("field", "").strip()
        description = request.form.get("description", "").strip()
        issn = request.form.get("issn", "").strip().upper()
        base_slug = slugify(request.form.get("slug") or title)
        duplicate = Journal.query.filter(Journal.slug == base_slug, Journal.id != journal.id).first()
        cover_url = request.form.get("cover_image", "").strip()
        cover_file = request.files.get("cover_file")
        submitted_authors = None
        if ("authors_structured" in request.form or "author_name" in request.form):
            try:
                submitted_authors = validate_authors(submitted_author_rows(request.form))
            except ValueError as error:
                flash(str(error), "error")
                return render_journal_form(journal)
        if any(len(request.form.get(name, "").strip()) > 20000 for name in (*EDITORIAL_FIELDS, "authors_orcid")):
            flash("As informações editoriais devem ter até 20000 caracteres por campo.", "error")
            return render_journal_form(journal)
        if any(len(request.form.get(name, "").strip()) > maximum for name, maximum in ARTICLE_FIELD_LIMITS.items()):
            flash("Os campos do artigo devem ter até 20000 caracteres; palavras-chave até 2000.", "error")
            return render_journal_form(journal)
        if len(request.form.get("content_markdown", "")) > 400000 or len(request.form.get("references", "")) > 100000:
            flash("O conteúdo do artigo deve ter até 400000 caracteres e as referências até 100000.", "error")
            return render_journal_form(journal)
        invalid_length = any(len(request.form.get(name, "").strip()) > maximum for name, maximum in {
            "article_title": 300, "article_title_en": 300, "corresponding_author": 2000, "slug": 200, "abbreviation": 30, "frequency": 80, "current_issue": 120,
            "doi": 180, "cover_image": 600, "cover_alt": 300,
        }.items())

        if not 3 <= len(title) <= 180:
            flash("O título deve ter entre 3 e 180 caracteres.", "error")
        elif not field or len(field) > 140:
            flash("Informe uma área científica válida.", "error")
        elif not 20 <= len(description) <= 4000:
            flash("A descrição deve ter entre 20 e 4000 caracteres.", "error")
        elif not base_slug:
            flash("Não foi possível gerar o endereço da revista.", "error")
        elif duplicate:
            flash("Já existe uma revista com este endereço.", "error")
        elif invalid_length:
            flash("Um dos campos excede o tamanho permitido. Reduza o texto e tente novamente.", "error")
        elif issn and not re.fullmatch(r"[0-9]{4}-[0-9]{3}[0-9X]", issn):
            flash("O ISSN deve seguir o formato 1234-567X.", "error")
        elif cover_url and not re.fullmatch(r"https?://[^\s]+", cover_url, re.I):
            flash("Informe um endereço válido para a capa.", "error")
        else:
            try:
                if cover_file and cover_file.filename:
                    cover_url = upload_journal_cover(cover_file)
            except ImageUploadError as error:
                flash(str(error), "error")
                return render_journal_form(journal)

            for name in ("article_title", "article_title_en", "corresponding_author"):
                if name in request.form:
                    setattr(journal, name, request.form[name].strip())
            journal.title = title
            journal.slug = base_slug
            journal.abbreviation = request.form.get("abbreviation", "").strip().upper()
            journal.field = field
            journal.description = description
            journal.issn = issn
            journal.frequency = request.form.get("frequency", "").strip()
            journal.current_issue = request.form.get("current_issue", "").strip()
            journal.doi = request.form.get("doi", "").strip()
            if submitted_authors is not None:
                journal.authors_data = json.dumps(submitted_authors, ensure_ascii=False)
                journal.authors_orcid = legacy_author_lines(submitted_authors)
            else:
                journal.authors_orcid = request.form.get("authors_orcid", "").strip()
                journal.authors_data = ""
            for name in EDITORIAL_FIELDS:
                setattr(journal, name, request.form.get(name, "").strip())
            publication_date_raw = request.form.get("publication_date", "").strip()
            try:
                journal.publication_date = datetime.strptime(publication_date_raw, "%Y-%m-%d").date() if publication_date_raw else None
            except ValueError:
                flash("Informe uma data de publicação válida.", "error")
                return render_journal_form(journal)
            for name in ARTICLE_FIELD_LIMITS:
                if name in request.form:
                    setattr(journal, name, request.form[name].strip())
            journal.content_markdown = request.form.get("content_markdown", "").strip()
            journal.references = request.form.get("references", "").strip()
            journal.editorial_policy = request.form.get("editorial_policy", "").strip()
            journal.copyright_policy = request.form.get("copyright_policy", "").strip()
            journal.cover_image = cover_url
            journal.cover_alt = request.form.get("cover_alt", "").strip()
            requested_published = request.form.get("save_mode") != "draft" and request.form.get("published") == "on"
            if requested_published != bool(journal.published):
                journal_access(journal.id,publishing=True)
            journal.published = requested_published
            if not journal.id:
                db.session.add(journal)
            from submissions import publication_saved
            publication_saved(journal)
            db.session.commit()
            flash("Revista guardada com sucesso.", "success")
            return redirect(url_for("admin.journals"))

    return render_journal_form(journal)


@admin_bp.post("/revistas/<int:journal_id>/publicacao")
@login_required
def toggle_journal(journal_id):
    from governance import journal_access
    journal_access(journal_id,publishing=True)
    validate_csrf()
    journal = db.get_or_404(Journal, journal_id)
    journal.published = not journal.published
    from submissions import publication_saved
    publication_saved(journal)
    db.session.commit()
    flash("Revista publicada." if journal.published else "Revista ocultada.", "success")
    return redirect(url_for("admin.journals"))


@admin_bp.post("/revistas/<int:journal_id>/eliminar")
@login_required
def delete_journal(journal_id):
    validate_csrf()
    journal = db.get_or_404(Journal, journal_id)
    from submission_models import Manuscript, SubmissionSetting, PublicationAsset
    from governance_models import TeamAppointment
    if TeamAppointment.query.filter_by(journal_id=journal_id).first() or PublicationAsset.query.filter_by(journal_id=journal_id).first():
        abort(409,description='Esta revista tem mandatos ou ficheiros editoriais associados. Oculte-a para preservar o histórico.')
    if Manuscript.query.filter(db.or_(Manuscript.journal_id == journal_id, Manuscript.publication_id == journal_id)).first() or db.session.get(SubmissionSetting, journal_id):
        abort(409, description="Esta revista está ligada ao fluxo editorial. Oculte-a em vez de eliminar os registos.")
    from reader_accounts import ReaderJournal
    from governance import audit
    ReaderJournal.query.filter_by(journal_id=journal_id).delete(synchronize_session=False)
    audit('journal.deleted','journal',journal_id)
    db.session.delete(journal)
    db.session.commit()
    flash("Revista eliminada.", "success")
    return redirect(url_for("admin.journals"))


@admin_bp.get("/comentarios")
@login_required
def comments():
    status = request.args.get("estado", "pendentes")
    query = Comment.query.join(Article).order_by(Comment.created_at.desc())
    if status == "publicados":
        query = query.filter(Comment.approved.is_(True))
    elif status == "todos":
        pass
    else:
        status = "pendentes"
        query = query.filter(Comment.approved.is_(False))
    return render_template("admin/comments.html", comments=query.all(), status=status)


@admin_bp.post("/comentarios/<int:comment_id>/estado")
@login_required
def update_comment_status(comment_id):
    validate_csrf()
    comment = db.get_or_404(Comment, comment_id)
    action = request.form.get("action")
    if action not in {"approve", "reject"}:
        abort(400)
    comment.approved = action == "approve"
    db.session.commit()
    flash("Estado do comentário atualizado.", "success")
    return redirect(url_for("admin.comments", estado=request.form.get("return_status", "pendentes")))


@admin_bp.post("/comentarios/<int:comment_id>/eliminar")
@login_required
def delete_comment(comment_id):
    validate_csrf()
    comment = db.get_or_404(Comment, comment_id)
    db.session.delete(comment)
    db.session.commit()
    flash("Comentário eliminado.", "success")
    return redirect(url_for("admin.comments", estado=request.form.get("return_status", "pendentes")))


@admin_bp.get("/contactos")
@login_required
def contacts():
    messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    ContactMessage.query.filter_by(read=False).update({"read": True}); db.session.commit()
    return render_template("admin/contacts.html", messages=messages)


@admin_bp.get("/subscritores")
@login_required
def subscribers():
    return render_template("admin/subscribers.html", subscribers=Subscriber.query.order_by(Subscriber.created_at.desc()).all())


@admin_bp.post("/contactos/<int:message_id>/eliminar")
@login_required
def delete_contact(message_id):
    validate_csrf()
    message = db.get_or_404(ContactMessage, message_id)
    db.session.delete(message)
    db.session.commit()
    flash("Mensagem eliminada.", "success")
    return redirect(url_for("admin.contacts"))


@admin_bp.post("/subscritores/<int:subscriber_id>/estado")
@login_required
def toggle_subscriber(subscriber_id):
    validate_csrf()
    subscriber = db.get_or_404(Subscriber, subscriber_id)
    subscriber.active = not subscriber.active
    db.session.commit()
    flash("Estado do subscritor atualizado.", "success")
    return redirect(url_for("admin.subscribers"))


def csv_safe_cell(value):
    """Impede execução de fórmulas ao abrir exportações em folhas de cálculo."""
    text_value = str(value if value is not None else "")
    return "'" + text_value if text_value.startswith(("=", "+", "-", "@", "\t", "\r")) else text_value


def csv_download(filename, headers, rows):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(tuple(csv_safe_cell(value) for value in row) for row in rows)
    response = Response("\ufeff" + stream.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@admin_bp.get("/contactos/exportar.csv")
@login_required
def export_contacts():
    rows = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    return csv_download("contactos.csv", ["Nome", "E-mail", "Assunto", "Mensagem", "Data"], ((x.name, x.email, x.subject, x.message, x.created_at.isoformat()) for x in rows))


@admin_bp.get("/subscritores/exportar.csv")
@login_required
def export_subscribers():
    rows = Subscriber.query.order_by(Subscriber.created_at.desc()).all()
    return csv_download("subscritores.csv", ["E-mail", "Ativo", "Data"], ((x.email, "sim" if x.active else "não", x.created_at.isoformat()) for x in rows))








