from flask import Flask, Response, jsonify, render_template, request, url_for
from xml.sax.saxutils import escape
import requests
import os
from datetime import timedelta
import bleach
import markdown
from markupsafe import Markup
from sqlalchemy import inspect, or_, text
from werkzeug.middleware.proxy_fix import ProxyFix
from admin import admin_bp
from extensions import limiter
from models import Article, Author, Category, ContactMessage, Subscriber, db, utcnow

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
database_url = os.getenv("DATABASE_URL", "sqlite:///sussurros.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config.update(
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=os.getenv("SECRET_KEY", "local-development-only-change-me"),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("RENDER", "") == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=9 * 1024 * 1024,
)
db.init_app(app)
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
    return response


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
    {"title": "Cadernos de Biodiversidade", "abbr": "CBIO", "field": "Biologia e Ecologia", "description": "Estudos sobre biodiversidade, conservação, ecologia e recursos naturais, com atenção aos contextos africanos.", "frequency": "Semestral", "issue": "Vol. 1 · N.º 1", "status": "Recebendo artigos"},
    {"title": "Saúde & Comunidade", "abbr": "SACO", "field": "Saúde Pública", "description": "Investigação e práticas sobre saúde comunitária, nutrição, prevenção e determinantes sociais da saúde.", "frequency": "Semestral", "issue": "Vol. 1 · N.º 1", "status": "Em preparação"},
    {"title": "Educação Científica", "abbr": "EDCI", "field": "Ensino e Aprendizagem", "description": "Pesquisa e experiências sobre ensino de Ciências e Biologia, formação docente e inovação pedagógica.", "frequency": "Anual", "issue": "Vol. 1 · N.º 1", "status": "Recebendo artigos"},
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
    return render_template("index.html", articles=items, journals=JOURNALS)

@app.get("/artigos")
def articles():
    category = request.args.get("categoria", "").strip().lower()
    query = request.args.get("q", "").strip().lower()
    results = Article.public_query()
    if category:
        results = results.join(Category).filter(db.func.lower(Category.name) == category)
    if query:
        like = f"%{query}%"
        results = results.filter(or_(db.func.lower(Article.title).like(like), db.func.lower(Article.summary).like(like), db.func.lower(Article.body).like(like)))
    return render_template("articles.html", articles=results.order_by(Article.published_at.desc()).all(), query=request.args.get("q", ""))

@app.get("/artigo/<int:article_id>")
def article(article_id):
    selected = Article.public_query().filter_by(id=article_id).first()
    if not selected:
        return render_template("404.html"), 404
    related = Article.public_query().filter(Article.id != article_id).order_by(Article.published_at.desc()).limit(3).all()
    return render_template("article.html", article=selected, related=related)

@app.get("/sobre")
def about():
    return render_template("about.html")

@app.get("/autores")
def authors():
    return render_template("authors.html")

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
    return render_template("journals.html", journals=JOURNALS)

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
        items = items.join(Category).filter(or_(db.func.lower(Article.title).like(like), db.func.lower(Article.summary).like(like), db.func.lower(Category.name).like(like)))
    return jsonify([{"id": a.id, "category": a.category, "title": a.title, "summary": a.summary, "author": a.author, "date": a.date, "read_time": a.read_time, "image": a.image} for a in items.all()])

@app.get("/feed.xml")
def feed():
    articles = Article.public_query().order_by(Article.published_at.desc()).all()
    items = "".join(f"<item><title>{escape(a.title)}</title><link>{request.url_root.rstrip('/')}{url_for('article', article_id=a.id)}</link><description>{escape(a.summary)}</description></item>" for a in articles)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Sussurros do Saber</title><link>{request.url_root}</link><description>Ciência que se compreende</description>{items}</channel></rss>'
    return Response(xml, mimetype="application/rss+xml")

@app.get("/sitemap.xml")
def sitemap():
    paths = [url_for("home"), url_for("articles"), url_for("resources"), url_for("learn"), url_for("osmosis_lab"), url_for("about"), url_for("authors"), url_for("contact"), url_for("terms"), url_for("privacy"), url_for("editorial_policy"), url_for("corrections_policy"), url_for("accessibility"), url_for("services"), url_for("scientific_editing"), url_for("journals")] + [url_for("article", article_id=a.id) for a in Article.public_query().all()]
    urls = "".join(f"<url><loc>{request.url_root.rstrip('/')}{path}</loc></url>" for path in paths)
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>', mimetype="application/xml")

@app.get("/robots.txt")
def robots():
    return Response(f"User-agent: *\nAllow: /\nSitemap: {request.url_root}sitemap.xml\n", mimetype="text/plain")

@app.post("/api/newsletter")
@limiter.limit("5 per hour")
def newsletter():
    email = (request.get_json(silent=True) or {}).get("email", "").strip().lower()
    if "@" not in email:
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
    if len(name) < 2 or "@" not in email or len(subject) < 3 or len(message) < 10:
        return jsonify({"ok": False, "message": "Preencha correctamente todos os campos."}), 400
    db.session.add(ContactMessage(name=name, email=email, subject=subject, message=message))
    db.session.commit()
    return jsonify({"ok": True, "message": "Mensagem recebida. Obrigado por contactar o Sussurros do Saber."})


def ensure_article_columns():
    existing = {column["name"] for column in inspect(db.engine).get_columns("article")}
    additions = {"references": "TEXT DEFAULT '' NOT NULL", "keywords": "VARCHAR(500) DEFAULT ''", "doi": "VARCHAR(180) DEFAULT ''"}
    for name, definition in additions.items():
        if name not in existing:
            db.session.execute(text(f'ALTER TABLE article ADD COLUMN "{name}" {definition}'))
    db.session.commit()


def seed_database():
    db.create_all()
    ensure_article_columns()
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
    for item in SEED_ARTICLES:
        db.session.add(Article(
            title=item["title"], slug=f"artigo-{item['id']}", summary=item["summary"], body=default_body,
            image=item["image"], status="published", read_minutes=int(item["read_time"].split()[0]),
            featured=item.get("featured", False), published_at=utcnow(), author_rel=authors[item["author"]], category_rel=categories[item["category"]],
        ))
    db.session.commit()


with app.app_context():
    seed_database()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
