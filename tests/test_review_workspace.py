"""Private review workspace: real grants, assignments and lifecycle transitions."""
import unittest
from datetime import date,timedelta
import test_staff_governance as fixtures
from models import db,utcnow
from governance_models import StaffPeerReview,StaffNotice,ArticleWorkflow

class ReviewWorkspaceTests(unittest.TestCase):
    setUp=fixtures.StaffGovernanceTests.setUp
    tearDown=fixtures.StaffGovernanceTests.tearDown
    member=fixtures.StaffGovernanceTests.member
    signin=fixtures.StaffGovernanceTests.signin
    post=fixtures.StaffGovernanceTests.post
    manuscript=fixtures.StaffGovernanceTests.manuscript
    article=fixtures.StaffGovernanceTests.article

    def peer(self,member,manuscript,status='invited'):
        item=StaffPeerReview(manuscript_id=manuscript.id,reviewer_id=member.id,version_number=1,
                             due_on=date.today()-timedelta(days=1),status=status)
        db.session.add(item);db.session.commit();return item

    def test_founder_can_manage_without_a_personal_member_and_choose_own_view(self):
        reviewer=self.member('reviewer',self.journal.id);m,_=self.manuscript();self.peer(reviewer,m)
        self.signin(self.primary)
        page=self.client.get('/admin/pareceres');self.assertEqual(page.status_code,200)
        self.assertIn(b'Gest\xc3\xa3o de pareceres',page.data);self.assertIn(m.code.encode(),page.data)
        own=self.client.get('/admin/pareceres?view=mine');self.assertEqual(own.status_code,200)
        self.assertNotIn(m.code.encode(),own.data);self.assertIn(b'Ainda n',own.data)

    def test_manager_overview_and_candidates_respect_journal_and_assigned_editor_scope(self):
        editor=self.member('chief_editor',self.journal.id);reviewer=self.member('reviewer')
        m,_=self.manuscript();other,_=self.manuscript(journal=self.other_journal)
        self.peer(reviewer,m);self.peer(reviewer,other);self.signin(editor.admin)
        page=self.client.get('/admin/pareceres');self.assertEqual(page.status_code,200)
        self.assertIn(m.code.encode(),page.data);self.assertNotIn(other.code.encode(),page.data)
        self.assertEqual(self.client.get('/admin/pareceres?manuscript_id='+str(other.id)).status_code,403)
        self.assertEqual(self.post('/admin/pareceres',manuscript_id=other.id,reviewer_id=reviewer.id,due_on=str(date.today())).status_code,403)
        associate=self.member('associate_editor',self.journal.id)
        m.editor_id=associate.admin_id;db.session.commit();self.signin(associate.admin)
        self.assertIn(m.code.encode(),self.client.get('/admin/pareceres').data)
        m.editor_id=None;db.session.commit()
        self.assertNotIn(m.code.encode(),self.client.get('/admin/pareceres').data)

    def test_personal_filters_do_not_expose_other_reviewers_or_management(self):
        reviewer=self.member('reviewer',self.journal.id);other=self.member('reviewer',self.journal.id)
        m,_=self.manuscript();private,_=self.manuscript();self.peer(reviewer,m,'accepted');self.peer(other,private)
        self.signin(reviewer.admin)
        page=self.client.get('/admin/pareceres?estado=overdue');self.assertEqual(page.status_code,200)
        self.assertIn(m.code.encode(),page.data);self.assertNotIn(private.code.encode(),page.data)
        self.assertNotIn(m.code.encode(),self.client.get('/admin/pareceres?estado=submitted').data)
        self.assertEqual(self.client.get('/admin/pareceres?view=manage').status_code,403)
        self.assertEqual(self.client.get('/admin/pareceres?estado=invalid').status_code,400)
        reviewer.appointments[0].active=False;db.session.commit()
        self.assertEqual(self.client.get('/admin/pareceres').status_code,403)

    def test_closed_reviews_offer_no_unusable_actions_or_downloads(self):
        reviewer=self.member('reviewer',self.journal.id);m,f=self.manuscript();r=self.peer(reviewer,m,'accepted')
        self.signin(reviewer.admin);m.status='accepted';db.session.commit();path=f'/admin/pareceres/{r.id}'
        page=self.client.get(path);self.assertEqual(page.status_code,200)
        self.assertNotIn(b'Entregar parecer</button>',page.data)
        self.assertNotIn(f'/ficheiros/{f.id}'.encode(),page.data)
        self.assertEqual(self.client.get(path+f'/ficheiros/{f.id}').status_code,404)
        self.assertEqual(self.post(path,action='submit',report='Parecer fundamentado. '*5,recommendation='accept').status_code,409)
        r.status='submitted';r.report='Parecer anterior preservado.';r.recommendation='minor_revision';m.current_version=2;db.session.commit()
        page=self.client.get(path);self.assertIn(r.report.encode(),page.data)

    def test_accepted_review_can_declare_conflict_and_revoke_file_access(self):
        reviewer=self.member('reviewer',self.journal.id);m,f=self.manuscript();r=self.peer(reviewer,m,'accepted')
        self.signin(reviewer.admin);path=f'/admin/pareceres/{r.id}'
        self.assertIn(b'Declarar conflito</button>',self.client.get(path).data)
        self.assertEqual(self.post(path,action='conflict',conflict_note='Colabora\u00e7\u00e3o recente com os autores.').status_code,302)
        self.assertEqual(r.status,'conflict');self.assertTrue(r.conflict_declared)
        self.assertEqual(self.client.get(path+f'/ficheiros/{f.id}').status_code,404)
        self.assertEqual(m.status,'review')

    def test_portal_reviews_have_a_separate_queue_and_follow_live_permissions(self):
        owner=self.member();reviewer=self.member('portal_reviewer');other=self.member('portal_reviewer')
        a=self.article(owner);private=self.article(owner)
        flow=db.session.get(ArticleWorkflow,a.id);flow.reviewer_id=reviewer.id;flow.stage='review'
        otherflow=db.session.get(ArticleWorkflow,private.id);otherflow.reviewer_id=other.id;otherflow.stage='review'
        db.session.commit();self.signin(reviewer.admin)
        page=self.client.get('/admin/pareceres');self.assertEqual(page.status_code,200)
        self.assertIn(f'/admin/fluxo-artigos/{a.id}'.encode(),page.data)
        self.assertNotIn(f'/admin/fluxo-artigos/{private.id}'.encode(),page.data)
        self.assertIn(b'Meus pareceres',page.data)
        reviewer.appointments[0].active=False;db.session.commit()
        self.assertEqual(self.client.get('/admin/pareceres').status_code,403)

    def test_invalid_report_does_not_change_review_or_recommendation(self):
        reviewer=self.member('reviewer',self.journal.id);m,_=self.manuscript();r=self.peer(reviewer,m,'accepted')
        self.signin(reviewer.admin)
        self.assertEqual(self.post(f'/admin/pareceres/{r.id}',action='submit',report='Curto',recommendation='bad').status_code,400)
        self.assertEqual(r.status,'accepted');self.assertEqual(r.report,'');self.assertEqual(r.recommendation,'')

    def test_assignment_acceptance_download_delivery_and_manager_consultation(self):
        editor=self.member('chief_editor',self.journal.id);reviewer=self.member('reviewer',self.journal.id)
        m,f=self.manuscript(editor);self.signin(editor.admin)
        self.assertEqual(self.post('/admin/pareceres',manuscript_id=m.id,reviewer_id=reviewer.id,due_on=str(date.today())).status_code,302)
        r=StaffPeerReview.query.filter_by(manuscript_id=m.id,reviewer_id=reviewer.id).one()
        self.assertIsNotNone(StaffNotice.query.filter_by(admin_id=reviewer.admin_id,resource_type='manuscript',resource_id=m.id).first())
        from bs4 import BeautifulSoup
        page=BeautifulSoup(self.client.get('/admin/pareceres?manuscript_id='+str(m.id)).data,'html.parser')
        self.assertIsNone(page.select_one(f'select[name=reviewer_id] option[value="{reviewer.id}"]'))
        self.signin(reviewer.admin);path=f'/admin/pareceres/{r.id}'
        self.assertEqual(self.post(path,action='accept',no_conflict='on').status_code,302)
        self.assertEqual(self.client.get(path+f'/ficheiros/{f.id}').data,b'SECRETO!')
        report='Metodologia verific\u00e1vel, resultados coerentes e limita\u00e7\u00f5es explicitadas. '*3
        self.assertEqual(self.post(path,action='submit',report=report,recommendation='minor_revision').status_code,302)
        self.assertEqual(r.status,'submitted');self.assertEqual(m.status,'review')
        self.signin(editor.admin);self.assertIn(report.strip().encode(),self.client.get('/admin/pareceres').data)
