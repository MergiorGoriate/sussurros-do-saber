"""Premium-only configuration; secrets remain in the server environment."""
from flask import has_app_context
from models import db
from premium_models import PremiumSetting, PremiumPlanTerms

NOTIFICATIONS = {'payment':'Pagamentos, cancelamentos e validade', 'content':'Novos conteúdos',
                 'event':'Inscrições e eventos', 'learning':'Aprendizagem e certificados'}


def settings():
    row = db.session.get(PremiumSetting, 1)
    return row.values if row else {}


def filter_methods(methods, currency):
    if not has_app_context(): return methods
    values = settings()
    currencies=values.get('currencies', ['MZN','USD','EUR','ZAR'])
    if not currencies or currency and currency not in currencies:return {}
    allowed = values.get('methods', ['mpesa','emola','netshop','stripe'])
    return {key:value for key,value in methods.items() if key in allowed}


def terms(plan):
    row = db.session.get(PremiumPlanTerms, plan.id)
    return {key:getattr(row,key) if row else '' for key in ('renewal','cancellation','refund','limitations')}


def notify(owner_id, kind, subject, body, key):
    values = settings()
    if not values.get('notifications', {}).get(kind, True): return
    from internal_notices import emit
    prefix = values.get('notice_prefix', 'Prémio')
    template = values.get('notice_templates', {}).get(kind, '{mensagem}')
    body = template.replace('{mensagem}', body).replace('{assunto}', subject)
    emit(None, prefix+': '+subject, body, researcher_id=owner_id, key='premium:'+key)
