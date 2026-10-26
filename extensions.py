import os
from flask import request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


UNLIMITED_READING_ENDPOINTS = frozenset({'article', 'journal_detail'})


def default_rate_limits():
    # Only reading published articles is unlimited. Mutations and other routes
    # retain their existing defaults and endpoint-specific limits.
    if request.method in {'GET', 'HEAD'} and request.endpoint in UNLIMITED_READING_ENDPOINTS:
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
