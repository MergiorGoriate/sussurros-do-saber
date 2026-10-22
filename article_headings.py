"""Article-only heading presentation, applied after the shared HTML sanitizer."""
from bs4 import BeautifulSoup
from markdown.extensions.toc import slugify


def article_headings(cleaned, namespace='article-section'):
    soup = BeautifulSoup(cleaned, 'html.parser')
    used = {element['id'] for element in soup.select('[id]')}
    for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        # The article title already owns the page's H1. Keep the source intact.
        if heading.name == 'h1':
            heading.name = 'h2'
        # Trusted endnote headings already have IDs referenced by aria-labelledby.
        # Untrusted source heading IDs were removed by the shared sanitizer.
        if heading.get('id'):
            continue
        base = namespace + '-' + (slugify(heading.get_text(' ', strip=True), '-') or 'section')
        ident, number = base, 2
        while ident in used:
            ident = f'{base}-{number}'
            number += 1
        used.add(ident)
        heading['id'] = ident
    return str(soup)
