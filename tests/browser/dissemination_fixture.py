"""Synthetic dissemination material for browser CI; never call an AI provider."""
import io
import json
import os
import secrets
import sys
import time
from pathlib import Path
if not os.getenv('DATABASE_URL', '').startswith('sqlite:') or os.getenv('FLASK_ENV') == 'production' or os.getenv('RENDER') == 'true':
    raise RuntimeError('Dissemination fixtures require isolated SQLite outside production')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PIL import Image
from app import app
from admin import admin_security_stamp
from models import db, Article, Author, Category, AdminUser
from dissemination_models import DisseminationMaterial
from dissemination_service import snapshot, add_version, save_asset
from dissemination_render import compose

with app.app_context():
    token=secrets.token_hex(6)
    account=AdminUser(username='dc-browser-'+token,display_name='Responsável de teste',password_hash='unused',
        is_superadmin=True,two_factor_enabled=True,totp_secret='JBSWY3DPEHPK3PXP')
    body='As plantas utilizam luz na fotossíntese. A resposta depende das condições ambientais.'
    article=Article(title='Fotossíntese para testes '+token,slug='dc-browser-'+token,summary=body,body=body,
        status='published',author_rel=Author.query.first(),category_rel=Category.query.first())
    db.session.add_all([article,account]);db.session.flush()
    item=DisseminationMaterial(source_kind='portal',source_id=article.id,network='instagram',kind='curiosity',
        status='review',token=secrets.token_urlsafe(24),created_by=account.id)
    db.session.add(item);db.session.flush()
    payload=dict(title='A luz e as plantas',caption='Material sintético para testar a interface.',
        slides=[dict(heading='A luz e as plantas',body='As plantas utilizam luz na fotossíntese.',claim_ids=[0])],
        claims=[dict(text='As plantas utilizam luz na fotossíntese.',evidence=body)],
        illustration='Imagem sintética de teste.',visual_label='Ilustração conceptual',layout='balanced',accent='teal')
    raw=io.BytesIO();Image.new('RGB',(1024,1024),'#c2d9cc').save(raw,format='PNG')
    assets=[dict(save_asset(raw.getvalue()),role='illustration')]
    assets.extend(dict(save_asset(image),role='slide') for image in compose(payload,'instagram',raw.getvalue(),app.static_folder))
    add_version(item,snapshot('portal',article.id),payload,dict(ready=True,issues=[],claim_checks=[dict(id=0,supported=True,reason='Dados sintéticos de teste.')]),assets)
    db.session.commit()
    cookie=app.session_interface.get_signing_serializer(app).dumps(dict(admin_authenticated=True,admin_id=account.id,
        admin_username=account.username,admin_superuser=True,admin_2fa_verified=True,admin_last_activity_at=time.time(),
        admin_security_stamp=admin_security_stamp(account),csrf_token='dc-browser-fixture'))
    print(json.dumps(dict(id=item.id,cookie=cookie)))
