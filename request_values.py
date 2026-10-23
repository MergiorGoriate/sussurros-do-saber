"""Bound numeric request values before passing them to database drivers."""
import re
from flask import request
from werkzeug.routing import IntegerConverter

MAX_DATABASE_ID = 2147483647


def database_id(value, *, optional=False):
    """Reject malformed or overflowing form IDs before binding SQL parameters."""
    if optional and value in (None, ''):
        return None
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,10}', value):
        raise ValueError('Identificador inválido.')
    result = int(value)
    if not 1 <= result <= MAX_DATABASE_ID:
        raise ValueError('Identificador inválido.')
    return result


class DatabaseIdConverter(IntegerConverter):
    # Numeric routes use INTEGER identifiers and positive submission steps.
    regex = r'[0-9]{1,10}'

    def __init__(self, url_map, **kwargs):
        kwargs.setdefault('min', 1)
        kwargs.setdefault('max', MAX_DATABASE_ID)
        super().__init__(url_map, **kwargs)


def pagination_page(name='page'):
    raw = request.args.get(name, '1')
    if not re.fullmatch(r'[0-9]{1,10}', raw):
        return 1
    page = int(raw)
    return page if 1 <= page <= MAX_DATABASE_ID else 1
