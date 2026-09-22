from flask import Flask, Response, g, jsonify, redirect, render_template, request, session, url_for
from xml.sax.saxutils import escape
import requests
import gzip
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from html import escape as html_escape, unescape as html_unescape
from urllib.parse import parse_qs, quote, urlparse
import bleach
import markdown
import math
from markupsafe import Markup
from sqlalchemy import inspect, or_, text
from werkzeug.middleware.proxy_fix import ProxyFix
from admin import admin_bp, slugify
from extensions import limiter
from models import AdminUser, Article, Author, Category, Comment, ContactMessage, Journal, Subscriber, db, utcnow

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

IS_PRODUCTION = (
    os.getenv("RENDER", "").lower() == "true"
    or os.getenv("FLASK_ENV", "").lower() == "production"
)
DEVELOPMENT_SECRET_KEY = "local-development-only-change-me"
secret_key = os.getenv("SECRET_KEY", "").strip()
if IS_PRODUCTION and (not secret_key or secret_key == DEVELOPMENT_SECRET_KEY):
    raise RuntimeError("SECRET_KEY forte e exclusiva é obrigatória em produção.")
if not secret_key:
    secret_key = DEVELOPMENT_SECRET_KEY

database_url = os.getenv("DATABASE_URL", "sqlite:///sussurros.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config.update(
    SQLALCHEMY_DATABASE_URI=database_url,
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SECRET_KEY=secret_key,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("RENDER", "").lower() == "true" or os.getenv("SESSION_COOKIE_SECURE", "").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
    SESSION_REFRESH_EACH_REQUEST=False,
    MAX_CONTENT_LENGTH=9 * 1024 * 1024,
)
CANONICAL_ORIGIN = "https://www.sussurrosdosaber.com"
_configured_site_url = os.getenv("SITE_URL", CANONICAL_ORIGIN).rstrip("/")
_configured_host = (urlparse(_configured_site_url).hostname or "").lower()
# A origem pública oficial usa www. Normalize também configurações antigas do Render
# para impedir que canonical, Open Graph, sitemap e dados estruturados divirjam.
SITE_URL = CANONICAL_ORIGIN if _configured_host == "sussurrosdosaber.com" else _configured_site_url

db.init_app(app)
limiter.init_app(app)
app.register_blueprint(admin_bp)


@app.before_request
def assign_csp_nonce():
    """Cria um nonce imprevisível e exclusivo para cada resposta."""
    g.csp_nonce = secrets.token_urlsafe(24)


@app.before_request
def redirect_bare_domain_to_www():
    """Consolida sinais de indexação e ligações no único host canónico."""
    request_host = request.host.split(":", 1)[0].lower()
    if request_host == "sussurrosdosaber.com":
        target = CANONICAL_ORIGIN + request.full_path
        return redirect(target.rstrip("?"), code=308)
    return None


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
        source_url = match.group(2)
        safe_url = html_escape(responsive_image_url(source_url, 1200), quote=True)
        safe_small = html_escape(responsive_image_url(source_url, 480), quote=True)
        safe_medium = html_escape(responsive_image_url(source_url, 768), quote=True)
        safe_alt = html_escape((match.group(1) or "Imagem do artigo").strip()[:180], quote=True)
        image = (
            '<figure class="article-inline-image">'
            f'<img src="{safe_url}" srcset="{safe_small} 480w, {safe_medium} 768w, {safe_url} 1200w" '
            f'sizes="(max-width: 760px) 100vw, 760px" alt="{safe_alt}" loading="lazy" decoding="async">'
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
        attributes={"a": ["href", "title", "rel"], "img": ["src", "srcset", "sizes", "alt", "title", "loading", "decoding", "width", "height"]},
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
    response.headers.setdefault("Content-Language", "pt-MZ")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'self'; "
        "object-src 'none'; img-src 'self' data: https:; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com; "
        f"script-src 'nonce-{getattr(g, 'csp_nonce', '')}' 'strict-dynamic' 'self' https:; "
        "script-src-attr 'none'; "
        "frame-src https://challenges.cloudflare.com https://www.youtube-nocookie.com https://player.vimeo.com; media-src https:; connect-src 'self' https://challenges.cloudflare.com https://*.google-analytics.com https://*.analytics.google.com https://*.googletagmanager.com; upgrade-insecure-requests",
    )
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        # Páginas de artigos contêm um token CSRF individual do formulário de
        # comentários e nunca podem ser guardadas por caches partilhadas.
        private_response = (
            request.method != "GET"
            or request.path.startswith(("/admin", "/api/", "/artigo/"))
            or response.status_code >= 400
        )
        if private_response:
            response.headers["Cache-Control"] = "no-store"
        elif not response.headers.get("Cache-Control") or response.headers["Cache-Control"] == "no-store":
            response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    if request.path.startswith("/admin") or response.status_code >= 400:
        response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
    elif request.path == "/favoritos" or (request.path == "/artigos" and request.args):
        response.headers.setdefault("X-Robots-Tag", "noindex, follow")

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


def google_site_verification_token():
    default_token = "MBbrCatBKLtKz2UmAJQsYlJ95ZEpNQ3CJvRMTo6aGwE"
    raw_value = os.getenv("GOOGLE_SITE_VERIFICATION", default_token).strip()
    content_match = re.search(
        r"""content\s*=\s*["']([^"']+)["']""",
        raw_value,
        re.I,
    )
    if content_match:
        raw_value = content_match.group(1)
    token = raw_value.strip().strip(chr(34) + chr(39))
    return token if re.fullmatch(r"[A-Za-z0-9_-]{20,}", token) else default_token


@app.context_processor
def site_context():
    return {
        "site_url": SITE_URL,
        "csp_nonce": getattr(g, "csp_nonce", ""),
        "google_site_verification": google_site_verification_token(),
        "gtm_container_id": os.getenv("GTM_CONTAINER_ID", "GTM-PQSZGPQQ").strip(),
        "social_links": {
            "facebook": os.getenv("SOCIAL_FACEBOOK_URL", "https://web.facebook.com/profile.php?id=61584597102517"),
            "instagram": os.getenv("SOCIAL_INSTAGRAM_URL", "https://www.instagram.com/sussurrodosaber?stkn=djl2d2s5cmJnZzE5"),
            "youtube": os.getenv("SOCIAL_YOUTUBE_URL", "https://www.youtube.com/channel/UCMxbh7jSRUxxX48JSWszc8g"),
            "linkedin": os.getenv("SOCIAL_LINKEDIN_URL", "https://www.linkedin.com/"),
            "x": os.getenv("SOCIAL_X_URL", "https://x.com/sussurrodosaber"),
            "whatsapp": os.getenv("SOCIAL_WHATSAPP_URL", "https://wa.me/258852130099"),
        },
    }


def cloudinary_cloud_name():
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
    if cloud_name:
        return cloud_name
    return urlparse(os.getenv("CLOUDINARY_URL", "").strip()).hostname or ""


@app.template_filter("safe_image_url")
def safe_image_url(url):
    """Normaliza URLs de imagem sem as encaminhar por proxies externos."""
    value = html_unescape(str(url or "")).strip().strip(chr(34) + chr(39))
    if value.startswith("//"):
        value = "https:" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return value


@app.template_filter("image_variant")
def responsive_image_url(url, width=1200):
    """Otimiza apenas imagens alojadas no Cloudinary.

    Imagens externas permanecem no endereço original. Encaminhá-las pelo
    image/fetch do Cloudinary fazia capas e imagens do corpo quebrarem quando
    o fetch remoto estava desativado ou a origem recusava o crawler.
    """
    value = safe_image_url(url)
    if not value:
        return ""
    try:
        requested_width = max(160, min(2000, int(width)))
    except (TypeError, ValueError):
        requested_width = 1200
    transformation = f"f_auto,q_auto:eco,w_{requested_width},c_limit"
    if "res.cloudinary.com/" in value and "/upload/" in value:
        return value.replace("/upload/", f"/upload/{transformation}/", 1)
    return value


@app.template_filter("absolute_url")
def absolute_url(value):
    address = html_unescape(str(value or "")).strip().strip(chr(34) + chr(39))
    if address.startswith(("http://", "https://")):
        return address
    if address.startswith("//"):
        return "https:" + address
    return SITE_URL + "/" + address.lstrip("/")


@app.template_filter("social_image")
def social_image_url(url):
    value = safe_image_url(url)
    if not value:
        return SITE_URL + "/static/img/logo-sussurros-horizontal.png"

    transformation = "f_jpg,q_auto:good,w_1200,h_630,c_fill,g_auto,fl_force_strip"
    if "res.cloudinary.com/" in value and "/upload/" in value:
        return value.replace("/upload/", f"/upload/{transformation}/", 1)

    # O endereço original é mais fiável do que Cloudinary image/fetch:
    # muitas origens bloqueiam o fetch e algumas contas não o têm ativado.
    return value



@app.errorhandler(500)
def internal_server_error(error):
    db.session.rollback()
    return render_template("500.html"), 500


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
    items = Article.public_card_query().order_by(Article.featured.desc(), Article.published_at.desc()).limit(10).all()
    return render_template("index.html", articles=items, journals=Journal.query.filter_by(published=True).order_by(Journal.updated_at.desc()).limit(3).all())

@app.get("/artigos")
def articles():
    category = request.args.get("categoria", "").strip().lower()
    query = request.args.get("q", "").strip().lower()
    results = Article.public_card_query()
    if category:
        results = results.join(Category).filter(db.func.lower(Category.name) == category)
    if query:
        like = f"%{query}%"
        results = results.join(Author).filter(or_(db.func.lower(Article.title).like(like), db.func.lower(Article.summary).like(like), db.func.lower(Article.body).like(like), db.func.lower(Author.name).like(like)))
    page = max(1, request.args.get("page", 1, type=int))
    pagination = results.order_by(Article.published_at.desc()).paginate(page=page, per_page=12, error_out=False)
    return render_template(
        "articles.html",
        articles=pagination.items,
        pagination=pagination,
        query=request.args.get("q", ""),
    )

def comment_csrf_token():
    token = session.get("comment_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["comment_csrf_token"] = token
    return token


@app.get("/artigo/<slug>")
def article(slug):
    selected = Article.public_query().filter_by(slug=slug).first()
    if not selected:
        legacy_match = re.fullmatch(r"artigo-(\d+)", slug)
        legacy = Article.public_query().filter_by(id=int(legacy_match.group(1))).first() if legacy_match else None
        if legacy:
            return redirect(url_for("article", slug=legacy.slug), code=301)
        return render_template("404.html"), 404
    related = Article.public_card_query().filter(Article.id != selected.id).order_by(Article.published_at.desc()).limit(3).all()
    comments = Comment.query.filter_by(article_id=selected.id, approved=True).order_by(Comment.created_at.desc()).limit(100).all()
    return render_template(
        "article.html",
        article=selected,
        related=related,
        comments=comments,
        comment_csrf_token=comment_csrf_token(),
    )


@app.post("/artigo/<slug>/comentarios")
@limiter.limit("5 per hour")
def submit_comment(slug):
    selected = Article.public_query().filter_by(slug=slug).first()
    if not selected:
        return render_template("404.html"), 404

    success_url = url_for("article", slug=selected.slug, comentario="recebido") + "#comentarios"
    if request.form.get("website", "").strip():
        return redirect(success_url, code=303)

    sent_token = request.form.get("csrf_token", "")
    expected_token = session.get("comment_csrf_token", "")
    if not expected_token or not secrets.compare_digest(sent_token, expected_token):
        return redirect(url_for("article", slug=selected.slug, comentario="invalido") + "#comentarios", code=303)

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    body = request.form.get("body", "").strip()
    if not 2 <= len(name) <= 80 or not valid_email(email) or not 10 <= len(body) <= 2000:
        return redirect(url_for("article", slug=selected.slug, comentario="invalido") + "#comentarios", code=303)

    db.session.add(Comment(article_id=selected.id, name=name, email=email, body=body))
    db.session.commit()
    session["comment_csrf_token"] = secrets.token_urlsafe(32)
    return redirect(success_url, code=303)


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
    editorial_team = (
        Author.query.filter_by(active=True)
        .order_by(Author.display_order.asc(), Author.name.asc())
        .all()
    )
    return render_template("authors.html", authors=editorial_team)


def profile_lines(value):
    return [line.strip().lstrip("-• ").strip() for line in (value or "").splitlines() if line.strip()]


@app.get("/autor/<slug>")
def author_detail(slug):
    author = Author.query.filter_by(slug=slug, active=True).first()
    if not author:
        return render_template("404.html"), 404
    page = max(request.args.get("pagina", 1, type=int) or 1, 1)
    pagination = (
        Article.public_card_query()
        .filter(Article.author_id == author.id)
        .order_by(Article.published_at.desc(), Article.id.desc())
        .paginate(page=page, per_page=9, error_out=False)
    )
    return render_template(
        "author.html",
        author=author,
        articles=pagination.items,
        pagination=pagination,
        interests=profile_lines(author.interests),
        projects=profile_lines(author.projects),
        publications=profile_lines(author.publications),
        academic_background=profile_lines(author.academic_background),
        editorial_experience=profile_lines(author.editorial_experience),
    )


@app.get("/autor/<int:author_id>")
def legacy_author(author_id):
    author = db.session.get(Author, author_id)
    if not author or not author.active:
        return render_template("404.html"), 404
    return redirect(url_for("author_detail", slug=author.slug), code=301)


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
    response = jsonify(LEARNING_RESOURCES)
    response.headers["Cache-Control"] = "public, max-age=600, stale-while-revalidate=3600"
    return response

@app.get("/favoritos")
def favorites():
    return render_template("favorites.html")

@app.get("/api/artigos")
def api_articles():
    query = request.args.get("q", "").strip().lower()[:120]
    raw_ids = request.args.get("ids", "")[:512]
    requested_ids = list(dict.fromkeys(
        int(value) for value in raw_ids.split(",")
        if value.strip().isdigit()
    ))[:50]
    limit = max(1, min(50, request.args.get("limit", 24, type=int)))

    items = Article.public_card_query()
    if requested_ids:
        items = items.filter(Article.id.in_(requested_ids))
        limit = min(50, len(requested_ids))
    if query:
        like = f"%{query}%"
        items = items.join(Category).join(Author).filter(or_(
            db.func.lower(Article.title).like(like),
            db.func.lower(Article.summary).like(like),
            db.func.lower(Category.name).like(like),
            db.func.lower(Author.name).like(like),
        ))
    articles = items.order_by(Article.published_at.desc()).limit(limit).all()
    response = jsonify([
        {
            "id": article.id,
            "slug": article.slug,
            "category": article.category,
            "title": article.title,
            "summary": article.summary,
            "author": article.author,
            "date": article.date,
            "read_time": article.read_time,
            "image": article.image,
        }
        for article in articles
    ])
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return response

@app.get("/feed.xml")
def feed():
    articles = Article.public_card_query().order_by(Article.published_at.desc()).all()
    items = "".join(f"<item><title>{escape(a.title)}</title><link>{SITE_URL}{url_for('article', slug=a.slug)}</link><guid isPermaLink=\"true\">{SITE_URL}{url_for('article', slug=a.slug)}</guid><pubDate>{format_datetime((a.published_at or a.created_at).replace(tzinfo=timezone.utc))}</pubDate><description>{escape(a.summary)}</description></item>" for a in articles)
    last_build = format_datetime(datetime.now(timezone.utc))
    xml = f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Sussurros do Saber</title><link>{SITE_URL}/</link><description>Ciência que se compreende</description><language>pt-MZ</language><lastBuildDate>{last_build}</lastBuildDate>{items}</channel></rss>'
    return Response(xml, mimetype="application/rss+xml")

@app.get("/sitemap.xml")
def sitemap():
    public_articles = Article.public_card_query().order_by(Article.updated_at.desc()).all()
    public_journals = Journal.query.filter_by(published=True).order_by(Journal.updated_at.desc()).all()
    public_authors = Author.query.filter_by(active=True).order_by(Author.name).all()
    static_paths = [
        url_for("home"), url_for("articles"), url_for("resources"), url_for("learn"),
        url_for("osmosis_lab"), url_for("about"), url_for("authors"), url_for("contact"),
        url_for("terms"), url_for("privacy"), url_for("editorial_policy"),
        url_for("corrections_policy"), url_for("accessibility"), url_for("services"),
        url_for("scientific_editing"), url_for("journals"),
    ]
    static_urls = "".join(
        f"<url><loc>{escape(SITE_URL + path)}</loc></url>"
        for path in static_paths
    )
    journal_urls = "".join(
        f"<url><loc>{escape(SITE_URL + url_for('journal_detail', slug=journal.slug))}</loc>"
        f"<lastmod>{journal.updated_at.strftime('%Y-%m-%d')}</lastmod></url>"
        for journal in public_journals
    )
    author_urls = "".join(
        f"<url><loc>{escape(SITE_URL + url_for('author_detail', slug=author.slug))}</loc></url>"
        for author in public_authors if author.slug
    )
    article_entries = []
    for article in public_articles:
        article_url = escape(SITE_URL + url_for("article", slug=article.slug))
        cover_url = safe_image_url(article.image)
        image_xml = ""
        if cover_url:
            image_xml = (
                f"<image:image><image:loc>{escape(cover_url)}</image:loc>"
                f"<image:title>{escape(article.title)}</image:title></image:image>"
            )
        article_entries.append(
            f"<url><loc>{article_url}</loc>"
            f"<lastmod>{article.updated_at.strftime('%Y-%m-%d')}</lastmod>"
            f"{image_xml}</url>"
        )
    response = Response(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
        'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">'
        + static_urls + journal_urls + author_urls + "".join(article_entries) + "</urlset>",
        mimetype="application/xml",
    )
    response.headers["Cache-Control"] = "public, max-age=3600"
    return response

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
    additions = {
        "is_superadmin": "BOOLEAN DEFAULT FALSE NOT NULL",
        "two_factor_enabled": "BOOLEAN DEFAULT FALSE NOT NULL",
        "totp_secret": "VARCHAR(64)",
        "recovery_code_hashes": "TEXT DEFAULT '' NOT NULL",
    }
    changed = False
    for name, definition in additions.items():
        if name not in existing:
            db.session.execute(text(
                f'ALTER TABLE admin_user ADD COLUMN "{name}" {definition}'
            ))
            changed = True
    if changed:
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
    additions = {
        "slug": "VARCHAR(160)",
        "role": "VARCHAR(140) DEFAULT ''",
        "headline": "VARCHAR(220) DEFAULT ''",
        "academic_background": "TEXT DEFAULT ''",
        "institution": "VARCHAR(220) DEFAULT ''",
        "bio": "TEXT DEFAULT ''",
        "interests": "TEXT DEFAULT ''",
        "projects": "TEXT DEFAULT ''",
        "orcid": "VARCHAR(19) DEFAULT ''",
        "google_scholar": "VARCHAR(600) DEFAULT ''",
        "researchgate": "VARCHAR(600) DEFAULT ''",
        "publications": "TEXT DEFAULT ''",
        "editorial_experience": "TEXT DEFAULT ''",
        "photo": "VARCHAR(600) DEFAULT ''",
        "display_order": "INTEGER DEFAULT 100",
    }
    changed = False
    for column, definition in additions.items():
        if column not in existing:
            db.session.execute(text(f'ALTER TABLE author ADD COLUMN {column} {definition}'))
            changed = True
    if changed:
        db.session.commit()

    used_slugs = set()
    profiles_changed = False
    for author in Author.query.order_by(Author.id).all():
        base = slugify(author.slug or author.name) or f"autor-{author.id}"
        candidate, number = base, 2
        while candidate in used_slugs:
            candidate, number = f"{base}-{number}", number + 1
        if author.slug != candidate:
            author.slug = candidate
            profiles_changed = True
        used_slugs.add(candidate)
        if author.display_order is None:
            author.display_order = 100
            profiles_changed = True
        if author.name.casefold() == "mergior alfredo goriate":
            if not author.role:
                author.role = "Fundador e Editor-Chefe"
                profiles_changed = True
            if not author.headline:
                author.headline = "Investigador, autor e fundador do Sussurros do Saber."
                profiles_changed = True
            if author.display_order != 1:
                author.display_order = 1
                profiles_changed = True
    if profiles_changed:
        db.session.commit()
    db.session.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_author_slug ON author (slug)"
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
        author = Author(
            name=name,
            slug=slugify(name),
            role=("Fundador e Editor-Chefe" if name.casefold() == "mergior alfredo goriate" else "Autor"),
            headline=(
                "Investigador, autor e fundador do Sussurros do Saber."
                if name.casefold() == "mergior alfredo goriate"
                else "Autor do Sussurros do Saber."
            ),
            display_order=(1 if name.casefold() == "mergior alfredo goriate" else 100),
            bio="Autor do Sussurros do Saber.",
        )
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
    app.run(
        debug=(not IS_PRODUCTION and os.getenv("FLASK_DEBUG", "").lower() == "true"),
        host="127.0.0.1",
        port=5000,
    )
