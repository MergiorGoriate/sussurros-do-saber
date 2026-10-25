"""Shared public search and resolver links; never changes stored metadata."""
import re
import sqlite3
from urllib.parse import quote

from sqlalchemy import String, event, or_
from sqlalchemy.engine import Engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement


# Explicit mappings keep the same behaviour on SQLite and PostgreSQL.
_ACCENTS = dict(zip('áàâãäéèêëíìîïóòôõöúùûüç',
                    'aaaaaeeeeiiiiooooouuuuc'))
_FOLD = str.maketrans({**_ACCENTS, **{k.upper(): v for k, v in _ACCENTS.items()}})


class _searchable(FunctionElement):
    """Compile a shallow normalization expression for each supported database."""
    type = String()
    inherit_cache = True


@compiles(_searchable, 'sqlite')
def _sqlite_searchable(element, compiler, **kwargs):
    return "sds_search_fold(%s)" % compiler.process(element.clauses, **kwargs)


@compiles(_searchable, 'postgresql')
def _postgresql_searchable(element, compiler, **kwargs):
    source = ''.join(_ACCENTS)
    target = ''.join(_ACCENTS.values())
    # These constants are maintained here, never supplied by the request.
    return "translate(lower(%s), '%s', '%s')" % (
        compiler.process(element.clauses, **kwargs), source + source.upper(),
        target + target)


@event.listens_for(Engine, 'connect')
def _register_sqlite_search(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.create_function(
            'sds_search_fold', 1,
            lambda value: value.lower().translate(_FOLD) if value is not None else None,
            deterministic=True)


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
