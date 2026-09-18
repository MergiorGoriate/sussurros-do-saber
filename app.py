from flask import Flask, Response, jsonify, redirect, render_template, request, url_for
from xml.sax.saxutils import escape
import requests
import gzip
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from html import escape as html_escape
from urllib.parse import parse_qs, quote, urlparse
import bleach
import markdown
import math
from markupsafe import Markup
from sqlalchemy import inspect, or_, text
from werkzeug.middleware.proxy_fix import ProxyFix
from admin import admin_bp, slugify
from extensions import limiter
from models import AdminUser, Article, Author, Category, ContactMessage, Journal, Subscriber, db, utcnow

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
    SESSION_COOKIE_SECURE=os.getenv("RENDER", "").lower() == "true" or os.getenv("SESSION_COOKIE_SECURE", "").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=9 * 1024 * 1024,
)
SITE_URL = os.getenv("SITE_URL", "https://sussurrosdosaber.com").rstrip("/")
db.init_app(app)
limiter.init_app(app)
app.register_blueprint(admin_bp)


IMAGE_DIRECTIVE = re.compile(r"!\[([^\]]*)\]\((https?://[^\s)]+)\)", re.I)
VIDEO_DIRECTIVE = re.compile(r"^\[video:\s*([^\]]*)\]\((https?://[^\s)]+)\)\s*$", re.I | re.M)
CHART_DIRECTIVE = re.compile(r"^\[chart:\s*(bar|line|pie)\|([^\]\n]{1,180})\|([^\]\n]{1,1200})\]\s*$", re.I | re.M)


def safe_video_embed(url, title):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    label = (title or "Vídeo incorporado").strip()[:180]
    embed_url = None
    if host in {"youtube.com", "m.youtube.com", "youtube-nocookie.com"}:
        video_id = parsed.path.split("/embed/", 1)[1].split("/", 1)[0] if "/embed/" in parsed.path else parse_qs(parsed.query).get("v", [""])[0]
        if re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id):
            embed_url = f"https://www.youtube-nocookie.com/embed/{video_id}"
    elif host == "youtu.be":
        video_id = parsed.path.strip("/").split("/", 1)[0]
        if re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id):
            embed_url = f"https://www.youtube-nocookie.com/embed/{video_id}"
    elif host in {"vimeo.com", "player.vimeo.com"}:
        match = re.search(r"(?:video/)?(\d{5,12})", parsed.path)
        if match:
            embed_url = f"https://player.vimeo.com/video/{match.group(1)}"

    safe_label = html_escape(label, quote=True)
    if embed_url:
        return (
            '<figure class="article-video"><div class="article-video-frame">'
            f'<iframe src="{embed_url}" title="{safe_label}" loading="lazy" '
            'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" '
            'referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe></div>'
            f'<figcaption>{safe_label}</figcaption></figure>'
        )
    if parsed.scheme in {"http", "https"} and parsed.path.lower().endswith((".mp4", ".webm", ".ogg")):
        safe_url = html_escape(url, quote=True)
        return (
            f'<figure class="article-video"><video controls preload="metadata" aria-label="{safe_label}">'
            f'<source src="{safe_url}">O navegador não suporta este vídeo.</video>'
            f'<figcaption>{safe_label}</figcaption></figure>'
        )
    return None


def safe_chart_embed(chart_type, title, raw_data):
    chart_type = chart_type.lower()
    title = (title or "Gráfico").strip()[:180]
    points = []
    for item in raw_data.split(";")[:12]:
        if "=" not in item:
            continue
        label, raw_value = item.rsplit("=", 1)
        label = label.strip()[:40]
        try:
            value = float(raw_value.strip().replace(",", "."))
        except ValueError:
            continue
        if label and math.isfinite(value) and value >= 0:
            points.append((label, value))
    if not points or max(value for _, value in points) <= 0:
        return None

    safe_title = html_escape(title, quote=True)
    colours = ["#087f72", "#e85d4a", "#2f6db0", "#d69e2e", "#805ad5", "#319795",
               "#c05621", "#4a5568", "#38a169", "#b83280", "#718096", "#dd6b20"]
    svg = [f'<svg viewBox="0 0 800 440" role="img" aria-label="{safe_title}">',
           f"<title>{safe_title}</title>", '<rect width="800" height="440" fill="#fff"/>']

    if chart_type in {"bar", "line"}:
        maximum = max(value for _, value in points)
        left, top, width, height = 80, 45, 680, 285
        svg.extend([
            f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + height}" class="chart-axis"/>',
            f'<line x1="{left}" y1="{top + height}" x2="{left + width}" y2="{top + height}" class="chart-axis"/>',
        ])
        for tick in range(5):
            value = maximum * tick / 4
            y = top + height - (height * tick / 4)
            svg.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + width}" y2="{y:.1f}" class="chart-grid"/>')
            svg.append(f'<text x="{left - 10}" y="{y + 5:.1f}" text-anchor="end" class="chart-value">{value:g}</text>')
        step = width / len(points)
        if chart_type == "bar":
            bar_width = min(58, step * .65)
            for index, (label, value) in enumerate(points):
                x = left + index * step + (step - bar_width) / 2
                bar_height = height * value / maximum
                y = top + height - bar_height
                safe_label = html_escape(label)
                svg.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" height="{bar_height:.1f}" rx="5" fill="{colours[index % len(colours)]}"/>')
                svg.append(f'<text x="{x + bar_width / 2:.1f}" y="{y - 8:.1f}" text-anchor="middle" class="chart-value">{value:g}</text>')
                svg.append(f'<text x="{x + bar_width / 2:.1f}" y="{top + height + 24}" text-anchor="middle" class="chart-label">{safe_label}</text>')
        else:
            coords = []
            for index, (label, value) in enumerate(points):
                x = left + (width / max(1, len(points) - 1)) * index
                y = top + height - height * value / maximum
                coords.append(f"{x:.1f},{y:.1f}")
                safe_label = html_escape(label)
                svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="{colours[index % len(colours)]}"/>')
                svg.append(f'<text x="{x:.1f}" y="{y - 12:.1f}" text-anchor="middle" class="chart-value">{value:g}</text>')
                svg.append(f'<text x="{x:.1f}" y="{top + height + 24}" text-anchor="middle" class="chart-label">{safe_label}</text>')
            svg.insert(-len(points) * 3, f'<polyline points="{" ".join(coords)}" class="chart-line"/>')
    else:
        total = sum(value for _, value in points)
        cx, cy, radius = 275, 220, 145
        start = -math.pi / 2
        if len(points) == 1:
            svg.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="{colours[0]}"/>')
        else:
            for index, (_, value) in enumerate(points):
                end = start + 2 * math.pi * value / total
                x1, y1 = cx + radius * math.cos(start), cy + radius * math.sin(start)
                x2, y2 = cx + radius * math.cos(end), cy + radius * math.sin(end)
                large = 1 if end - start > math.pi else 0
                svg.append(f'<path d="M {cx} {cy} L {x1:.2f} {y1:.2f} A {radius} {radius} 0 {large} 1 {x2:.2f} {y2:.2f} Z" fill="{colours[index % len(colours)]}"/>')
                start = end
        for index, (label, value) in enumerate(points):
            safe_label = html_escape(label)
            percent = value / total * 100
            y = 75 + index * 27
            svg.append(f'<rect x="500" y="{y - 13}" width="16" height="16" rx="3" fill="{colours[index % len(colours)]}"/>')
            svg.append(f'<text x="526" y="{y}" class="chart-legend">{safe_label}: {value:g} ({percent:.1f}%)</text>')

    svg.append("</svg>")
    return (
        '<figure class="article-chart">'
        + "".join(svg)
        + f"<figcaption>{safe_title}</figcaption></figure>"
    )


@app.template_filter("markdown")
def render_markdown(value):
    embeds = {}

    def store_embed(prefix, embed):
        token = f"{prefix}EMBEDTOKEN{len(embeds)}"
        embeds[token] = embed
        return token

    def image_placeholder(match):
        parsed = urlparse(match.group(2))
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return match.group(0)
        safe_url = html_escape(match.group(2), quote=True)
        safe_alt = html_escape((match.group(1) or "Imagem do artigo").strip()[:180], quote=True)
        image = (
            '<figure class="article-inline-image">'
            f'<img src="{safe_url}" alt="{safe_alt}" loading="lazy" decoding="async">'
            '</figure>'
        )
        return store_embed("IMAGE", image)

    def video_placeholder(match):
        embed = safe_video_embed(match.group(2), match.group(1))
        return store_embed("VIDEO", embed) if embed else match.group(0)

    def chart_placeholder(match):
        embed = safe_chart_embed(match.group(1), match.group(2), match.group(3))
        return store_embed("CHART", embed) if embed else match.group(0)

    prepared = IMAGE_DIRECTIVE.sub(image_placeholder, value or "")
    prepared = VIDEO_DIRECTIVE.sub(video_placeholder, prepared)
    prepared = CHART_DIRECTIVE.sub(chart_placeholder, prepared)
    rendered = markdown.markdown(prepared, extensions=["extra", "sane_lists"])
    allowed = set(bleach.sanitizer.ALLOWED_TAGS).union({"p", "h2", "h3", "h4", "blockquote", "pre", "code", "ul", "ol", "li", "hr", "table", "thead", "tbody", "tr", "th", "td", "img"})
    cleaned = bleach.clean(
        rendered,
        tags=allowed,
        attributes={"a": ["href", "title", "rel"], "img": ["src", "alt", "title", "loading", "decoding"]},
        protocols=["http", "https", "mailto"],
        strip=True,
    )
    for token, embed in embeds.items():
        cleaned = cleaned.replace(f"<p>{token}</p>", embed).replace(token, embed)
    return Markup(cleaned)


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
        "frame-src https://challenges.cloudflare.com https://www.youtube-nocookie.com https://player.vimeo.com; media-src https:; connect-src 'self' https://challenges.cloudflare.com; upgrade-insecure-requests",
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

    compressible = {
        "text/html", "text/css", "text/plain", "text/xml",
        "application/json", "application/javascript", "application/xml",
    }
    accepts_gzip = "gzip" in request.headers.get("Accept-Encoding", "").lower()
    if (
        accepts_gzip
        and response.status_code == 200
        and not response.direct_passthrough
        and not response.headers.get("Content-Encoding")
        and response.mimetype in compressible
    ):
        payload = response.get_data()
        if len(payload) >= 1024:
            response.set_data(gzip.compress(payload, compresslevel=5))
            response.headers["Content-Encoding"] = "gzip"
            response.headers["Content-Length"] = len(response.get_data())
            response.vary.add("Accept-Encoding")
    return response


@app.context_processor
def site_context():
    return {
        "site_url": SITE_URL,
        "social_links": {
            "facebook": os.getenv("SOCIAL_FACEBOOK_URL", "https://www.facebook.com/"),
            "instagram": os.getenv("SOCIAL_INSTAGRAM_URL", "https://www.instagram.com/"),
            "youtube": os.getenv("SOCIAL_YOUTUBE_URL", "https://www.youtube.com/"),
            "linkedin": os.getenv("SOCIAL_LINKEDIN_URL", "https://www.linkedin.com/"),
            "x": os.getenv("SOCIAL_X_URL", "https://x.com/"),
            "whatsapp": os.getenv("SOCIAL_WHATSAPP_URL", "https://www.whatsapp.com/"),
        },
    }


@app.template_filter("image_variant")
def responsive_image_url(url, width=1200):
    value = (url or "").strip()
    try:
        requested_width = max(160, min(2000, int(width)))
    except (TypeError, ValueError):
        requested_width = 1200
    if "res.cloudinary.com/" in value and "/upload/" in value:
        transformation = f"f_auto,q_auto:eco,w_{requested_width},c_limit"
        return value.replace("/upload/", f"/upload/{transformation}/", 1)
    return value

@app.template_filter("absolute_url")
def absolute_url(value):
    address = (value or "").strip()
    if address.startswith(("http://", "https://")):
        return address
    if address.startswith("//"):
        return "https:" + address
    return SITE_URL + "/" + address.lstrip("/")


@app.template_filter("social_image")
def social_image_url(url):
    value = absolute_url((url or "").strip()) if url else ""
    if not value:
        return SITE_URL + "/static/img/logo-sussurros-horizontal.png"

    transformation = "f_jpg,q_auto:good,w_1200,h_630,c_fill,g_auto,fl_force_strip"
    if "res.cloudinary.com/" in value and "/upload/" in value:
        return value.replace("/upload/", f"/upload/{transformation}/", 1)

    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
    if not cloud_name:
        cloudinary_url = os.getenv("CLOUDINARY_URL", "").strip()
        cloud_name = urlparse(cloudinary_url).hostname or ""

    if cloud_name and value.startswith(("http://", "https://")):
        encoded_source = quote(value, safe="")
        return (
            f"https://res.cloudinary.com/{cloud_name}/image/fetch/"
            f"{transformation}/{encoded_source}"
        )
    return value



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

DEFAULT_JOURNALS = [
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
    return render_template("index.html", articles=items, journals=Journal.query.filter_by(published=True).order_by(Journal.updated_at.desc()).limit(3).all())

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
    return render_template("articles.html", articles=results.order_by(Article.published_at.desc()).all(), query=request.args.get("q", ""))

@app.get("/artigo/<slug>")
def article(slug):
    selected = Article.public_query().filter_by(slug=slug).first()
    if not selected:
        legacy_match = re.fullmatch(r"artigo-(\d+)", slug)
        legacy = Article.public_query().filter_by(id=int(legacy_match.group(1))).first() if legacy_match else None
        if legacy:
            return redirect(url_for("article", slug=legacy.slug), code=301)
        return render_template("404.html"), 404
    related = Article.public_query().filter(Article.id != selected.id).order_by(Article.published_at.desc()).limit(3).all()
    return render_template("article.html", article=selected, related=related)


@app.get("/artigo/<int:article_id>")
def article_legacy(article_id):
    selected = Article.public_query().filter_by(id=article_id).first()
    if not selected:
        return render_template("404.html"), 404
    return redirect(url_for("article", slug=selected.slug), code=301)

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
    return render_template(
        "journals.html",
        journals=Journal.query.filter_by(published=True).order_by(Journal.title).all(),
    )


@app.get("/revistas/<slug>")
def journal_detail(slug):
    journal = Journal.query.filter_by(slug=slug, published=True).first()
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
    return jsonify([{"id": a.id, "slug": a.slug, "category": a.category, "title": a.title, "summary": a.summary, "author": a.author, "date": a.date, "read_time": a.read_time, "image": a.image} for a in items.all()])

@app.get("/feed.xml")
def feed():
    articles = Article.public_query().order_by(Article.published_at.desc()).all()
    items = "".join(f"<item><title>{escape(a.title)}</title><link>{SITE_URL}{url_for('article', slug=a.slug)}</link><guid isPermaLink=\"true\">{SITE_URL}{url_for('article', slug=a.slug)}</guid><pubDate>{format_datetime((a.published_at or a.created_at).replace(tzinfo=timezone.utc))}</pubDate><description>{escape(a.summary)}</description></item>" for a in articles)
    last_build = format_datetime(datetime.now(timezone.utc))
    xml = f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Sussurros do Saber</title><link>{SITE_URL}/</link><description>Ciência que se compreende</description><language>pt-MZ</language><lastBuildDate>{last_build}</lastBuildDate>{items}</channel></rss>'
    return Response(xml, mimetype="application/rss+xml")

@app.get("/sitemap.xml")
def sitemap():
    paths = [url_for("home"), url_for("articles"), url_for("resources"), url_for("learn"), url_for("osmosis_lab"), url_for("about"), url_for("authors"), url_for("contact"), url_for("terms"), url_for("privacy"), url_for("editorial_policy"), url_for("corrections_policy"), url_for("accessibility"), url_for("services"), url_for("scientific_editing"), url_for("journals")] + [url_for("journal_detail", slug=j.slug) for j in Journal.query.filter_by(published=True).all()] + [url_for("article", slug=a.slug) for a in Article.public_query().all()]
    article_updates = {url_for("article", slug=a.slug): a.updated_at.strftime("%Y-%m-%d") for a in Article.public_query().all()}
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


def ensure_admin_columns():
    inspector = inspect(db.engine)
    if "admin_user" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("admin_user")}
    if "is_superadmin" not in existing:
        db.session.execute(text(
            'ALTER TABLE admin_user ADD COLUMN is_superadmin BOOLEAN DEFAULT FALSE NOT NULL'
        ))
        db.session.commit()

    administrators = AdminUser.query.order_by(AdminUser.created_at, AdminUser.id).all()
    configured_primary = bool(os.getenv("ADMIN_USERNAME"))
    if configured_primary:
        changed = False
        for administrator in administrators:
            if administrator.is_superadmin:
                administrator.is_superadmin = False
                changed = True
        if changed:
            db.session.commit()
        return

    if administrators:
        active = [administrator for administrator in administrators if administrator.active]
        primary = next(
            (administrator for administrator in administrators if administrator.is_superadmin and administrator.active),
            active[0] if active else administrators[0],
        )
        changed = False
        for administrator in administrators:
            should_be_primary = administrator.id == primary.id
            if administrator.is_superadmin != should_be_primary:
                administrator.is_superadmin = should_be_primary
                changed = True
        if changed:
            db.session.commit()


def ensure_author_columns():
    inspector = inspect(db.engine)
    if "author" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("author")}
    if "photo" not in existing:
        db.session.execute(text(
            'ALTER TABLE author ADD COLUMN photo VARCHAR(600) DEFAULT \'\''
        ))
        db.session.commit()



def ensure_journal_columns():
    inspector = inspect(db.engine)
    if "journal" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("journal")}
    additions = {
        "abbreviation": "VARCHAR(30) DEFAULT ''",
        "field": "VARCHAR(140) DEFAULT '' NOT NULL",
        "description": "TEXT DEFAULT '' NOT NULL",
        "issn": "VARCHAR(9) DEFAULT ''",
        "frequency": "VARCHAR(80) DEFAULT ''",
        "current_issue": "VARCHAR(120) DEFAULT ''",
        "guidelines": "TEXT DEFAULT ''",
        "cover_image": "VARCHAR(600) DEFAULT ''",
        "cover_alt": "VARCHAR(300) DEFAULT ''",
        "published": "BOOLEAN DEFAULT TRUE NOT NULL",
        "created_at": "TIMESTAMP",
        "updated_at": "TIMESTAMP",
    }
    changed = False
    for name, definition in additions.items():
        if name not in existing:
            db.session.execute(text(
                f'ALTER TABLE journal ADD COLUMN "{name}" {definition}'
            ))
            changed = True
    if changed:
        db.session.commit()


def ensure_article_columns():
    existing = {column["name"] for column in inspect(db.engine).get_columns("article")}
    additions = {"references": "TEXT DEFAULT '' NOT NULL", "keywords": "VARCHAR(500) DEFAULT ''", "doi": "VARCHAR(180) DEFAULT ''"}
    for name, definition in additions.items():
        if name not in existing:
            db.session.execute(text(f'ALTER TABLE article ADD COLUMN "{name}" {definition}'))
    db.session.commit()


def ensure_article_slugs():
    articles = Article.query.order_by(Article.id).all()
    fixed_slugs = {
        article.slug for article in articles
        if article.slug and not re.fullmatch(r"(?:artigo-)?\d+", article.slug)
    }
    changed = False
    for article in articles:
        if article.slug and not re.fullmatch(r"(?:artigo-)?\d+", article.slug):
            continue
        base = slugify(article.title) or f"artigo-{article.id}"
        candidate, number = base, 2
        while candidate in fixed_slugs:
            candidate, number = f"{base}-{number}", number + 1
        article.slug = candidate
        fixed_slugs.add(candidate)
        changed = True
    if changed:
        db.session.commit()


def seed_database():
    db.create_all()
    ensure_admin_columns()
    ensure_author_columns()
    ensure_journal_columns()
    ensure_article_columns()
    if not Journal.query.first():
        default_guidelines = (
            "Aceitamos manuscritos originais, revisões e relatos fundamentados. "
            "As submissões devem respeitar princípios de ética, transparência, "
            "atribuição de fontes e revisão editorial."
        )
        for item in DEFAULT_JOURNALS:
            db.session.add(Journal(
                title=item["title"],
                slug=item["slug"],
                abbreviation=item["abbr"],
                field=item["field"],
                description=item["description"],
                frequency=item["frequency"],
                current_issue=item["issue"],
                guidelines=default_guidelines,
                published=True,
            ))
        db.session.commit()
    if Article.query.first():
        ensure_article_slugs()
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
            title=item["title"], slug=slugify(item["title"]), summary=item["summary"], body=default_body,
            image=item["image"], status="published", read_minutes=int(item["read_time"].split()[0]),
            featured=item.get("featured", False), published_at=published_at, author_rel=authors[item["author"]], category_rel=categories[item["category"]],
        ))
    db.session.commit()


with app.app_context():
    seed_database()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
