"""Privacy-conscious, best-effort measurement of successfully served public resources."""
import hashlib
import hmac
import ipaddress
import os
import re
from datetime import timedelta
from flask import current_app, request
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from models import db, utcnow
from scientific_metrics_models import ScientificMetricDay, ScientificMetricReceipt, ScientificMetricStart

BOT = re.compile(r'bot|spider|crawler|slurp|headless|curl|wget|python|preview|monitor|facebook|whatsapp|lighthouse|selenium|playwright', re.I)


def scientific(journal):
    return bool(journal.published and (journal.content_markdown or '').strip())


def country_code():
    # An optional server-side middleware may supply this value; HTTP headers cannot.
    country = request.environ.get('sussurros.country_code', 'ZZ')
    return country if isinstance(country, str) and re.fullmatch('[A-Z]{2}', country) and country not in {'XX', 'T1'} else 'ZZ'


def record(journal, kind, response):
    if kind not in {'view','download'} or not scientific(journal) or request.method != 'GET' or response.status_code != 200:
        return response
    if kind == 'view' and (response.mimetype != 'text/html' or request.headers.get('Sec-Fetch-Dest','') not in {'','document'}):
        return response
    if kind == 'download' and response.mimetype != 'application/pdf':
        return response
    # Avoid shared caches bypassing the origin's measurement. The PDF generation cache is retained.
    response.headers['Cache-Control'] = 'private, no-store'
    ua = request.headers.get('User-Agent', '')[:500]
    if (not ua or BOT.search(ua) or request.headers.get('DNT') == '1'
            or request.headers.get('Sec-GPC') == '1' or request.headers.get('Purpose') == 'prefetch'
            or request.headers.get('Sec-Purpose', '').startswith('prefetch')):
        return response
    try:
        peer=request.environ.get('werkzeug.proxy_fix.orig',{}).get('REMOTE_ADDR',request.remote_addr)
        networks=[ipaddress.ip_network(value.strip()) for value in os.getenv('SCIENTIFIC_METRICS_TRUSTED_PROXIES','').split(',') if value.strip()]
        trusted=any(ipaddress.ip_address(peer or '') in network for network in networks)
        address = str(ipaddress.ip_address((request.remote_addr if trusted else peer) or ''))
    except ValueError:
        return response
    now = utcnow(); day = now.date()
    secret = os.getenv('SCIENTIFIC_METRICS_HMAC_KEY') or current_app.secret_key
    payload = f'{day}|{journal.id}|{kind}|{address}'
    digest = hmac.new(str(secret).encode(), payload.encode(), hashlib.sha256).hexdigest()
    dialect = db.engine.dialect.name
    if dialect not in {'sqlite', 'postgresql'}:
        return response
    if dialect == 'sqlite':
        from sqlalchemy.dialects.sqlite import insert
    else:
        from sqlalchemy.dialects.postgresql import insert
    try:
        with db.engine.begin() as connection:
            # The unique receipt and aggregate increment commit together across workers.
            receipt = insert(ScientificMetricReceipt).values(digest=digest, day=day).on_conflict_do_nothing()
            if connection.execute(receipt.returning(ScientificMetricReceipt.digest)).scalar_one_or_none() is not None:
                start = insert(ScientificMetricStart).values(journal_id=journal.id, started_at=now).on_conflict_do_nothing()
                connection.execute(start)
                table = ScientificMetricDay.__table__
                values = dict(journal_id=journal.id, day=day, country=country_code(), views=int(kind=='view'), downloads=int(kind=='download'))
                statement = insert(table).values(**values)
                column = 'views' if kind == 'view' else 'downloads'
                connection.execute(statement.on_conflict_do_update(index_elements=['journal_id','day','country'],
                    set_={column: table.c[column] + 1}))
                connection.execute(delete(ScientificMetricReceipt).where(ScientificMetricReceipt.day < day-timedelta(days=2)))
    except SQLAlchemyError:
        current_app.logger.warning('Scientific metrics write unavailable; public resource served.')
    return response
