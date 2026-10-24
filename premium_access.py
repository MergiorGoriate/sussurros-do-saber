"""Delegated permissions apply exclusively to Premium endpoints."""
from functools import wraps
from flask import abort, session
from admin import login_required
from models import db
from premium_models import PremiumStaff

PERMISSIONS = {'content':'Biblioteca e conteúdos', 'events':'Participantes de eventos',
               'plans':'Planos e benefícios', 'members':'Acessos de oferta',
               'finance':'Pagamentos e relatórios financeiros', 'reports':'Utilização e relatórios'}


def can(permission):
    if session.get('admin_superuser'):
        return True
    ident = session.get('admin_id')
    grant = db.session.get(PremiumStaff, ident) if ident else None
    return bool(grant and (permission in grant.permissions or permission == 'any' and grant.permissions))


def required(permission):
    def decorate(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            if not can(permission): abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorate
