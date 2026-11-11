import os
from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


UNLIMITED_GET_ENDPOINTS = frozenset({
    'home', 'articles', 'article', 'journals', 'journal_detail',
    'authors', 'author_detail', 'language.choose',
})


def default_rate_limits():
    # Browsing and reading public articles and choosing a language stay available
    # after repeated visits. Mutations retain their endpoint-specific limits.
    if request.method in {'GET', 'HEAD'} and request.endpoint in UNLIMITED_GET_ENDPOINTS:
        return ''
    return '300 per day; 100 per hour'


def rate_limit_storage_uri():
    configured = (
        os.getenv("RATELIMIT_STORAGE_URI", "").strip()
        or os.getenv("REDIS_URL", "").strip()
    )
    production = (
        os.getenv("RENDER", "").lower() == "true"
        or os.getenv("FLASK_ENV", "").lower() == "production"
    )
    if production and not configured:
        raise RuntimeError(
            "RATELIMIT_STORAGE_URI ou REDIS_URL é obrigatória em produção."
        )
    return configured or "memory://"


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[default_rate_limits],
    storage_uri=rate_limit_storage_uri(),
)
