"""Bound numeric request values before passing them to database drivers."""
import re
from flask import request
from werkzeug.routing import IntegerConverter

MAX_DATABASE_ID = 2147483647


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
