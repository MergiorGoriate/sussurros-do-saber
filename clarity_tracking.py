"""Consent-gated analytics on anonymous, public editorial pages only."""
import os
import re
from flask import g, request, session


def project_id():
    value = os.getenv('CLARITY_PROJECT_ID', 'zdbchcjjtg').strip()
    if not re.fullmatch(r'[a-z0-9]{5,32}', value):
        return ''
    if request.method != 'GET' or request.args:
        return ''
    if any(session.get(key) for key in ('admin_authenticated', 'admin_id',
                                      'pending_2fa_username', 'researcher_id')):
        return ''
    if (request.endpoint not in {'home', 'articles', 'journals', 'authors', 'privacy', 'advertising_policy'}
            and not getattr(g, 'google_cmp_public_content', False)):
        return ''
    return value
