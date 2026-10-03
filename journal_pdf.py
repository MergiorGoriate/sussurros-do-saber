"""Print the public article's rich content without browser/network dependencies."""
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote
from html import escape
import ipaddress
import socket
import time
import warnings
import urllib3
from bs4 import BeautifulSoup, NavigableString
from PIL import Image as PillowImage
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, Spacer, Table, TableStyle
from svglib.svglib import svg2rlg

MAX_IMAGE_BYTES = 8 * 1024 * 1024


def load_image(source, static_folder, origin, deadline):
    """Bounded fetch, pinned to public DNS addresses; redirects are revalidated."""
    url = urljoin(origin + '/', source)
    for _ in range(4):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError('Tempo de carregamento excedido')
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https') or parsed.username or parsed.password:
            raise ValueError('Endereço de imagem inválido')
        if parsed.hostname == urlparse(origin).hostname and parsed.path.startswith('/static/'):
            root = Path(static_folder).resolve()
            path = (root / unquote(parsed.path[len('/static/'):])).resolve()
            if not path.is_relative_to(root) or path.stat().st_size > MAX_IMAGE_BYTES:
                raise ValueError('Imagem local inválida')
            return path.read_bytes()
        port = parsed.port or (443 if parsed.scheme == 'https' else 80)
        if port not in (80, 443):
            raise ValueError('Porta inválida')
        addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
        ips = list(dict.fromkeys(item[4][0] for item in addresses))
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise ValueError('Endereço de rede privado')
        options = dict(timeout=urllib3.Timeout(connect=min(3, remaining), read=min(4, remaining)), retries=False)
        if parsed.scheme == 'https':
            pool = urllib3.HTTPSConnectionPool(ips[0], port, server_hostname=parsed.hostname,
                                              assert_hostname=parsed.hostname, cert_reqs='CERT_REQUIRED', **options)
        else:
            pool = urllib3.HTTPConnectionPool(ips[0], port, **options)
        response = None
        try:
            response = pool.urlopen('GET', parsed.path + ('?' + parsed.query if parsed.query else ''),
                                    headers={'Host': parsed.netloc, 'User-Agent': 'SussurrosPDF/1.0'},
                                    redirect=False, preload_content=False)
            if response.status in (301, 302, 303, 307, 308):
                url = urljoin(url, response.headers.get('Location', ''))
                continue
            if response.status != 200:
                raise ValueError('Imagem indisponível')
            chunks, size = [], 0
            while True:
                if time.monotonic() >= deadline:
                    raise ValueError('Tempo excedido')
                chunk = response.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    raise ValueError('Imagem demasiado grande')
                chunks.append(chunk)
            return b''.join(chunks)
        finally:
            if response is not None:
                response.close()
            pool.close()
    raise ValueError('Demasiados redirecionamentos')


def article_flowables(html, width, height, static_folder, origin):
    styles = getSampleStyleSheet()
    soup = BeautifulSoup(str(html), 'html.parser')
    story, cache = [], {}
    deadline = time.monotonic() + 20

    def paragraph(node, style='BodyText'):
        safe = BeautifulSoup(str(node), 'html.parser')
        for tag in list(safe.find_all(True)):
            if tag.name not in ('b', 'strong', 'i', 'em', 'br', 'a', 'sup', 'sub'):
                tag.unwrap()
            else:
                tag.attrs = {'href': tag.get('href')} if tag.name == 'a' and urlparse(tag.get('href', '')).scheme in ('http', 'https', 'mailto') else {}
        return Paragraph(str(safe), styles[style])

    def walk(node):
        if isinstance(node, NavigableString):
            if node.strip():
                story.append(Paragraph(escape(str(node)), styles['BodyText']))
            return
        name = node.name
        if name == 'img':
            source, label = node.get('src', ''), node.get('alt', 'Figura')
            try:
                if source not in cache:
                    if len(cache) >= 30:
                        raise ValueError('Limite de imagens excedido')
                    raw = load_image(source, static_folder, origin, deadline)
                    with warnings.catch_warnings():
                        warnings.simplefilter('error', PillowImage.DecompressionBombWarning)
                        with PillowImage.open(BytesIO(raw)) as image:
                            image.load()
                            converted = BytesIO()
                            image.convert('RGB').save(converted, format='PNG')
                    cache[source] = converted.getvalue()
                figure = Image(BytesIO(cache[source]))
                ratio = min(width / figure.imageWidth, height * .70 / figure.imageHeight, 1)
                figure.drawWidth = figure.imageWidth * ratio
                figure.drawHeight = figure.imageHeight * ratio
                story.extend([Spacer(1, 8), figure])
                if label:
                    story.append(Paragraph(escape(label), styles['Caption'] if 'Caption' in styles else styles['BodyText']))
            except Exception:
                story.append(Paragraph(escape(f'{label} — imagem indisponível no PDF.'), styles['BodyText']))
            story.append(Spacer(1, 8))
        elif name == 'svg':
            # Only the sanitized inline chart SVG produced by the public renderer.
            viewbox = node.attrs.pop('viewbox', '0 0 800 440')
            node['viewBox'] = viewbox
            node['width'], node['height'] = viewbox.split()[2:4]
            node.insert(0, soup.new_tag('style'))
            node.style.string = '.chart-axis{stroke:#4a5568;stroke-width:2}.chart-grid{stroke:#ddd}.chart-line{fill:none;stroke:#087f72;stroke-width:3}text{font-size:14px;fill:#222}'
            drawing = svg2rlg(BytesIO(str(node).encode()))
            if drawing:
                scale = min(width / drawing.width, height * .7 / drawing.height)
                drawing.width *= scale
                drawing.height *= scale
                drawing.scale(scale, scale)
                story.extend([drawing, Spacer(1, 8)])
        elif name == 'table':
            rows = [[paragraph(cell) for cell in row.find_all(['th', 'td'], recursive=False)] for row in node.find_all('tr')]
            rows = [row for row in rows if row]
            if rows:
                columns = max(map(len, rows))
                rows = [row + [''] * (columns - len(row)) for row in rows]
                table = Table(rows, colWidths=[width / columns] * columns, repeatRows=1 if node.find('thead') else 0, hAlign='LEFT')
                table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), .4, colors.lightgrey), ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#edf2f7')), ('BOTTOMPADDING', (0, 0), (-1, -1), 7)]))
                story.extend([table, Spacer(1, 8)])
        elif name in ('h1', 'h2', 'h3', 'h4'):
            story.extend([paragraph(node, 'Heading' + str(min(int(name[1]), 3))), Spacer(1, 6)])
        elif name in ('p', 'li', 'figcaption', 'blockquote') and not node.find(['img', 'svg', 'table', 'figure']):
            story.extend([paragraph(node), Spacer(1, 6)])
        elif name not in ('script', 'style', 'iframe', 'source'):
            for child in node.children:
                walk(child)
    for child in soup.children:
        walk(child)
    return story
