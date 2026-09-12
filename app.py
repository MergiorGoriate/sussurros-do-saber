from flask import Flask, Response, jsonify, redirect, render_template, request, url_for
from xml.sax.saxutils import escape
import requests
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import bleach
import markdown
from markupsafe import Markup
from sqlalchemy import inspect, or_, text
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_migrate import Migrate
from admin import admin_bp
from extensions import limiter
from models import Article, Author, Category, ContactMessage, Journal, Subscriber, db, utcnow

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
production = bool(os.getenv("RENDER") or os.getenv("FLASK_ENV") == "production")
secret_key = os.getenv("SECRET_KEY")
if production and (not secret_key or len(secret_key) < 32 or secret_key == "local-development-only-change-me"):
    raise RuntimeError("SECRET_KEY segura (mínimo 32 caracteres) é obrigatória em produção.")
database_url = os.getenv("DATABASE_URL", "sqlite:///sussurros.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config.update(
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=secret_key or "local-development-only-change-me",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("RENDER", "").lower() == "true" or os.getenv("SESSION_COOKIE_SECURE", "").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=9 * 1024 * 1024,
)
SITE_URL = os.getenv("SITE_URL", "https://sussurrosdosaber.com").rstrip("/")
db.init_app(app)
migrate = Migrate(app, db)
limiter.init_app(app)
app.register_blueprint(admin_bp)


@app.template_filter("markdown")
def render_markdown(value):
    html = markdown.markdown(value or "", extensions=["extra", "sane_lists"])
    allowed = set(bleach.sanitizer.ALLOWED_TAGS).union({"p", "h2", "h3", "h4", "blockquote", "pre", "code", "ul", "ol", "li", "hr", "table", "thead", "tbody", "tr", "th", "td"})
    return Markup(bleach.clean(html, tags=allowed, attributes={"a": ["href", "title", "rel"]}, protocols=["http", "https", "mailto"], strip=True))


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'; "
        "object-src 'none'; img-src 'self' data: https:; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdnjs.cloudflare.com https://challenges.cloudflare.com; "
        "frame-src https://challenges.cloudflare.com; connect-src 'self' https://challenges.cloudflare.com; upgrade-insecure-requests",
    )
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=604800, stale-while-revalidate=86400"
    else:
        private_response = request.method != "GET" or request.path.startswith(("/admin", "/api/"))
        response.headers.setdefault("Cache-Control", "no-store" if private_response else "public, max-age=60")
    if request.path.startswith("/admin"):
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
    return response


@app.context_processor
def site_context():
    return {"site_url": SITE_URL}


@app.errorhandler(429)
def rate_limited(error):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "answer": "Limite temporário atingido. Aguarde antes de tentar novamente."}), 429
    return render_template("429.html"), 429

SEED_ARTICLES = [
    {"id": 1, "category": "Biologia", "title": "Bactérias endofíticas: os microrganismos invisíveis que protegem as plantas", "summary": "Dentro das plantas vivem comunidades capazes de produzir compostos com potencial antibacteriano.", "author": "Mergior Goriate", "date": "10 Setembro 2026", "read_time": "7 min", "image": "https://images.unsplash.com/photo-1532187863486-abf9dbad1b69?auto=format&fit=crop&w=1400&q=85", "featured": True},
    {"id": 2, "category": "Saúde", "title": "Por que sentimos sono depois de comer?", "summary": "A digestão, as hormonas e o relógio biológico explicam a queda de energia após as refeições.", "author": "Redacção", "date": "8 Setembro 2026", "read_time": "5 min", "image": "https://images.unsplash.com/photo-1532094349884-543bc11b234d?auto=format&fit=crop&w=1000&q=85"},
    {"id": 3, "category": "Ambiente", "title": "Plantas medicinais de Nampula e o futuro da investigação local", "summary": "Conhecimento tradicional e métodos laboratoriais podem abrir caminhos para novas descobertas.", "author": "Mergior Goriate", "date": "6 Setembro 2026", "read_time": "9 min", "image": "https://images.unsplash.com/photo-1531058240690-006c446962d8?auto=format&fit=crop&w=1000&q=85"},
    {"id": 4, "category": "Espaço", "title": "Como os radiotelescópios africanos observam o universo", "summary": "A radioastronomia transforma África num ponto estratégico para estudar galáxias distantes.", "author": "Redacção", "date": "4 Setembro 2026", "read_time": "6 min", "image": "https://images.unsplash.com/photo-1462331940025-496dfbfc7564?auto=format&fit=crop&w=1000&q=85"},
    {"id": 5, "category": "Educação", "title": "Cinco estratégias para aprender Biologia com rigor científico", "summary": "Da observação à explicação: um método simples para estudar processos biológicos.", "author": "Mergior Goriate", "date": "1 Setembro 2026", "read_time": "4 min", "image": "https://images.unsplash.com/photo-1532094349884-543bc11b234d?auto=format&fit=crop&w=1000&q=85"},
    {"id": 6, "category": "Tecnologia", "title": "Python na investigação: da folha de cálculo à análise reprodutível", "summary": "Como estudantes podem automatizar tarefas, explorar dados e documentar melhor as suas análises.", "author": "Mergior Goriate", "date": "28 Agosto 2026", "read_time": "8 min", "image": "https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1000&q=85"},
]

JOURNALS = [
    {"slug": "cadernos-de-biodiversidade", "title": "Cadernos de Biodiversidade", "abbr": "CBIO", "field": "Biologia e Ecologia", "description": "Estudos sobre biodiversidade, conservação, ecologia e recursos naturais, com atenção aos contextos africanos.", "frequency": "Semestral", "issue": "Vol. 1 · N.º 1", "status": "Recebendo artigos"},
    {"slug": "saude-e-comunidade", "title": "Saúde & Comunidade", "abbr": "SACO", "field": "Saúde Pública", "description": "Investigação e práticas sobre saúde comunitária, nutrição, prevenção e determinantes sociais da saúde.", "frequency": "Semestral", "issue": "Vol. 1 · N.º 1", "status": "Em preparação"},
    {"slug": "educacao-cientifica", "title": "Educação Científica", "abbr": "EDCI", "field": "Ensino e Aprendizagem", "description": "Pesquisa e experiências sobre ensino de Ciências e Biologia, formação docente e inovação pedagógica.", "frequency": "Anual", "issue": "Vol. 1 · N.º 1", "status": "Recebendo artigos"},
]

LEARNING_RESOURCES = [
    {"id": 1, "type": "Interactivo", "topic": "Biologia Celular", "level": "Universitário", "title": "Explore a célula", "description": "Identifique organelos e relacione estruturas com as suas funções.", "icon": "◉"},
    {"id": 2, "type": "Laboratório Virtual", "topic": "Fisiologia", "level": "Secundário", "title": "Osmose em células", "description": "Teste concentrações e observe o movimento previsto da água.", "icon": "⌁", "url": "/laboratorio/osmose"},
    {"id": 3, "type": "Actividade", "topic": "Genética", "level": "Universitário", "title": "Heredogramas passo a passo", "description": "Pratique a identificação de padrões de herança em famílias.", "icon": "◇"},
    {"id": 4, "type": "Vídeo", "topic": "Microbiologia", "level": "Secundário", "title": "O mundo invisível dos microrganismos", "description": "Uma introdução visual à diversidade microbiana.", "icon": "▶"},
    {"id": 5, "type": "Dados", "topic": "Ecologia", "level": "Universitário", "title": "Diversidade de espécies", "description": "Conjunto demonstrativo para calcular riqueza e abundância.", "icon": "▥"},
    {"id": 6, "type": "Explicador", "topic": "Bioquímica", "level": "Universitário", "title": "Do DNA à proteína", "description": "Uma sequência guiada por replicação, transcrição e tradução.", "icon": "↝"},
]

@app.get("/")
def home():
    items = Article.public_query().order_by(Article.featured.desc(), Article.published_at.desc()).limit(6).all()
    return render_template("index.html", articles=items, journals=Journal.public_query().order_by(Journal.title).limit(3).all())

@app.get("/artigos")
def articles():
    category = request.args.get("categoria", "").strip().lower()
    query = request.args.get("q", "").strip().lower()
    results = Article.public_query()
    if category:
        results = results.join(Category).filter(db.func.lower(Category.name) == category)
    if query:
        like = f"%{query}%"
        results = results.join(Author).filter(or_(db.func.lower(Article.title).like(like), db.func.lower(Article.summary).like(like), db.func.lower(Article.body).like(like), db.func.lower(Author.name).like(like)))
    page = request.args.get("page", 1, type=int)
    pagination = results.order_by(Article.published_at.desc()).paginate(page=max(1, page), per_page=12, error_out=False)
    return render_template("articles.html", articles=pagination.items, pagination=pagination, query=request.args.get("q", ""), category=request.args.get("categoria", ""))

@app.get("/artigo/<int:article_id>")
def article(article_id):
    selected = Article.public_query().filter_by(id=article_id).first()
    if not selected:
        return render_template("404.html"), 404
    return redirect(url_for("article_by_slug", slug=selected.slug), code=301)

@app.get("/artigo/<slug>")
def article_by_slug(slug):
    selected = Article.public_query().filter_by(slug=slug).first()
    if not selected:
        return render_template("404.html"), 404
    related = Article.public_query().filter(Article.id != selected.id, Article.category_id == selected.category_id).order_by(Article.published_at.desc()).limit(3).all()
    if len(related) < 3:
        excluded = [selected.id] + [item.id for item in related]
        related += Article.public_query().filter(~Article.id.in_(excluded)).order_by(Article.published_at.desc()).limit(3 - len(related)).all()
    return render_template("article.html", article=selected, related=related)

@app.get("/sobre")
def about():
    return render_template("about.html")

@app.get("/autores")
def authors():
    return render_template("authors.html", authors=Author.query.filter_by(active=True).order_by(Author.name).all())

@app.get("/contacto")
def contact():
    return render_template("contact.html")

@app.get("/termos-e-condicoes")
def terms():
    return render_template("terms.html")

@app.get("/politica-de-privacidade")
def privacy():
    return render_template("privacy.html")

@app.get("/politica-editorial")
def editorial_policy():
    return render_template("editorial_policy.html")

@app.get("/politica-de-correcoes")
def corrections_policy():
    return render_template("corrections_policy.html")

@app.get("/acessibilidade")
def accessibility():
    return render_template("accessibility.html")

@app.get("/servicos")
def services():
    return render_template("services.html")

@app.get("/servicos/edicao-cientifica")
def scientific_editing():
    return render_template("scientific_editing.html")

@app.get("/revistas")
def journals():
    return render_template("journals.html", journals=Journal.public_query().order_by(Journal.title).all())

@app.get("/revistas/<slug>")
def journal_detail(slug):
    journal = Journal.public_query().filter_by(slug=slug).first()
    if not journal:
        return render_template("404.html"), 404
    return render_template("journal.html", journal=journal)

@app.get("/recursos")
def resources():
    return render_template("resources.html")

@app.get("/aprender")
def learn():
    resource_type = request.args.get("tipo", "").strip().lower()
    topic = request.args.get("tema", "").strip().lower()
    items = LEARNING_RESOURCES
    if resource_type:
        items = [item for item in items if item["type"].lower() == resource_type]
    if topic:
        items = [item for item in items if item["topic"].lower() == topic]
    return render_template("learn.html", resources=items, all_resources=LEARNING_RESOURCES)

@app.get("/laboratorio/osmose")
def osmosis_lab():
    return render_template("osmosis_lab.html")

@app.get("/api/recursos")
def api_resources():
    return jsonify(LEARNING_RESOURCES)

@app.get("/favoritos")
def favorites():
    return render_template("favorites.html")

@app.get("/api/artigos")
def api_articles():
    query = request.args.get("q", "").strip().lower()
    items = Article.public_query()
    if query:
        like = f"%{query}%"
        items = items.join(Category).join(Author).filter(or_(db.func.lower(Article.title).like(like), db.func.lower(Article.summary).like(like), db.func.lower(Category.name).like(like), db.func.lower(Author.name).like(like)))
    limit = min(max(request.args.get("limit", 50, type=int), 1), 100)
    offset = max(request.args.get("offset", 0, type=int), 0)
    return jsonify([{"id": a.id, "slug": a.slug, "category": a.category, "title": a.title, "summary": a.summary, "author": a.author, "date": a.date, "read_time": a.read_time, "image": a.image} for a in items.order_by(Article.published_at.desc()).offset(offset).limit(limit).all()])

@app.get("/feed.xml")
def feed():
    articles = Article.public_query().order_by(Article.published_at.desc()).all()
    items = "".join(f"<item><title>{escape(a.title)}</title><link>{SITE_URL}{url_for('article_by_slug', slug=a.slug)}</link><guid isPermaLink=\"true\">{SITE_URL}{url_for('article_by_slug', slug=a.slug)}</guid><pubDate>{format_datetime((a.published_at or a.created_at).replace(tzinfo=timezone.utc))}</pubDate><description>{escape(a.summary)}</description></item>" for a in articles)
    last_build = format_datetime(datetime.now(timezone.utc))
    xml = f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Sussurros do Saber</title><link>{SITE_URL}/</link><description>Ciência que se compreende</description><language>pt-MZ</language><lastBuildDate>{last_build}</lastBuildDate>{items}</channel></rss>'
    return Response(xml, mimetype="application/rss+xml")

@app.get("/sitemap.xml")
def sitemap():
    paths = [url_for("home"), url_for("articles"), url_for("resources"), url_for("learn"), url_for("osmosis_lab"), url_for("about"), url_for("authors"), url_for("contact"), url_for("terms"), url_for("privacy"), url_for("editorial_policy"), url_for("corrections_policy"), url_for("accessibility"), url_for("services"), url_for("scientific_editing"), url_for("journals")] + [url_for("article_by_slug", slug=a.slug) for a in Article.public_query().all()] + [url_for("journal_detail", slug=j.slug) for j in Journal.public_query().all()]
    article_updates = {url_for("article_by_slug", slug=a.slug): a.updated_at.strftime("%Y-%m-%d") for a in Article.public_query().all()}
    urls = "".join(f"<url><loc>{SITE_URL}{path}</loc>{f'<lastmod>{article_updates[path]}</lastmod>' if path in article_updates else ''}</url>" for path in paths)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>', mimetype="application/xml")

@app.get("/robots.txt")
def robots():
    return Response(f"User-agent: *\nAllow: /\nDisallow: /admin\nDisallow: /api/\nSitemap: {SITE_URL}/sitemap.xml\n", mimetype="text/plain")


@app.get("/healthz")
def healthcheck():
    db.session.execute(text("SELECT 1"))
    return jsonify({"ok": True})


def valid_email(value):
    return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value)) and len(value) <= 254

@app.post("/api/newsletter")
@limiter.limit("5 per hour")
def newsletter():
    email = (request.get_json(silent=True) or {}).get("email", "").strip().lower()
    if not valid_email(email):
        return jsonify({"ok": False, "message": "Introduza um endereço de e-mail válido."}), 400
    subscriber = Subscriber.query.filter_by(email=email).first()
    if subscriber:
        subscriber.active = True
    else:
        db.session.add(Subscriber(email=email))
    db.session.commit()
    return jsonify({"ok": True, "message": "Inscrição confirmada. Bem-vindo ao Sussurros do Saber!"})

@app.post("/api/assistente")
@limiter.limit("5 per minute; 20 per hour")
def assistant():
    message = (request.get_json(silent=True) or {}).get("message", "").strip()
    if not message:
        return jsonify({"ok": False, "answer": "Escreva uma pergunta para eu poder ajudar."}), 400
    if len(message) > 800:
        return jsonify({"ok": False, "answer": "Utilize até 800 caracteres por pergunta."}), 400

    try:
        headers = {}
        if os.getenv("ASSISTANT_SHARED_KEY"):
            headers["X-Assistant-Key"] = os.environ["ASSISTANT_SHARED_KEY"]
        worker_response = requests.post(
            os.getenv("ASSISTANT_WORKER_URL", "https://assistente-sussurros.geniospurificado.workers.dev"),
            json={"message": message},
            headers=headers,
            timeout=25,
        )
        worker_response.raise_for_status()
        result = worker_response.json()
        if not isinstance(result, dict) or not isinstance(result.get("answer"), str) or len(result.get("answer", "")) > 10000:
            raise ValueError("Resposta inválida do assistente")
        return jsonify(result), 200 if result.get("ok") else 502
    except (requests.RequestException, ValueError):
        return jsonify({
            "ok": False,
            "answer": "O assistente está temporariamente indisponível. Tente novamente dentro de alguns instantes.",
            "links": [],
        }), 502

@app.post("/api/contacto")
@limiter.limit("10 per hour")
def submit_contact():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    subject = data.get("subject", "").strip()
    message = data.get("message", "").strip()
    website = data.get("website", "").strip()
    if website:
        return jsonify({"ok": True, "message": "Mensagem recebida."})
    if not 2 <= len(name) <= 120 or not valid_email(email) or not 3 <= len(subject) <= 220 or not 10 <= len(message) <= 5000:
        return jsonify({"ok": False, "message": "Preencha correctamente todos os campos."}), 400
    db.session.add(ContactMessage(name=name, email=email, subject=subject, message=message))
    db.session.commit()
    return jsonify({"ok": True, "message": "Mensagem recebida. Obrigado por contactar o Sussurros do Saber."})


def ensure_legacy_columns():
    migrations = {
        "article": {"references": "TEXT DEFAULT '' NOT NULL", "keywords": "VARCHAR(500) DEFAULT ''", "doi": "VARCHAR(180) DEFAULT ''", "image_alt": "VARCHAR(300) DEFAULT ''", "image_public_id": "VARCHAR(255) DEFAULT ''"},
        "admin_user": {"role": "VARCHAR(20) DEFAULT 'editor' NOT NULL", "session_version": "INTEGER DEFAULT 1 NOT NULL", "password_changed_at": "TIMESTAMP"},
    }
    for table_name, additions in migrations.items():
        existing = {column["name"] for column in inspect(db.engine).get_columns(table_name)}
        for name, definition in additions.items():
            if name not in existing:
                db.session.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN "{name}" {definition}'))
    db.session.commit()


def seed_database():
    db.create_all()
    ensure_legacy_columns()
    if not Journal.query.first():
        for item in JOURNALS:
            db.session.add(Journal(title=item["title"], slug=item["slug"], abbreviation=item["abbr"], field=item["field"], description=item["description"], frequency=item["frequency"], current_issue=item["issue"], published=True, guidelines="Consulte a política editorial e contacte a editoria antes da submissão."))
        db.session.commit()
    if Article.query.first():
        return
    author_names = sorted({item["author"] for item in SEED_ARTICLES})
    authors = {}
    for name in author_names:
        author = Author(name=name, bio="Autor do Sussurros do Saber.")
        db.session.add(author)
        authors[name] = author
    category_names = sorted({item["category"] for item in SEED_ARTICLES})
    categories = {}
    for name in category_names:
        category = Category(name=name, slug=name.lower().replace("ú", "u").replace("ç", "c").replace("ã", "a").replace(" ", "-"))
        db.session.add(category)
        categories[name] = category
    db.session.flush()
    default_body = "A ciência começa com uma pergunta bem formulada. Este artigo apresenta o tema de forma acessível, sem perder o rigor nem a ligação às evidências.\n\nCombinando observação, experimentação e análise crítica, investigadores conseguem transformar fenómenos pouco visíveis em conhecimento verificável. O contexto local também importa: perguntas científicas relevantes surgem das necessidades das comunidades e dos ecossistemas onde a pesquisa acontece.\n\nCompreender ciência ajuda estudantes e cidadãos a tomar decisões informadas e aproxima a produção académica do público."
    month_numbers = {"Janeiro": 1, "Fevereiro": 2, "Março": 3, "Abril": 4, "Maio": 5, "Junho": 6, "Julho": 7, "Agosto": 8, "Setembro": 9, "Outubro": 10, "Novembro": 11, "Dezembro": 12}
    for item in SEED_ARTICLES:
        day, month_name, year = item["date"].split()
        published_at = datetime(int(year), month_numbers[month_name], int(day))
        db.session.add(Article(
            title=item["title"], slug=f"artigo-{item['id']}", summary=item["summary"], body=default_body,
            image=item["image"], status="published", read_minutes=int(item["read_time"].split()[0]),
            featured=item.get("featured", False), published_at=published_at, author_rel=authors[item["author"]], category_rel=categories[item["category"]],
        ))
    db.session.commit()


with app.app_context():
    seed_database()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
