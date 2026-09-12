import hmac
import csv
import io
import os
import re
import secrets
from datetime import datetime
from functools import wraps
import requests
from flask import Blueprint, Response, abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import or_
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import limiter
from models import AdminUser, Article, Author, Category, ContactMessage, Journal, JournalIssue, Subscriber, db, utcnow
from storage import ImageUploadError, upload_article_image

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def slugify(value):
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9à-ÿ]+", "-", value, flags=re.I)
    return value.strip("-")


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
    services = {
        "Assistente IA": bool(os.getenv("AI_WORKER_URL")),
        "Cloudinary": all(os.getenv(key) for key in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET")),
        "Turnstile": bool(os.getenv("TURNSTILE_SITE_KEY") and os.getenv("TURNSTILE_SECRET_KEY")),
        "Limite distribuído": bool(os.getenv("RATELIMIT_STORAGE_URI")),
    }
    return render_template(
        "admin/dashboard.html", article_count=Article.query.count(),
        draft_count=Article.query.filter_by(status="draft").count(),
        scheduled_count=Article.query.filter_by(status="scheduled").count(), journal_count=Journal.query.count(),
        contact_count=ContactMessage.query.filter_by(read=False).count(), subscriber_count=Subscriber.query.filter_by(active=True).count(),
        recent_articles=Article.query.order_by(Article.updated_at.desc()).limit(6).all(), services=services,
    )


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
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    query = Article.query.join(Author).join(Category)
    if search:
        like = f"%{search.lower()}%"
        query = query.filter(or_(db.func.lower(Article.title).like(like), db.func.lower(Author.name).like(like), db.func.lower(Category.name).like(like)))
    if status in {"draft", "published", "scheduled"}:
        query = query.filter(Article.status == status)
    return render_template("admin/articles.html", articles=query.order_by(Article.updated_at.desc()).all(), search=search, selected_status=status)


@admin_bp.get("/revistas")
@login_required
def journals():
    search = request.args.get("q", "").strip()
    visibility = request.args.get("visibility", "").strip()
    query = Journal.query
    if search:
        like = f"%{search.lower()}%"
        query = query.filter(or_(db.func.lower(Journal.title).like(like), db.func.lower(Journal.abbreviation).like(like), db.func.lower(Journal.field).like(like)))
    if visibility == "published":
        query = query.filter(Journal.active.is_(True))
    elif visibility == "hidden":
        query = query.filter(Journal.active.is_(False))
    return render_template("admin/journals.html", journals=query.order_by(Journal.updated_at.desc()).all(), search=search, selected_visibility=visibility)


@admin_bp.route("/revistas/<int:journal_id>/edicoes/nova", methods=["GET", "POST"])
@admin_bp.route("/revistas/edicoes/<int:issue_id>/editar", methods=["GET", "POST"])
@login_required
def journal_issue_form(journal_id=None, issue_id=None):
    issue = db.session.get(JournalIssue, issue_id) if issue_id else JournalIssue(journal_id=journal_id)
    if issue_id and not issue:
        abort(404)
    journal = db.get_or_404(Journal, issue.journal_id)
    if request.method == "POST":
        validate_csrf()
        try:
            volume = int(request.form.get("volume", ""))
            number = int(request.form.get("number", ""))
            year = int(request.form.get("year", ""))
        except ValueError:
            volume = number = year = 0
        duplicate = JournalIssue.query.filter_by(journal_id=journal.id, volume=volume, number=number, year=year).filter(JournalIssue.id != issue.id).first()
        if volume < 1 or number < 1 or not 1900 <= year <= 2200:
            flash("Informe volume, número e ano válidos.", "error")
        elif duplicate:
            flash("Esta edição já existe na revista.", "error")
        else:
            issue.volume, issue.number, issue.year = volume, number, year
            issue.title = request.form.get("title", "").strip()[:180]
            issue.description = request.form.get("description", "").strip()[:3000]
            issue.published = request.form.get("published") == "on"
            issue.published_at = issue.published_at or (utcnow() if issue.published else None)
            image_file = request.files.get("cover_file")
            try:
                issue.cover_image = upload_article_image(image_file) if image_file and image_file.filename else request.form.get("cover_image", "").strip()[:600]
            except ImageUploadError as error:
                flash(str(error), "error")
                return render_template("admin/journal_issue_form.html", issue=issue, journal=journal)
            if not issue.id:
                db.session.add(issue)
            journal.current_issue = issue.label if issue.published else journal.current_issue
            db.session.commit()
            flash("Edição guardada com sucesso.", "success")
            return redirect(url_for("admin.journal_form", journal_id=journal.id))
    return render_template("admin/journal_issue_form.html", issue=issue, journal=journal)


@admin_bp.post("/revistas/edicoes/<int:issue_id>/eliminar")
@login_required
def delete_journal_issue(issue_id):
    validate_csrf()
    issue = db.get_or_404(JournalIssue, issue_id)
    journal_id = issue.journal_id
    if issue.articles:
        flash("Não é possível eliminar uma edição que possui artigos.", "error")
    else:
        db.session.delete(issue)
        db.session.commit()
        flash("Edição eliminada.", "success")
    return redirect(url_for("admin.journal_form", journal_id=journal_id))


@admin_bp.route("/revistas/nova", methods=["GET", "POST"])
@admin_bp.route("/revistas/<int:journal_id>/editar", methods=["GET", "POST"])
@login_required
def journal_form(journal_id=None):
    journal = db.session.get(Journal, journal_id) if journal_id else Journal()
    if journal_id and not journal:
        abort(404)
    if request.method == "POST":
        validate_csrf()
        title = request.form.get("title", "").strip()
        abbreviation = request.form.get("abbreviation", "").strip().upper()
        field = request.form.get("field", "").strip()
        description = request.form.get("description", "").strip()
        contact_email = request.form.get("contact_email", "").strip().lower()
        base_slug = slugify(request.form.get("slug") or title)
        duplicate_title = Journal.query.filter(db.func.lower(Journal.title) == title.lower(), Journal.id != journal.id).first()
        duplicate_abbreviation = Journal.query.filter(db.func.lower(Journal.abbreviation) == abbreviation.lower(), Journal.id != journal.id).first()
        if not 3 <= len(title) <= 180 or not base_slug:
            flash("Informe um título válido com até 180 caracteres.", "error")
        elif not re.fullmatch(r"[A-Z0-9-]{2,20}", abbreviation):
            flash("A sigla deve ter 2 a 20 letras, números ou hífen.", "error")
        elif not 3 <= len(field) <= 140 or not 20 <= len(description) <= 3000:
            flash("Informe a área científica e uma descrição com pelo menos 20 caracteres.", "error")
        elif contact_email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact_email):
            flash("Informe um e-mail editorial válido.", "error")
        elif duplicate_title or duplicate_abbreviation:
            flash("Já existe uma revista com esse título ou sigla.", "error")
        else:
            candidate, number = base_slug, 2
            while Journal.query.filter(Journal.slug == candidate, Journal.id != journal.id).first():
                candidate, number = f"{base_slug}-{number}", number + 1
            journal.title = title
            journal.slug = candidate
            journal.abbreviation = abbreviation
            journal.field = field
            journal.description = description
            journal.frequency = request.form.get("frequency", "Anual").strip()[:80] or "Anual"
            journal.current_issue = request.form.get("current_issue", "").strip()[:100]
            journal.status = request.form.get("status", "Em preparação").strip()[:80] or "Em preparação"
            journal.issn_print = request.form.get("issn_print", "").strip()[:20]
            journal.issn_online = request.form.get("issn_online", "").strip()[:20]
            journal.contact_email = contact_email[:180]
            journal.guidelines = request.form.get("guidelines", "").strip()
            journal.active = request.form.get("active") == "on"
            image_file = request.files.get("image_file")
            try:
                journal.image = upload_article_image(image_file) if image_file and image_file.filename else request.form.get("image", "").strip()[:600]
            except ImageUploadError as error:
                flash(str(error), "error")
                return render_template("admin/journal_form.html", journal=journal)
            if not journal.id:
                db.session.add(journal)
            db.session.commit()
            flash("Revista guardada com sucesso.", "success")
            return redirect(url_for("admin.journals"))
    return render_template("admin/journal_form.html", journal=journal)


@admin_bp.post("/revistas/<int:journal_id>/eliminar")
@login_required
def delete_journal(journal_id):
    validate_csrf()
    journal = db.get_or_404(Journal, journal_id)
    if any(issue.articles for issue in journal.issues):
        flash("Não é possível eliminar uma revista com artigos associados.", "error")
    else:
        db.session.delete(journal)
        db.session.commit()
        flash("Revista eliminada.", "success")
    return redirect(url_for("admin.journals"))


@admin_bp.post("/revistas/<int:journal_id>/visibilidade")
@login_required
def toggle_journal_visibility(journal_id):
    validate_csrf()
    journal = db.get_or_404(Journal, journal_id)
    journal.active = not journal.active
    db.session.commit()
    flash(f"Revista {'publicada' if journal.active else 'ocultada'} com sucesso.", "success")
    return redirect(request.referrer if request.referrer and request.referrer.startswith(request.host_url) else url_for("admin.journals"))


def parse_datetime(value):
    return datetime.fromisoformat(value) if value else None


def article_form_context(article):
    return {
        "article": article,
        "authors": Author.query.filter_by(active=True).all(),
        "categories": Category.query.order_by(Category.name).all(),
        "journal_issues": JournalIssue.query.join(Journal).order_by(Journal.title, JournalIssue.year.desc(), JournalIssue.number.desc()).all(),
    }


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
                return render_template("admin/article_form.html", **article_form_context(article))
            if not 10 <= len(summary) <= 2000 or status not in {"draft", "published", "scheduled"}:
                flash("O resumo deve ter entre 10 e 2000 caracteres e o estado deve ser válido.", "error")
                return render_template("admin/article_form.html", **article_form_context(article))
            if status in {"published", "scheduled"} and len(body) < 50:
                flash("Artigos publicados ou programados precisam de conteúdo completo.", "error")
                return render_template("admin/article_form.html", **article_form_context(article))
            if not db.session.get(Author, author_id) or not db.session.get(Category, category_id):
                flash("Selecione um autor e uma categoria existentes.", "error")
                return render_template("admin/article_form.html", **article_form_context(article))
            article.title = title
            base_slug = slugify(request.form.get("slug") or title)
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
                return render_template("admin/article_form.html", **article_form_context(article))
            article.read_minutes = read_minutes
            article.author_id = author_id
            article.category_id = category_id
            issue_id = request.form.get("journal_issue_id", "").strip()
            article.journal_issue_id = int(issue_id) if issue_id and db.session.get(JournalIssue, int(issue_id)) else None
            article.featured = request.form.get("featured") == "on"
            article.status = status
            article.scheduled_at = scheduled_at
            if article.status == "published" and not article.published_at:
                article.published_at = utcnow()
            if article.status == "scheduled" and not article.scheduled_at:
                flash("Informe a data e hora da publicação programada.", "error")
                return render_template("admin/article_form.html", **article_form_context(article))
            if not article.id:
                db.session.add(article)
            db.session.commit()
            flash("Artigo guardado com sucesso.", "success")
            return redirect(url_for("admin.articles"))
    return render_template("admin/article_form.html", **article_form_context(article))


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
