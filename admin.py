import hmac
import os
import re
import secrets
from datetime import datetime
from functools import wraps
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from models import Article, Author, Category, ContactMessage, Subscriber, db, utcnow

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
    return {"csrf_token": csrf_token}


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        validate_csrf()
        configured_user = os.getenv("ADMIN_USERNAME")
        configured_password = os.getenv("ADMIN_PASSWORD")
        if not configured_user or not configured_password:
            flash("Configure ADMIN_USERNAME e ADMIN_PASSWORD no Render antes de entrar.", "error")
        elif hmac.compare_digest(request.form.get("username", ""), configured_user) and hmac.compare_digest(request.form.get("password", ""), configured_password):
            session.clear()
            session["admin_authenticated"] = True
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


@admin_bp.get("/artigos")
@login_required
def articles():
    return render_template("admin/articles.html", articles=Article.query.order_by(Article.updated_at.desc()).all())


def parse_datetime(value):
    return datetime.fromisoformat(value) if value else None


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
        if len(title) < 5:
            flash("O título deve ter pelo menos cinco caracteres.", "error")
        else:
            article.title = title
            base_slug = slugify(request.form.get("slug") or title)
            candidate, number = base_slug, 2
            while Article.query.filter(Article.slug == candidate, Article.id != article.id).first():
                candidate, number = f"{base_slug}-{number}", number + 1
            article.slug = candidate
            article.summary = request.form.get("summary", "").strip()
            article.body = request.form.get("body", "").strip()
            article.image = request.form.get("image", "").strip()
            article.read_minutes = max(1, int(request.form.get("read_minutes") or 5))
            article.author_id = int(request.form["author_id"])
            article.category_id = int(request.form["category_id"])
            article.featured = request.form.get("featured") == "on"
            article.status = request.form.get("status", "draft")
            article.scheduled_at = parse_datetime(request.form.get("scheduled_at"))
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
