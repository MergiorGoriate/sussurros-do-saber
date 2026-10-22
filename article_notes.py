"""Scoped Markdown footnotes with narrowly allowed IDs and accessible backlinks."""
import itertools
import re
from flask import g, has_request_context
import markdown
from markdown.extensions.footnotes import FootnoteExtension
from bs4 import BeautifulSoup

_counter = itertools.count(1)
_IMAGE_ATTRIBUTES = {'src','srcset','sizes','alt','title','loading','decoding','width','height'}


def render_notes_markdown(source, *, strict_headings=False):
    if has_request_context():
        number = getattr(g, '_markdown_notes_counter', 0) + 1
        g._markdown_notes_counter = number
    else:
        number = next(_counter)
    namespace = f'md{number}'
    renderer = markdown.Markdown(extensions=['extra','sane_lists'], extension_configs={
        'extra': {'footnotes':{'SEPARATOR':f'-{namespace}-','USE_DEFINITION_ORDER':False,
                     'BACKLINK_TEXT':'Voltar ao texto','BACKLINK_TITLE':'Voltar à chamada %d'}}})
    if strict_headings:
        # Configure the existing block processor, after fenced-code handling.
        # A hash run without a following space is literal text in articles.
        renderer.parser.blockprocessors['hashheader'].RE = re.compile(
            r'(?:^|\n)(?P<level>#{1,6}) +(?P<header>(?:\\.|[^\\])*?)#*(?:\n|$)')
    rendered = renderer.convert(source)
    extension = next(item for item in renderer.registeredExtensions if isinstance(item,FootnoteExtension))
    info = dict(namespace=namespace, notes={extension.makeFootnoteId(label) for label in extension.footnotes},
                refs=set(extension.used_refs))
    return rendered, info


def allowed_markdown_attribute(info, tag, name, value):
    if tag == 'a' and name in {'href','title','rel'}:
        return True
    if tag == 'img' and name in _IMAGE_ATTRIBUTES:
        return True
    if name == 'id':
        return (tag == 'li' and value in info['notes']) or (tag == 'sup' and value in info['refs'])
    if name == 'class':
        return (tag == 'div' and value == 'footnote' and bool(info['notes'])) or (
            tag == 'a' and value in {'footnote-ref','footnote-backref'} and bool(info['notes']))
    return False


def decorate_notes(cleaned, info):
    if not info['notes']:
        return cleaned
    soup = BeautifulSoup(cleaned,'html.parser')
    for index,container in enumerate(soup.select('div.footnote')):
        if not any(item.get('id') in info['notes'] for item in container.find_all('li')):
            continue
        heading = soup.new_tag('h2',id=f'notes-{info["namespace"]}-{index}')
        heading.string = 'Notas e referências'
        container.insert(0,heading)
        container['role'] = 'doc-endnotes'
        container['aria-labelledby'] = heading['id']
    for target in soup.find_all(['li','sup']):
        if target.get('id') in info['notes'] | info['refs']:
            target['tabindex'] = '-1'
    for link in soup.select('a.footnote-ref'):
        if link.get('href','').removeprefix('#') not in info['notes']:
            continue
        number = link.get_text(strip=True)
        link['role'] = 'doc-noteref'
        link['aria-label'] = f'Nota {number}'
        link['title'] = f'Ler nota {number}'
    for link in soup.select('a.footnote-backref'):
        if link.get('href','').removeprefix('#') not in info['refs']:
            link.decompose()
            continue
        link['role'] = 'doc-backlink'
        link['aria-label'] = link.get('title','Voltar à chamada no texto')
        link.string = 'Voltar ao texto'
    return str(soup)
