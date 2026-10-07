"""Isolated browser identities. Never loaded by application routes."""
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app import app
from admin import admin_security_stamp
from models import db, AdminUser, Author, Category, Journal, utcnow
from governance_models import TeamMember, TeamRole, TeamAppointment
from submission_models import Researcher, Manuscript, ManuscriptAuthor
with app.app_context():
    account=AdminUser.query.filter_by(username='browser-permissions-secretariat').first()
    if not account:
        account=AdminUser(username='browser-permissions-secretariat',display_name='Secretariado de teste',password_hash='synthetic-fixture',email='browser-secretariat@example.org',governance_managed=True,two_factor_enabled=True,totp_secret='JBSWY3DPEHPK3PXP')
        author=Author(name='Autor de teste de permissões',slug='browser-permissions-author')
        role=TeamRole(code='browser_permissions',name='Secretariado — teste isolado',permissions=[])
        member=TeamMember(admin=account,author=author,name='Secretariado de teste',email=account.email,status='active',accepted_at=utcnow())
        db.session.add_all([member,role]);db.session.flush()
        db.session.add(TeamAppointment(member=member,role=role,starts_on=date.today()))
        if not Category.query.first():db.session.add(Category(name='Categoria de teste',slug='browser-permissions'))
        journal=Journal(title='Revista de teste de permissões',slug='browser-permissions-journal',field='Biologia',description='Teste')
        owner=Researcher(name='Investigador sintético',email='browser-owner@example.org',password_hash='unused',verified=True,token_nonce='browser')
        db.session.add_all([journal,owner]);db.session.flush()
        manuscript=Manuscript(code='BROWSER-PERMISSIONS',owner_id=owner.id,journal_id=journal.id,title='Submissão para testar atribuições',summary='Dados isolados.',status='review',submitted_at=utcnow(),current_version=1)
        db.session.add(manuscript);db.session.flush();db.session.add(ManuscriptAuthor(manuscript_id=manuscript.id,position=0,name=owner.name,email=owner.email,corresponding=True))
    member=TeamMember.query.filter_by(admin_id=account.id).first()
    role=TeamRole.query.filter_by(code='browser_permissions').one()
    role.permissions=[] if len(sys.argv)>1 and sys.argv[1]=='revoke' else ['tasks.manage','article.write','reports.read','contacts.manage','manuscript.assign']
    db.session.commit()
    cookie=app.session_interface.get_signing_serializer(app).dumps(dict(admin_authenticated=True,admin_id=account.id,admin_username=account.username,admin_superuser=False,admin_last_activity_at=time.time(),admin_2fa_verified=True,admin_security_stamp=admin_security_stamp(account),csrf_token='browser-permissions'))
    print(json.dumps({'cookie':cookie,'member_id':member.id}))
