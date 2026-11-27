"""Bounded HTTP client, restricted to the public services used by these operators."""
from time import monotonic

import requests

from automation.config import SITE_ORIGIN, SEO_PATHS

CROSSREF_URL = 'https://api.crossref.org/works'
PORTAL_PATHS = frozenset((*SEO_PATHS, '/healthz', '/robots.txt', '/sitemap.xml', '/video-sitemap.xml'))
MAX_BYTES = 512 * 1024


class FetchError(RuntimeError):
    pass


def portal_url(path):
    if path not in PORTAL_PATHS:
        raise ValueError('Destino de monitorização indisponível.')
    return SITE_ORIGIN + path


def fetch(url, timeout, params=None):
    if url != CROSSREF_URL and url not in {portal_url(path) for path in PORTAL_PATHS}:
        raise ValueError('Destino de monitorização indisponível.')
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.get(url, params=params, timeout=(timeout, timeout), stream=True,
                             allow_redirects=False, headers={'User-Agent': 'SussurrosAutomation/1.0'}) as response:
                started = monotonic()
                body = bytearray()
                for chunk in response.iter_content(16384):
                    if monotonic() - started > timeout or len(body) + len(chunk) > MAX_BYTES:
                        raise FetchError('Resposta demasiado longa ou extensa.')
                    body.extend(chunk)
                return response.status_code, dict(response.headers), bytes(body)
    except (requests.RequestException, OSError):
        raise FetchError('O serviço não respondeu dentro dos limites definidos.') from None
