"""Integration checks for live permissions, private documents and editorial state."""
import io
import secrets
import time
import unittest
from datetime import date, timedelta
from app import app
from admin import admin_security_stamp
from models import db, AdminUser, Author, Article, Category, Journal, utcnow
from governance import seed_roles
from governance_models import (TeamMember, TeamRole, TeamAppointment, StaffTask, StaffDocument, StaffNotice,
                               ArticleWorkflow, StaffPeerReview, GovernanceAudit, PortalReview)
from submission_models import Researcher, Manuscript, ManuscriptAuthor, ManuscriptVersion, ManuscriptFile

class StaffGovernanceTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True,RATELIMIT_ENABLED=False)
        self.ctx=app.app_context(); self.ctx.push()
        self.client=app.test_client()
        seed_roles()
        self.token=secrets.token_hex(6)
        self.primary=AdminUser(username='primary-'+self.token,display_name='Principal',password_hash='unused',is_superadmin=True,
                               two_factor_enabled=True,totp_secret='JBSWY3DPEHPK3PXP')
        self.journal=Journal(title='Ciência '+self.token,slug=self.token,field='Biologia',description='Revista de investigação científica.')
        self.other_journal=Journal(title='Outra '+self.token,slug='other-'+self.token,field='História',description='Outra revista científica.')
        self.category=Category(name='Área '+self.token,slug=self.token)
        db.session.add_all([self.primary,self.journal,self.other_journal,self.category]);db.session.commit()

    def tearDown(self):
        db.session.remove();self.ctx.pop()

    def member(self,code='author',scope=None,active=True):
        token=secrets.token_hex(6)
        account=AdminUser(username='staff-'+token,display_name='Membro '+token,email=token+'@example.org',password_hash='unused',
                          governance_managed=True,two_factor_enabled=True,totp_secret='JBSWY3DPEHPK3PXP')
        author=Author(name='Autor '+token,slug=token)
        member=TeamMember(admin=account,author=author,name='Membro '+token,email=token+'@example.org',status='active' if active else 'invited',
                          accepted_at=utcnow() if active else None)
        db.session.add(member);db.session.flush()
        role=TeamRole.query.filter_by(code=code).one()
        db.session.add(TeamAppointment(member=member,role=role,journal_id=scope,starts_on=date.today()-timedelta(days=1),ends_on=date.today()+timedelta(days=10)))
        db.session.commit()
        return member

    def signin(self,account):
        db.session.commit()
        stamp=admin_security_stamp(account)
        with self.client.session_transaction() as session:
            session.clear();session.update(admin_authenticated=True,admin_id=account.id,admin_username=account.username,
                admin_security_stamp=stamp,admin_last_activity_at=time.time(),admin_2fa_verified=True,admin_superuser=account.is_superadmin,csrf_token='test')

    def post(self,path,**data):
        return self.client.post(path,data={'csrf_token':'test',**data})

    def manuscript(self,editor=None,journal=None):
        owner=Researcher(name='Investigador',email='owner-'+secrets.token_hex(5)+'@example.org',password_hash='unused',verified=True,token_nonce=self.token)
        db.session.add(owner);db.session.flush()
        item=Manuscript(owner_id=owner.id,journal_id=(journal or self.journal).id,code='SDS-'+secrets.token_hex(6),
                        title='Estudo científico privado',summary='Resumo para avaliação científica',status='review',
                        submitted_at=utcnow(),current_version=1,editor_id=editor.admin_id if editor else None)
        db.session.add(item);db.session.flush()
        db.session.add(ManuscriptAuthor(manuscript_id=item.id,position=0,name=owner.name,email=owner.email,corresponding=True))
        version=ManuscriptVersion(manuscript_id=item.id,number=1,uploader_id=owner.id,snapshot={},finalized_at=utcnow())
        db.session.add(version);db.session.flush()
        file=ManuscriptFile(version_id=version.id,kind='main',original_name='privado.txt',internal_name=secrets.token_hex(12),mime='text/plain',size=8,sha256='a'*64,payload=b'SECRETO!')
        db.session.add(file);db.session.commit()
        return item,file

    def article(self,owner):
        item=Article(title='Artigo de divulgação',slug=secrets.token_hex(6),summary='Um resumo científico completo.',body='Texto científico fundamentado. '*10,
                     author_id=owner.author_id,category_id=self.category.id,status='draft')
        db.session.add(item);db.session.flush()
        db.session.add(ArticleWorkflow(article_id=item.id,owner_id=owner.id));db.session.commit()
        return item

    def test_management_pages_render_and_public_team_hides_pending(self):
        member=self.member(active=False)
        member.public_visible=member.public_consent=True;db.session.commit()
        self.signin(self.primary)
        for path in ['/admin/equipa','/admin/equipa?edit='+str(member.id),'/admin/funcoes','/admin/trabalho','/admin/documentos-equipa','/admin/notificacoes','/admin/relatorios-equipa']:
            response=self.client.get(path);self.assertEqual(response.status_code,200,path)
            self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertNotIn(member.name.encode(),self.client.get('/equipa').data)
        member.accepted_at=utcnow();member.status='active';db.session.commit()
        response=self.client.get('/equipa');self.assertIn(member.name.encode(),response.data);self.assertNotIn(member.email.encode(),response.data)
        member.public_consent=False;db.session.commit()
        self.assertNotIn(member.name.encode(),self.client.get('/equipa').data)

    def test_author_cannot_manage_roles_contacts_or_other_articles(self):
        owner=self.member();other=self.member();article=self.article(other)
        self.signin(owner.admin)
        for path in ['/admin/equipa','/admin/funcoes','/admin/contactos','/admin/subscritores','/admin/categorias','/admin/relatorios-equipa']:
            self.assertEqual(self.client.get(path).status_code,403,path)
        self.assertEqual(self.client.get(f'/admin/artigos/{article.id}/editar').status_code,404)
        self.assertNotIn(article.title.encode(),self.client.get('/admin/artigos').data)

    def test_suspension_and_expiry_revoke_existing_session(self):
        member=self.member('coordination');self.signin(member.admin)
        self.assertEqual(self.client.get('/admin/categorias').status_code,200)
        member.status='suspended';db.session.commit()
        self.assertEqual(self.client.get('/admin/categorias').status_code,403)
        member.status='active';member.appointments[0].ends_on=date.today()-timedelta(days=1);db.session.commit()
        self.assertEqual(self.client.get('/admin/categorias').status_code,403)

    def test_unlinked_managed_account_does_not_regain_legacy_permissions(self):
        member=self.member('coordination');account=member.admin
        self.signin(account);member.admin_id=None;db.session.commit()
        self.assertEqual(self.client.get('/admin/categorias').status_code,403)
        self.assertNotIn(b'Estudo cient',self.client.get('/admin/submissoes').data)

    def test_scoped_editor_cannot_read_other_journal_or_unassigned_manuscript(self):
        member=self.member('associate_editor',self.journal.id)
        own,file=self.manuscript(member);other,other_file=self.manuscript(member,self.other_journal);unassigned,_=self.manuscript()
        self.signin(member.admin)
        self.assertEqual(self.client.get(f'/admin/submissoes/{own.id}').status_code,200)
        for m in [other,unassigned]:self.assertEqual(self.client.get(f'/admin/submissoes/{m.id}').status_code,404)
        self.assertEqual(self.client.get(f'/submissoes/ficheiros/{file.id}').status_code,200)
        self.assertEqual(self.client.get(f'/submissoes/ficheiros/{other_file.id}').status_code,404)
        self.assertEqual(self.post(f'/admin/submissoes/{own.id}',action='accepted',note='Aceite sem autoridade').status_code,403)
        self.assertEqual(self.post(f'/admin/submissoes/{own.id}',action='revision_requested',note='Rever metodologia').status_code,302)

    def test_director_cannot_make_scientific_decisions(self):
        member=self.member('direction');item,_=self.manuscript();self.signin(member.admin)
        self.assertEqual(self.client.get(f'/admin/submissoes/{item.id}').status_code,404)
        self.assertEqual(self.post(f'/admin/submissoes/{item.id}',action='accepted',note='Aceitar').status_code,404)

    def test_review_files_require_acceptance_assignment_and_current_version(self):
        member=self.member('reviewer',self.journal.id);other=self.member('reviewer',self.journal.id)
        manuscript,file=self.manuscript()
        review=StaffPeerReview(manuscript_id=manuscript.id,reviewer_id=member.id,version_number=1,due_on=date.today())
        db.session.add(review);db.session.commit();self.signin(member.admin)
        path=f'/admin/pareceres/{review.id}'
        self.assertEqual(self.client.get(path).status_code,200)
        self.assertEqual(self.client.get(path+f'/ficheiros/{file.id}').status_code,404)
        self.assertEqual(self.client.get(f'/submissoes/ficheiros/{file.id}').status_code,404)
        self.assertEqual(self.post(path,action='accept').status_code,400)
        self.assertEqual(self.post(path,action='accept',no_conflict='on').status_code,302)
        self.assertEqual(self.client.get(path+f'/ficheiros/{file.id}').data,b'SECRETO!')
        self.signin(other.admin);self.assertEqual(self.client.get(path).status_code,404)
        self.signin(member.admin);manuscript.current_version=2;db.session.commit()
        self.assertEqual(self.client.get(path+f'/ficheiros/{file.id}').status_code,404)
        self.assertEqual(self.post(path,action='submit',recommendation='accept',report='Fundamentação científica. '*5).status_code,409)

    def test_conflict_revokes_review_access_after_acceptance(self):
        member=self.member('reviewer',self.journal.id);manuscript,file=self.manuscript()
        review=StaffPeerReview(manuscript_id=manuscript.id,reviewer_id=member.id,version_number=1,due_on=date.today(),status='accepted')
        db.session.add(review);db.session.commit();self.signin(member.admin)
        self.assertEqual(self.post(f'/admin/pareceres/{review.id}',action='conflict',conflict_note='Colaboração recente').status_code,302)
        self.assertEqual(self.client.get(f'/admin/pareceres/{review.id}/ficheiros/{file.id}').status_code,404)

    def test_assigning_author_as_reviewer_is_refused(self):
        member=self.member('reviewer',self.journal.id);manuscript,_=self.manuscript()
        manuscript.authors[0].email=member.email;db.session.commit();self.signin(self.primary)
        self.assertEqual(self.post('/admin/pareceres',manuscript_id=manuscript.id,reviewer_id=member.id,due_on=str(date.today())).status_code,400)
        self.assertEqual(StaffPeerReview.query.filter_by(manuscript_id=manuscript.id).count(),0)

    def test_peer_report_is_retained_and_does_not_accept_manuscript(self):
        member=self.member('reviewer',self.journal.id);manuscript,_=self.manuscript()
        review=StaffPeerReview(manuscript_id=manuscript.id,reviewer_id=member.id,version_number=1,due_on=date.today(),status='accepted')
        db.session.add(review);db.session.commit();self.signin(member.admin)
        report='Métodos adequados, dados verificáveis e resultados claros. '*5
        self.assertEqual(self.post(f'/admin/pareceres/{review.id}',action='submit',recommendation='accept',report=report).status_code,302)
        self.assertEqual(review.report,report.strip());self.assertEqual(manuscript.status,'review')
        self.signin(self.primary);response=self.client.get('/admin/pareceres?manuscript_id='+str(manuscript.id))
        self.assertEqual(response.status_code,200);self.assertIn(report.strip().encode(),response.data)

    def test_private_docs_allow_invited_member_to_accept_but_deny_other_member(self):
        member=self.member(active=False);other=self.member()
        document=StaffDocument(member_id=member.id,title='Termo privado',kind='agreement',body='Condições de colaboração',filename='termo.txt',payload=b'PRIVADO')
        db.session.add(document);db.session.commit();self.signin(other.admin)
        path=f'/admin/documentos-equipa/{document.id}'
        self.assertEqual(self.client.get(path+'/ficheiro').status_code,404)
        self.assertEqual(self.post(path+'/aceitar',confirm='on').status_code,404)
        self.signin(member.admin)
        self.assertIn(b'Termo privado',self.client.get('/admin/documentos-equipa').data)
        self.assertEqual(self.post(path+'/aceitar',confirm='on').status_code,302)
        self.assertIsNotNone(member.accepted_at);self.assertEqual(member.status,'invited')

    def test_validated_private_document_upload(self):
        member=self.member();self.signin(self.primary)
        response=self.post('/admin/documentos-equipa',member_id=member.id,title='Contrato',kind='agreement',file=(io.BytesIO(b'Contrato de colaboracao.'),'termo.txt'))
        self.assertEqual(response.status_code,302)
        document=StaffDocument.query.filter_by(member_id=member.id,title='Contrato').one()
        self.assertEqual(document.payload,b'Contrato de colaboracao.')
        self.assertEqual(self.post('/admin/documentos-equipa',member_id=member.id,title='Invalido',kind='agreement',file=(io.BytesIO(b'executable'),'run.exe')).status_code,400)

    def test_task_and_notification_ids_are_private_and_csrf_is_required(self):
        member=self.member();other=self.member()
        task=StaffTask(title='Tarefa privada',assignee_id=other.id,due_on=date.today())
        notice=StaffNotice(admin_id=other.admin_id,subject='Privada')
        db.session.add_all([task,notice]);db.session.commit();self.signin(member.admin)
        self.assertEqual(self.post('/admin/trabalho',id=task.id,status='done').status_code,403)
        self.assertEqual(self.post('/admin/notificacoes',id=notice.id).status_code,404)
        self.assertEqual(self.client.post('/admin/trabalho',data={'id':task.id,'status':'done'}).status_code,400)
        self.signin(other.admin);self.assertEqual(self.post('/admin/trabalho',id=task.id,status='done',comment='Concluído').status_code,302)
        self.assertEqual(task.comments[0].body,'Concluído')

    def test_article_requires_independent_review_and_approval(self):
        owner=self.member();reviewer=self.member('portal_reviewer');editor=self.member('portal_editor')
        article=self.article(owner);path=f'/admin/fluxo-artigos/{article.id}'
        self.signin(owner.admin);self.assertEqual(self.client.get(path).status_code,200)
        self.assertEqual(self.post(path,action='submit').status_code,302)
        self.signin(editor.admin);self.assertEqual(self.post(path,action='assign',reviewer_id=owner.id).status_code,400)
        self.assertEqual(self.post(path,action='assign',reviewer_id=reviewer.id).status_code,302)
        self.assertEqual(self.post(path,action='approve').status_code,409)
        self.signin(reviewer.admin);note='Fontes verificadas. Texto científico rigoroso.'
        self.assertEqual(self.post(path,action='reviewed',note=note).status_code,302)
        self.signin(editor.admin);self.assertEqual(self.post(path,action='approve').status_code,302)
        self.assertEqual(article.status,'approved');self.assertEqual(PortalReview.query.filter_by(article_id=article.id).one().report,note)
        self.signin(owner.admin);self.assertEqual(self.client.get(f'/admin/artigos/{article.id}/editar').status_code,409)

    def test_article_form_cannot_bypass_approval(self):
        member=self.member();article=self.article(member);self.signin(member.admin)
        response=self.post(f'/admin/artigos/{article.id}/editar',title=article.title,summary=article.summary,body=article.body,
                           author_id=member.author_id,category_id=self.category.id,status='published')
        self.assertEqual(response.status_code,409);self.assertEqual(article.status,'draft')

    def test_internal_due_reminders_are_idempotent(self):
        member=self.member();db.session.add(StaffTask(title='Prazo',assignee_id=member.id,due_on=date.today()));db.session.commit()
        runner=app.test_cli_runner()
        self.assertEqual(runner.invoke(args=['notificar-prazos-equipa']).exit_code,0)
        self.assertEqual(runner.invoke(args=['notificar-prazos-equipa']).exit_code,0)
        self.assertEqual(StaffNotice.query.filter(StaffNotice.admin_id==member.admin_id,StaffNotice.source_key.isnot(None)).count(),1)

    def test_scientific_editor_scope_filters_journal_list_and_configuration(self):
        member=self.member('chief_editor',self.journal.id);self.signin(member.admin)
        response=self.client.get('/admin/revistas')
        self.assertEqual(response.status_code,200);self.assertIn(self.journal.title.encode(),response.data)
        self.assertNotIn(self.other_journal.title.encode(),response.data)
        self.assertEqual(self.client.get('/admin/submissoes/configuracao?journal_id='+str(self.journal.id)).status_code,200)
        self.assertEqual(self.client.get('/admin/submissoes/configuracao?journal_id='+str(self.other_journal.id)).status_code,403)
        self.assertEqual(self.client.get('/admin/revistas/'+str(self.other_journal.id)+'/previsualizar').status_code,403)

    def test_publication_role_cannot_reopen_or_modify_approved_content(self):
        owner=self.member();publisher=self.member('publisher');article=self.article(owner)
        item=db.session.get(ArticleWorkflow,article.id);item.stage='approved';item.approved_at=utcnow();article.status='approved';db.session.commit()
        self.signin(publisher.admin)
        data=dict(title=article.title,summary=article.summary,body=article.body,author_id=owner.author_id,category_id=self.category.id)
        self.assertEqual(self.post(f'/admin/artigos/{article.id}/editar',**data,status='draft').status_code,403)
        data['body']='Conteúdo alterado sem revisão. '*10
        self.assertEqual(self.post(f'/admin/artigos/{article.id}/editar',**data,status='published').status_code,403)
        data['body']=article.body
        self.assertEqual(self.post(f'/admin/fluxo-artigos/{article.id}',action='publish').status_code,302)
        self.assertEqual(article.status,'published')

    def test_director_cannot_rebind_editor_account_to_gain_scientific_role(self):
        director=self.member('direction');editor=self.member('chief_editor');self.signin(director.admin)
        response=self.post('/admin/equipa',id=editor.id,name=editor.name,email=editor.email,status='active',group='scientific',
                           admin_id=director.admin_id,author_id=editor.author_id)
        self.assertIn(response.status_code,[400,403]);self.assertEqual(editor.admin_id,editor.admin.id)

    def test_review_and_approval_cannot_be_done_by_same_member(self):
        owner=self.member();reviewer=self.member('portal_reviewer');article=self.article(owner)
        db.session.add(TeamAppointment(member=reviewer,role=TeamRole.query.filter_by(code='portal_editor').one(),starts_on=date.today()))
        item=db.session.get(ArticleWorkflow,article.id);item.stage='review';item.reviewed_at=utcnow();item.reviewer_id=reviewer.id;db.session.commit()
        self.signin(reviewer.admin)
        self.assertEqual(self.post(f'/admin/fluxo-artigos/{article.id}',action='approve').status_code,403)
        self.assertIsNone(item.approved_at)
