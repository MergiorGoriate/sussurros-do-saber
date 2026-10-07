"""Isolated E2E server: shared synthetic traffic must not consume public quotas."""
import os
if not os.environ.get('DATABASE_URL','').startswith('sqlite:') or os.environ.get('RENDER','').lower()=='true' or os.environ.get('FLASK_ENV','').lower()=='production':
    raise RuntimeError('E2E server requires isolated SQLite outside production')
from app import app
from extensions import limiter
# All identities/requests share localhost in CI. Authentication, 2FA, sessions and
# CSRF remain enabled; only public rate quotas are disabled in this test module.
app.config['RATELIMIT_ENABLED']=False
limiter.enabled=False
