import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

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
    default_limits=["300 per day", "100 per hour"],
    storage_uri=rate_limit_storage_uri(),
)
