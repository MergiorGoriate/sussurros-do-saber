"""Disposable review identities and manuscripts for browser checks (SQLite only)."""
import os,sys,json,time
from pathlib import Path
from datetime import date,timedelta
if not os.environ.get('DATABASE_URL','').startswith('sqlite:'):
    raise RuntimeError('Review browser fixtures require isolated SQLite')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_staff_governance import StaffGovernanceTests
from app import app
from admin import admin_security_stamp
from models import db,utcnow
from governance_models import StaffPeerReview,TeamRole,TeamAppointment,ArticleWorkflow
case=StaffGovernanceTests();case.setUp()
reviewer=case.member('reviewer',case.journal.id);editor=case.member('chief_editor',case.journal.id)
portal_role=TeamRole.query.filter_by(code='portal_reviewer').one()
db.session.add(TeamAppointment(member=reviewer,role=portal_role,starts_on=date.today()))
m,f=case.manuscript(editor);m.title='Avaliação científica de demonstração'
other,of=case.manuscript(editor);other.title='Estudo para declaração de conflito'
accepted=StaffPeerReview(manuscript_id=other.id,reviewer_id=reviewer.id,version_number=1,due_on=date.today(),status='accepted')
db.session.add(accepted)
if len(sys.argv)>1 and sys.argv[1]=='layout':
 db.session.add(StaffPeerReview(manuscript_id=m.id,reviewer_id=reviewer.id,version_number=1,due_on=date.today()-timedelta(days=2)))
owner=case.member();a=case.article(owner);a.title='Revisão de divulgação científica: fontes e explicação'
flow=db.session.get(ArticleWorkflow,a.id);flow.stage='review';flow.reviewer_id=reviewer.id
reviewer.name='Revisor científico de demonstração';db.session.commit()
def cookie(account):
 return app.session_interface.get_signing_serializer(app).dumps(dict(admin_authenticated=True,admin_id=account.id,admin_username=account.username,admin_superuser=account.is_superadmin,admin_last_activity_at=time.time(),admin_2fa_verified=True,admin_security_stamp=admin_security_stamp(account),csrf_token='review-browser-fixture'))
print(json.dumps(dict(founder=cookie(case.primary),reviewer=cookie(reviewer.admin),member_id=reviewer.id,manuscript_id=m.id,code=m.code,file_id=f.id,conflict_id=accepted.id,conflict_file_id=of.id,article_id=a.id,due_on=date.today().isoformat())))
