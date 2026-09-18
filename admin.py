import hmac
import csv
import io
import os
import re
import secrets
import unicodedata
from datetime import datetime
from functools import wraps
import requests
from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import limiter
from models import AdminUser, Article, Author, Category, ContactMessage, Subscriber, db, utcnow
from storage import ImageUploadError, upload_article_image

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def slugify(value):
    value = unicodedata.normalize("NFKD", (value or "").strip())
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:260]


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin.login", next=request.path))
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


@admin_bp.app_context_processor
def admin_context():
    return {"csrf_token": csrf_token, "turnstile_site_key": os.getenv("TURNSTILE_SITE_KEY", "")}


def turnstile_valid():
    secret = os.getenv("TURNSTILE_SECRET_KEY")
    if not secret:
        return os.getenv("REQUIRE_TURNSTILE", "false").lower() != "true"
    try:
        response = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={"secret": secret, "response": request.form.get("cf-turnstile-response", ""), "remoteip": request.remote_addr},
            timeout=8,
        )
        return bool(response.json().get("success"))
    except (requests.RequestException, ValueError):
        return False


@admin_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute; 20 per hour")
def login():
    if request.method == "POST":
        validate_csrf()
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        database_admin = AdminUser.query.filter(db.func.lower(AdminUser.username) == username, AdminUser.active.is_(True)).first()
        configured_user = os.getenv("ADMIN_USERNAME")
        configured_password = os.getenv("ADMIN_PASSWORD")
        configured_password_hash = os.getenv("ADMIN_PASSWORD_HASH")
        if not turnstile_valid():
            flash("A verificação de segurança falhou. Actualize a página e tente novamente.", "error")
        elif database_admin and check_password_hash(database_admin.password_hash, password):
            session.clear()
            session.permanent = True
            session["admin_authenticated"] = True
            session["admin_id"] = database_admin.id
            session["admin_username"] = database_admin.username
            session["csrf_token"] = secrets.token_urlsafe(32)
            database_admin.last_login_at = utcnow()
            db.session.commit()
            return redirect(url_for("admin.dashboard"))
        elif not configured_user or not (configured_password_hash or configured_password):
            flash("As credenciais administrativas ainda não estão configuradas.", "error")
        elif hmac.compare_digest(username, configured_user.lower()) and ((configured_password_hash and check_password_hash(configured_password_hash, password)) or (configured_password and hmac.compare_digest(password, configured_password))):
            session.clear()
            session.permanent = True
            session["admin_authenticated"] = True
            session["admin_username"] = configured_user
            session["csrf_token"] = secrets.token_urlsafe(32)
            return redirect(url_for("admin.dashboard"))
        else:
            flash("Utilizador ou palavra-passe inválidos.", "error")
    return render_template("admin/login.html")


@admin_bp.post("/logout")
@login_required
def logout():
    validate_csrf()
    session.clear()
    return redirect(url_for("admin.login"))


@admin_bp.get("")
@login_required
def dashboard():
    return render_template("admin/dashboard.html", article_count=Article.query.count(), draft_count=Article.query.filter_by(status="draft").count(), contact_count=ContactMessage.query.filter_by(read=False).count(), subscriber_count=Subscriber.query.filter_by(active=True).count(), recent_articles=Article.query.order_by(Article.updated_at.desc()).limit(6).all())


@admin_bp.route("/administradores", methods=["GET", "POST"])
@login_required
def administrators():
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
        elif len(password) < 12:
            flash("A palavra-passe deve ter pelo menos 12 caracteres.", "error")
        elif password != password_confirmation:
            flash("A confirmação da palavra-passe não corresponde.", "error")
        elif duplicate_username or duplicate_email:
            flash("Já existe um administrador com esse utilizador ou e-mail.", "error")
        else:
            db.session.add(AdminUser(username=username, display_name=display_name, email=email, password_hash=generate_password_hash(password)))
            db.session.commit()
            flash("Novo administrador criado com sucesso.", "success")
            return redirect(url_for("admin.administrators"))
    return render_template("admin/administrators.html", administrators=AdminUser.query.order_by(AdminUser.created_at.desc()).all())


@admin_bp.get("/artigos")
@login_required
def articles():
    return render_template("admin/articles.html", articles=Article.query.order_by(Article.updated_at.desc()).all())


def parse_datetime(value):
    return datetime.fromisoformat(value) if value else None


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
    article = db.session.get(Article, article_id) if article_id else Article()
    if article_id and not article:
        abort(404)
    if request.method == "POST":
        validate_csrf()
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
            if not 10 <= len(summary) <= 2000 or status not in {"draft", "published", "scheduled"}:
                flash("O resumo deve ter entre 10 e 2000 caracteres e o estado deve ser válido.", "error")
                return render_template("admin/article_form.html", article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all())
            if status in {"published", "scheduled"} and len(body) < 50:
                flash("Artigos publicados ou programados precisam de conteúdo completo.", "error")
                return render_template("admin/article_form.html", article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all())
            if not db.session.get(Author, author_id) or not db.session.get(Category, category_id):
                flash("Selecione um autor e uma categoria existentes.", "error")
                return render_template("admin/article_form.html", article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all())
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
            db.session.commit()
            flash("Artigo guardado com sucesso.", "success")
            return redirect(url_for("admin.articles"))
    return render_template("admin/article_form.html", article=article, authors=Author.query.filter_by(active=True).all(), categories=Category.query.order_by(Category.name).all())


@admin_bp.post("/artigos/<int:article_id>/eliminar")
@login_required
def delete_article(article_id):
    validate_csrf()
    article = db.get_or_404(Article, article_id)
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
        if name:
            author_id = request.form.get("author_id")
            author = db.session.get(Author, int(author_id)) if author_id else Author()
            author.name = name
            author.email = request.form.get("email", "").strip() or None
            author.bio = request.form.get("bio", "").strip()
            if not author.id:
                db.session.add(author)
            db.session.commit()
            flash("Autor guardado.", "success")
    return render_template("admin/authors.html", authors=Author.query.order_by(Author.name).all())


@admin_bp.post("/autores/<int:author_id>/eliminar")
@login_required
def delete_author(author_id):
    validate_csrf()
    author = db.get_or_404(Author, author_id)
    if author.articles:
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
        category = db.session.get(Category, int(category_id)) if category_id else Category()
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


def csv_download(filename, headers, rows):
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow(headers)
    writer.writerows(rows)
    return Response("\ufeff" + stream.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


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
