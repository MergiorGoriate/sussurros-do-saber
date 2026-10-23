"""Synthetic scientific metrics for a guarded, isolated browser database only."""
import os
import sys
import json
import secrets
import time
from datetime import timedelta
from pathlib import Path
if not os.environ.get('DATABASE_URL','').startswith('sqlite:') or os.getenv('FLASK_ENV')=='production' or os.getenv('RENDER')=='true':
    raise RuntimeError('Scientific fixtures require isolated SQLite outside production')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app import app
from admin import admin_security_stamp
from models import db, Journal, AdminUser, utcnow
from scientific_metrics_models import ScientificMetricStart, ScientificMetricDay, ScientificMetricSource
with app.app_context():
    token=secrets.token_hex(6)
    admin=AdminUser(username='scientific-metrics-'+token,display_name='Gestor de teste',password_hash='unused',is_superadmin=True,two_factor_enabled=True,totp_secret='JBSWY3DPEHPK3PXP')
    journal=Journal(title='Revista científica de teste '+token,article_title='Artigo científico de teste '+token,slug='scientific-metrics-'+token,
        field='Biologia',description='Dados sintéticos para testes; não são estatísticas de produção.',published=True,
        content_markdown='## Métodos\n\nInvestigação científica de teste.',current_issue='Edição de teste '+token,
        publication_date=utcnow().date(),doi='10.9999/fixture-'+token,authors_data=json.dumps([{'name':'Autora Científica de Teste','orcid':'','description':''}]))
    counter=Journal(title=journal.title,article_title='Contagem de teste '+token,slug='scientific-counter-'+token,field='Biologia',description='Teste de contagem',published=True,content_markdown='## Texto\n\nAcesso aberto.',current_issue=journal.current_issue,publication_date=utcnow().date())
    db.session.add_all([admin,journal,counter]);db.session.flush()
    for j in [journal,counter]:db.session.add(ScientificMetricStart(journal_id=j.id,started_at=utcnow()-timedelta(days=40)))
    db.session.add_all([ScientificMetricDay(journal_id=journal.id,day=utcnow().date(),country='MZ',views=7,downloads=2),ScientificMetricDay(journal_id=journal.id,day=utcnow().date(),country='ZA',views=3,downloads=1)])
    for source,count in [('crossref',2),('openalex',4)]:db.session.add(ScientificMetricSource(journal_id=journal.id,source=source,doi=journal.doi,state='ok',citations=count,checked_at=utcnow(),measured_at=utcnow()))
    db.session.commit()
    cookie=app.session_interface.get_signing_serializer(app).dumps(dict(admin_authenticated=True,admin_id=admin.id,admin_superuser=True,admin_2fa_verified=True,admin_last_activity_at=time.time(),admin_security_stamp=admin_security_stamp(admin)))
    print(json.dumps(dict(slug=journal.slug,title=journal.article_title,id=journal.id,counter_slug=counter.slug,issue=journal.current_issue,admin_cookie=cookie)))
