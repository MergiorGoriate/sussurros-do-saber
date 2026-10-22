"""Article-only heading policy applied after the shared Markdown sanitizer."""
import re
import unicodedata

from bs4 import BeautifulSoup


def prepare_article_headings(cleaned, *, prefix="sec"):
    soup = BeautifulSoup(cleaned, 'html.parser')
    used = {element['id'] for element in soup.select('[id]')}
    for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        if heading.find_parent(['pre', 'code']):
            continue
        # The separate article title is the page's only H1. Keep source intact.
        if heading.name == 'h1':
            heading.name = 'h2'
        if heading.get('id'):
            continue
        label = heading.get_text(' ', strip=True)
        normalized = unicodedata.normalize('NFKD', label).encode('ascii', 'ignore').decode().lower()
        base = prefix + '-' + (re.sub(r'[^a-z0-9]+', '-', normalized).strip('-') or 'seccao')
        candidate, suffix = base, 2
        while candidate in used:
            candidate, suffix = f'{base}-{suffix}', suffix + 1
        heading['id'] = candidate
        used.add(candidate)
    return str(soup)
