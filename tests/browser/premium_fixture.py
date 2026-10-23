"""Synthetic Premium identities and products for an isolated SQLite browser run."""
import os
import sys
import json
import secrets
import time
from pathlib import Path
from datetime import timedelta
if not os.environ.get('DATABASE_URL', '').startswith('sqlite:') or os.getenv('FLASK_ENV') == 'production' or os.getenv('RENDER') == 'true':
    raise RuntimeError('Premium fixtures require isolated SQLite outside production')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import app
from admin import admin_security_stamp
from models import db, AdminUser, utcnow
from submission_models import Researcher
from premium_models import PremiumPlan, PremiumSubscription, PremiumContent
with app.app_context():
    token = secrets.token_hex(8)
    account = Researcher(name='Leitor Premium de teste', email=token+'@example.test', password_hash='unused',
                         token_nonce=token, active=True, verified=True)
    free = Researcher(name='Leitor gratuito de teste', email='free-'+token+'@example.test', password_hash='unused',
                      token_nonce=token, active=True, verified=True)
    admin = AdminUser(username='premium-admin-'+token, display_name='Gestor Premium', password_hash='unused',
                      is_superadmin=True, two_factor_enabled=True, totp_secret='JBSWY3DPEHPK3PXP')
    plan = PremiumPlan(name='Plano de teste '+token, interval='monthly', price_minor=15000, currency='MZN', active=True)
    content = PremiumContent(title='Curso de teste '+token, summary='Descrição pública de um curso especializado.', kind='course',
                             body='CONTEUDO-RESERVADO-'+token+'\n\n## Aprender\n\nExplicação de teste.', published=True)
    db.session.add_all([account, free, admin, plan, content]); db.session.flush()
    db.session.add(PremiumSubscription(owner_id=account.id, plan_id=plan.id, starts_at=utcnow()-timedelta(days=1),
        ends_at=utcnow()+timedelta(days=30), status='active', source='complimentary', reason='Oferta de teste isolado',
        plan_snapshot=dict(name=plan.name,interval='monthly',currency='MZN',price_minor=15000)))
    db.session.commit()
    serializer=app.session_interface.get_signing_serializer(app)
    print(json.dumps(dict(content_id=content.id, title=content.title, secret='CONTEUDO-RESERVADO-'+token,
        owner_id=free.id, plan_name=plan.name, plan_id=plan.id,
        member_cookie=serializer.dumps(dict(researcher_id=account.id,researcher_nonce=token)),
        free_cookie=serializer.dumps(dict(researcher_id=free.id,researcher_nonce=token)),
        admin_cookie=serializer.dumps(dict(admin_authenticated=True,admin_id=admin.id,admin_superuser=True,
            admin_2fa_verified=True,admin_last_activity_at=time.time(),admin_security_stamp=admin_security_stamp(admin))))))
