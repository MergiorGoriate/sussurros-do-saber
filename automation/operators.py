"""Independent read-only checks producing bounded structured reports."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shutil
from urllib.parse import quote, urlsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from markdown import markdown

from automation.config import RESEARCH_TOPICS, SITE_ORIGIN
from automation.http import CROSSREF_URL, FetchError, fetch, portal_url
from automation.models import AutomationDiscovery, AutomationRun
from content_audit import assess_article
from governance_models import ArticleWorkflow, StaffPeerReview, StaffTask
from models import Article, Journal, db, utcnow
from news_models import NewsVersion
from submission_models import Manuscript


def report(**details):
    return {'findings': [], 'truncated': False, **details}


def finding(result, severity, code, subject, description, recommendation=''):
    if len(result['findings']) >= 200:
        result['truncated'] = True
        return
    result['findings'].append(dict(severity=severity, code=code, subject=subject,
                                   description=description, recommendation=recommendation))


def parsed_link(value):
    if not isinstance(value, str) or not value or len(value) > 2000 or any(c.isspace() or ord(c) < 32 or c == '\\' for c in value):
        return None
    try:
        parts = urlsplit(value)
        if parts.username or parts.password or parts.port not in (None, 80, 443):
            return None
        if parts.scheme in ('http', 'https') and parts.hostname:
            return parts
        if not parts.scheme and not parts.netloc and (parts.path.startswith('/') or parts.fragment and not parts.path):
            return parts
    except ValueError:
        pass
    return None


def linked_content_exists(path):
    match = re.fullmatch(r'/artigo/([a-z0-9-]+)/?', path)
    if match:
        return Article.public_query().filter_by(slug=match[1]).first() is not None
    match = re.fullmatch(r'/(noticias|en/news)/([a-z0-9-]+)/?', path)
    if match:
        return NewsVersion.public('en' if match[1].startswith('en') else 'pt').filter_by(slug=match[2]).first() is not None
    match = re.fullmatch(r'/revistas/([a-z0-9-]+)/?', path)
    if match:
        return Journal.query.filter_by(slug=match[1], published=True).first() is not None
    return None


def review_links(result, subject, soup, public):
    invalid, missing, absent_alt, external = 0, 0, 0, 0
    elements = soup.select('a[href], img')
    if len(elements) > 100:
        result['truncated'] = True
    for element in elements[:100]:
        image = element.name == 'img'
        if image and not element.get('alt', '').strip():
            absent_alt += 1
        href = element.get('src' if image else 'href', '')
        if href.startswith(('mailto:', 'tel:', '#')) and not image:
            continue
        parsed = parsed_link(href)
        if not parsed:
            invalid += 1
        elif parsed.hostname and parsed.hostname not in {'www.sussurrosdosaber.com', 'sussurrosdosaber.com'}:
            external += 1
        elif public and not image and linked_content_exists(parsed.path) is False:
            missing += 1
    result['external_links_unverified'] += external
    if invalid:
        finding(result, 'HIGH', 'invalid-link', subject, f'{invalid} ligações ou imagens com endereços inválidos.', 'Rever as ligações no editor.')
    if missing:
        finding(result, 'HIGH', 'missing-internal', subject, f'{missing} ligações para conteúdos internos ausentes ou privados.', 'Confirmar os destinos públicos.')
    if absent_alt:
        finding(result, 'MEDIUM', 'image-alt', subject, f'{absent_alt} imagens sem descrição alternativa.', 'Rever o texto alternativo.')


def review_content(result, kind, item):
    subject = f'{kind}:{item.id}'
    journal = kind == 'revista'
    title = item.title or ''
    summary = (item.description if journal else item.summary) or ''
    body = ((item.content_markdown or item.guidelines) if journal else item.body) or ''
    cover = (item.cover_image if journal else item.image) or ''
    public = item.published if journal else item.status == 'published'
    if not title.strip() or not summary.strip() or not body.strip():
        finding(result, 'CRITICAL' if public else 'HIGH', 'required', subject, 'Título, descrição ou corpo editorial incompleto.', 'Completar os campos no editor.')
    if title and len(title) > 70:
        finding(result, 'LOW', 'title-length', subject, 'Título superior a 70 caracteres.')
    if summary and not 70 <= len(summary) <= 170:
        finding(result, 'LOW', 'description-length', subject, 'Comprimento da descrição fora do intervalo de referência.')
    if not item.slug or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', item.slug):
        finding(result, 'HIGH', 'slug', subject, 'Identificador da rota ausente ou fora da convenção.')
    if not cover and not (kind == 'artigo' and item.cover_video):
        finding(result, 'MEDIUM', 'missing-cover', subject, 'Sem capa definida.')
    elif cover and not parsed_link(cover):
        finding(result, 'HIGH', 'cover-url', subject, 'Endereço da capa inválido.')
    if cover and kind in ('noticia', 'revista') and not (item.image_alt if kind == 'noticia' else item.cover_alt):
        finding(result, 'MEDIUM', 'cover-alt', subject, 'Capa sem texto alternativo.')
    if len(body) > 200000:
        result['truncated'] = True
    soup = BeautifulSoup(markdown(body[:200000], extensions=['extra']), 'html.parser')
    headings = [int(x.name[1]) for x in soup.find_all(re.compile(r'^h[1-6]$'))]
    if any(current > previous + 1 for previous, current in zip(headings, headings[1:])):
        finding(result, 'MEDIUM', 'heading-order', subject, 'Saltos na hierarquia dos títulos internos.')
    if len(body) > 1500 and not headings:
        finding(result, 'LOW', 'no-headings', subject, 'Texto longo sem títulos internos.')
    if kind == 'artigo':
        audit = assess_article(dict(slug=item.slug, title=title, body=body[:200000], references=(item.references or '')[:50000], image=cover))
        for flag in audit['flags']:
            level = 'HIGH' if flag in {'demo_body_published', 'unresolved_editorial_note'} else 'INFO'
            finding(result, level, flag, subject, 'Sinal da auditoria editorial: ' + flag, 'Validar manualmente o conteúdo e as fontes.')
    review_links(result, subject, soup, public)
    model = type(item)
    if title:
        query = model.query.filter(db.func.lower(model.title) == title.lower(), model.id != item.id)
        if kind == 'noticia':
            query = query.filter_by(language=item.language)
        if query.first():
            finding(result, 'MEDIUM', 'duplicate-title', subject, 'Existe outro registo com título igual.', 'Confirmar se os conteúdos são distintos.')


def editorial(settings, cursor):
    result = report(scanned=0, external_links_unverified=0, next_cursor={})
    for kind, model in (('artigo', Article), ('noticia', NewsVersion), ('revista', Journal)):
        batch = settings['batch']
        rows = model.query.filter(model.id > cursor.get(kind, 0)).order_by(model.id).limit(batch).all()
        for item in rows:
            review_content(result, kind, item)
        result['scanned'] += len(rows)
        result['next_cursor'][kind] = rows[-1].id if len(rows) == batch else 0
    return result


def get_portal(result, path, timeout, severity='HIGH'):
    try:
        status, headers, body = fetch(portal_url(path), timeout)
    except FetchError as error:
        finding(result, severity, 'unavailable', path, str(error), 'Confirmar o serviço e a ligação pública.')
        return None
    if 300 <= status < 400:
        finding(result, 'MEDIUM', 'redirect', path, f'Resposta de redireccionamento HTTP {status}.', 'Confirmar o destino e a cadeia de redireccionamento.')
        return None
    if status != 200:
        finding(result, severity, 'http', path, f'Resposta HTTP {status}.', 'Confirmar a disponibilidade da página.')
        return None
    return headers, body


def seo(settings, cursor):
    result = report(pages=[], resources=[], external_links_unverified=0)
    for path in settings['paths']:
        response = get_portal(result, path, settings['timeout'])
        if response is None:
            continue
        headers, body = response
        soup = BeautifulSoup(body, 'html.parser')
        result['pages'].append(path)
        review_links(result, path, soup, True)
        title = soup.title
        description = soup.select_one('meta[name="description" i]')
        canonical = soup.select_one('link[rel="canonical"]')
        robots = soup.select_one('meta[name="robots" i]')
        header_robots = next((value for key, value in headers.items() if key.lower() == 'x-robots-tag'), '')
        if not title or not title.get_text(strip=True):
            finding(result, 'HIGH', 'missing-title', path, 'A página não apresentou título HTML.')
        if not description or not description.get('content', '').strip():
            finding(result, 'MEDIUM', 'missing-description', path, 'A página não apresentou descrição SEO.')
        if not canonical or canonical.get('href') != portal_url(path):
            finding(result, 'MEDIUM', 'canonical', path, 'Canonical ausente ou diferente do endereço seleccionado.')
        if 'noindex' in (header_robots + ' ' + (robots.get('content', '') if robots else '')).lower():
            finding(result, 'MEDIUM', 'noindex', path, 'Directiva noindex encontrada.', 'Confirmar a política editorial de indexação.')
    for path in ('/robots.txt', '/sitemap.xml', '/video-sitemap.xml'):
        response = get_portal(result, path, settings['timeout'])
        if response is None:
            continue
        _, body = response
        result['resources'].append(path)
        if path == '/robots.txt':
            parser = RobotFileParser()
            parser.parse(body.decode('utf-8', errors='replace').splitlines())
            if SITE_ORIGIN + '/sitemap.xml' not in (parser.site_maps() or []):
                finding(result, 'MEDIUM', 'robots-sitemap', path, 'Não foi encontrada referência ao sitemap canónico.')
            for selected in settings['paths']:
                if not parser.can_fetch('Googlebot', portal_url(selected)):
                    finding(result, 'MEDIUM', 'robots-blocked', selected, 'O robots.txt impede o rastreio para Googlebot.')
            continue
        try:
            if b'<!doctype' in body.lower() or b'<!entity' in body.lower():
                raise ValueError()
            root = ElementTree.fromstring(body)
            if root.tag.rsplit('}', 1)[-1] not in {'urlset', 'sitemapindex'}:
                raise ValueError()
            for location in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
                if not (location.text or '').startswith(SITE_ORIGIN + '/'):
                    finding(result, 'MEDIUM', 'sitemap-origin', path, 'O sitemap contém um endereço fora do domínio canónico.')
                    break
        except (ValueError, ElementTree.ParseError):
            finding(result, 'HIGH', 'sitemap-invalid', path, 'O sitemap não contém XML válido dentro dos limites.')
    return result


def backup_evidence(result, max_age):
    configured = os.getenv('AUTOMATION_BACKUP_REPORT_PATH', '')
    result['backup_creation_date'] = None
    if not configured:
        finding(result, 'INFO', 'backup-unconfigured', 'backup', 'Evidência de restauro não configurada.')
        return
    try:
        path = Path(configured)
        if not path.is_file():
            raise ValueError()
        with path.open('rb') as source:
            data = source.read(32769)
        if len(data) > 32768:
            raise ValueError()
        evidence = json.loads(data)
        digest = evidence.get('archive_sha256', '')
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
            raise ValueError()
        restored = datetime.fromisoformat(evidence['restored_at_utc'])
        if restored.tzinfo is None or restored > datetime.now(timezone.utc):
            raise ValueError()
        result['restore_verified_at'] = restored.isoformat()
        if evidence.get('restore_completed') is not True or evidence.get('broken_relations') != 0:
            finding(result, 'HIGH', 'backup-failed', 'backup', 'O relatório de restauro indica falha ou relações inválidas.')
        elif restored < datetime.now(timezone.utc) - timedelta(days=max_age):
            finding(result, 'HIGH', 'backup-old', 'backup', 'A última verificação de restauro excedeu o prazo configurado.')
        else:
            result['restore_integrity'] = 'verified_by_report'
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        finding(result, 'HIGH', 'backup-invalid', 'backup', 'O relatório de restauro não está disponível ou é inválido.')


def infrastructure(settings, cursor):
    result = report(database='unknown', container_disk_percent=None)
    response = get_portal(result, '/healthz', settings['timeout'], severity='CRITICAL')
    result['public_health'] = 'responded' if response else 'unavailable'
    if response:
        try:
            if json.loads(response[1]).get('ok') is not True:
                raise ValueError()
        except (ValueError, AttributeError):
            finding(result, 'CRITICAL', 'health-response', 'healthz', 'A resposta de saúde não confirmou funcionamento.')
    result['database'] = 'ok' if db.session.execute(db.text('SELECT 1')).scalar() == 1 else 'unknown'
    result['database_dialect'] = db.engine.dialect.name
    result['queue_pending'] = AutomationRun.query.filter_by(status='queued').count()
    result['queue_running'] = AutomationRun.query.filter_by(status='running').count()
    production = os.getenv('FLASK_ENV') == 'production' or os.getenv('RENDER') == 'true'
    if production and result['database_dialect'] != 'postgresql':
        finding(result, 'HIGH', 'database-dialect', 'database', 'O ambiente de produção não utiliza PostgreSQL.')
    disk = shutil.disk_usage(Path.cwd())
    result['container_disk_percent'] = round(disk.used * 100 / disk.total, 1)
    if result['container_disk_percent'] >= 90:
        finding(result, 'HIGH', 'disk', 'container', 'O sistema de ficheiros acessível ultrapassou 90% de ocupação.')
    result['recent_failed_runs'] = AutomationRun.query.filter(
        AutomationRun.status == 'failed', AutomationRun.finished_at >= utcnow() - timedelta(days=7)).count()
    if result['recent_failed_runs']:
        finding(result, 'MEDIUM', 'automation-failures', 'automation', 'Existem execuções falhadas nos últimos sete dias.', 'Consultar o histórico.')
    backup_evidence(result, settings['backup_age_days'])
    return result


def clean(value, maximum):
    source = str(value or '')[:maximum * 4].replace('\x00', '')
    return ' '.join(BeautifulSoup(source, 'html.parser').get_text(' ', strip=True).split())[:maximum]


def research_record(raw, topic):
    if not isinstance(raw, dict):
        return None
    doi = raw.get('DOI')
    if not isinstance(doi, str) or len(doi) > 255 or not re.fullmatch(r'10\.\d{4,9}/[!-~]+', doi):
        return None
    title = raw.get('title')
    if not isinstance(title, list) or not title or not isinstance(title[0], str):
        return None
    title = clean(title[0], 300)
    if not title:
        return None
    authors = raw.get('author') or []
    if not isinstance(authors, list):
        authors = []
    names = [clean(' '.join(str(a.get(field) or '') for field in ('given', 'family')), 100)
             for a in authors[:12] if isinstance(a, dict)]
    parts = raw.get('published') if isinstance(raw.get('published'), dict) else {}
    dates = parts.get('date-parts') or []
    date = None
    if isinstance(dates, list) and dates and isinstance(dates[0], list):
        numbers = dates[0][:3]
        if numbers and all(type(n) is int for n in numbers):
            try:
                datetime(*(numbers + [1] * 3)[:3])
                date = '-'.join(f'{n:04d}' if i == 0 else f'{n:02d}' for i, n in enumerate(numbers))
            except ValueError:
                pass
    return dict(doi=doi.lower(), title=title, authors=[name for name in names if name],
                published=date, topic=topic, source='Crossref', url='https://doi.org/' + quote(doi, safe='/'))


def research(settings, cursor):
    result = report(records=[], topics_checked=[], duplicates=0)
    encountered = set()
    start = (utcnow().date() - timedelta(days=settings['days'])).isoformat()
    for topic in settings['topics']:
        params = {'query.bibliographic': RESEARCH_TOPICS[topic], 'filter': f'from-pub-date:{start}',
                  'rows': 10, 'select': 'DOI,title,author,published,URL'}
        try:
            status, _, body = fetch(CROSSREF_URL, settings['timeout'], params)
            if status != 200:
                raise FetchError()
            data = json.loads(body)['message']['items']
            if not isinstance(data, list):
                raise ValueError()
        except (FetchError, ValueError, KeyError, TypeError, UnicodeError):
            finding(result, 'HIGH', 'source-error', topic, 'Não foi possível obter metadados da Crossref dentro dos limites definidos.', 'Repetir posteriormente.')
            continue
        result['topics_checked'].append(topic)
        for raw in data[:10]:
            record = research_record(raw, topic)
            if not record:
                continue
            doi = record['doi']
            if doi in encountered or db.session.get(AutomationDiscovery, doi):
                result['duplicates'] += 1
                continue
            encountered.add(doi)
            result['records'].append(record)
    return result


def workflow(settings, cursor):
    result = report(pending={})
    cutoff = utcnow() - timedelta(days=settings['age_days'])
    today = utcnow().date()
    checks = [
        ('tarefas', StaffTask.query.filter(StaffTask.status.in_(['pending', 'in_progress', 'blocked']), StaffTask.due_on < today), 'Tarefa ultrapassou a data prevista.'),
        ('pareceres', StaffPeerReview.query.filter(StaffPeerReview.status.in_(['invited', 'accepted']), StaffPeerReview.due_on < today), 'Parecer ultrapassou a data prevista.'),
        ('submissoes', Manuscript.query.filter(Manuscript.removed_at.is_(None),
             Manuscript.status.in_(['submitted', 'screening', 'review', 'revised', 'reevaluation']), Manuscript.updated_at < cutoff), 'Submissão pendente sem actualização dentro do prazo.'),
        ('artigos', ArticleWorkflow.query.join(Article).filter(ArticleWorkflow.stage.in_(['submitted', 'review', 'changes', 'approved']), Article.updated_at < cutoff), 'Artigo a aguardar uma acção editorial.'),
    ]
    for kind, query, message in checks:
        result['pending'][kind] = query.count()
        for item in query.limit(30):
            ident = item.article_id if kind == 'artigos' else item.id
            finding(result, 'MEDIUM', 'workflow-pending', f'{kind}:{ident}', message, 'Consultar a área de trabalho editorial.')
        if result['pending'][kind] > 30:
            result['truncated'] = True
    return result


OPERATORS = {'editorial': editorial, 'seo': seo, 'infrastructure': infrastructure,
             'research': research, 'workflow': workflow}
