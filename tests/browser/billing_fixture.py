"""Read-only UI cases with synthetic financial states, outside production."""
import os
import sys
import secrets
import json
from pathlib import Path
from datetime import timedelta
if not os.getenv('DATABASE_URL','').startswith('sqlite:') or os.getenv('FLASK_ENV')=='production' or os.getenv('RENDER')=='true':
    raise RuntimeError('Billing fixtures require isolated SQLite outside production')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from werkzeug.security import generate_password_hash
from app import app
from models import db,utcnow
from submission_models import Researcher
from premium_models import PremiumPlan
from billing_models import BillingOrder,BillingJournal
with app.app_context():
    token=secrets.token_hex(8)
    owner=Researcher(name='Leitor de teste financeiro',email=token+'@example.test',password_hash=generate_password_hash('Synthetic-subscription-password-123!'),token_nonce=token,verified=True,active=True)
    plan=PremiumPlan(name='Plano de teste financeiro '+token,interval='monthly',currency='MZN',price_minor=50000,active=True)
    annual=PremiumPlan(name='Plano anual de teste '+token,interval='annual',currency='MZN',price_minor=123456,active=True)
    db.session.add_all([owner,plan,annual]);db.session.flush()
    orders={}
    for state in ['pending','paid','failed','expired']:
        order=BillingOrder(owner_id=owner.id,plan_id=plan.id,snapshot={'name':plan.name,'interval':'monthly'},
            amount_minor=50000,currency='MZN',method='mpesa',provider='clicpay',live=False,state=state,expires_at=utcnow()+timedelta(days=1))
        db.session.add(order);db.session.flush();orders[state]=order.id
        if state=='paid':db.session.add(BillingJournal(event_key='receipt:'+order.id,order_id=order.id,kind='receipt',debit='gateway_clearing',credit='premium_deferred',amount_minor=50000,currency='MZN',live=False))
    db.session.commit()
    cookie=app.session_interface.get_signing_serializer(app).dumps({'researcher_id':owner.id,'researcher_nonce':token})
    print(json.dumps({'cookie':cookie,'plan':plan.id,'orders':orders,'annual':annual.id,'email':owner.email,'password':'Synthetic-subscription-password-123!'}))
