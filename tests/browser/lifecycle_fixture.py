"""Generate isolated identities and disposable lifecycle resources for Playwright."""
import json, sys, time, secrets
from datetime import date
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app import app
from admin import admin_security_stamp
from models import db, AdminUser, Journal, utcnow
from governance_models import TeamMember, TeamRole, TeamAppointment, StaffDocument, StaffTask, AuditReport
from submission_models import Researcher, Manuscript
from internal_notices import emit
with app.app_context():
    suffix=secrets.token_hex(6)
    founder=AdminUser(username='lifecycle-founder-'+suffix,display_name='Fundador isolado',password_hash='unused',is_superadmin=True,two_factor_enabled=True,totp_secret='JBSWY3DPEHPK3PXP')
    account=AdminUser(username='lifecycle-member-'+suffix,display_name='Colaborador isolado',password_hash='unused',governance_managed=True,two_factor_enabled=True,totp_secret='JBSWY3DPEHPK3PXP')
    replacement=AdminUser(username='lifecycle-new-'+suffix,display_name='Substituto isolado',password_hash='unused',governance_managed=True,two_factor_enabled=True,totp_secret='JBSWY3DPEHPK3PXP')
    member=TeamMember(admin=account,name='Colaborador '+suffix,email=suffix+'@example.org',status='active',accepted_at=utcnow())
    target=TeamMember(admin=replacement,name='Substituto '+suffix,email='new-'+suffix+'@example.org',status='active',accepted_at=utcnow())
    journal=Journal(title='Revista isolada '+suffix,slug='lifecycle-'+suffix,description='Fixture',field='Biologia')
    owner=Researcher(name='Autor isolado',email='owner-'+suffix+'@example.org',password_hash='unused',verified=True,token_nonce=suffix)
    db.session.add_all([founder,member,target,journal,owner]);db.session.flush()
    role=TeamRole.query.filter_by(code='secretariat').one()
    for m in [member,target]:db.session.add(TeamAppointment(member=m,role=role,starts_on=date.today()))
    doc=StaffDocument(member=member,title='Termo '+suffix,body='Versão documental isolada',kind='other',accepted_at=utcnow(),accepted_by=account.id)
    report=AuditReport(title='Relatório '+suffix,snapshot=[])
    manuscript=Manuscript(owner_id=owner.id,journal_id=journal.id,title='Submissão '+suffix,code='LIFECYCLE-'+suffix,status='review',submitted_at=utcnow())
    task=StaffTask(title='Responsabilidade '+suffix,assignee=member,status='pending',due_on=date.today())
    db.session.add_all([doc,report,manuscript,task]);db.session.flush()
    emit(account.id,'Primeiro aviso '+suffix,key='browser-first-'+suffix,resource=('task',task.id))
    emit(account.id,'Segundo aviso '+suffix,key='browser-second-'+suffix,resource=('document',doc.id))
    db.session.commit()
    def cookie(a):
        return app.session_interface.get_signing_serializer(app).dumps(dict(admin_authenticated=True,admin_id=a.id,admin_username=a.username,admin_superuser=a.is_superadmin,admin_last_activity_at=time.time(),admin_2fa_verified=True,admin_security_stamp=admin_security_stamp(a),csrf_token='lifecycle'))
    print(json.dumps(dict(cookie=cookie(account),founder_cookie=cookie(founder),member_id=member.id,target_id=target.id,document_id=doc.id,report_id=report.id,manuscript_id=manuscript.id,task_id=task.id,suffix=suffix)))
