"""Shared public search and resolver links; never changes stored metadata."""
import re
from urllib.parse import quote

from sqlalchemy import func, or_


# Explicit mappings keep the same behaviour on SQLite and PostgreSQL.
_ACCENTS = dict(zip('áàâãäéèêëíìîïóòôõöúùûüç',
                    'aaaaaeeeeiiiiooooouuuuc'))
_FOLD = str.maketrans({**_ACCENTS, **{k.upper(): v for k, v in _ACCENTS.items()}})


def _searchable(column):
    expression = func.lower(column)
    for accented, plain in _ACCENTS.items():
        expression = func.replace(expression, accented.upper(), plain)
        expression = func.replace(expression, accented, plain)
    return expression


def search_term(value):
    value = (value or '').strip().lower()
    value = re.sub(r'^https?://(?:www\.)?(?:(?:dx\.)?doi\.org|orcid\.org)/', '', value)
    value = re.sub(r'^(?:doi|orcid)\s*:\s*', '', value)
    return value[:120]


def metadata_match(value, *columns):
    """Literal partial matches, using SQL supported by SQLite and PostgreSQL."""
    term = search_term(value).translate(_FOLD)
    return or_(*(_searchable(column).contains(term, autoescape=True) for column in columns))


def doi_url(value):
    """Return a safe resolver URL, without claiming that a DOI is registered."""
    identifier = (value or '').strip()
    identifier = re.sub(r'^https?://(?:www\.)?(?:dx\.)?doi\.org/', '', identifier, flags=re.I)
    identifier = re.sub(r'^doi\s*:\s*', '', identifier, flags=re.I)
    if not re.fullmatch(r'10\.\d{4,9}/[^\s<>\"]+', identifier):
        return ''
    return 'https://doi.org/' + quote(identifier, safe='/():;._-')
