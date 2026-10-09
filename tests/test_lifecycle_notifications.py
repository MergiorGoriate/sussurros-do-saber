"""Synthetic data only: lifecycle operations, sessions, inbox ownership and delivery."""
import unittest
import secrets
from datetime import date, timedelta
import test_staff_governance as fixtures
from app import app
from models import db, utcnow, AdminUser
from governance_models import StaffDocument, StaffNotice, StaffTask, StaffPeerReview, GovernanceAudit, AuditReport, TeamRole, TeamAppointment, ArticleWorkflow
from submission_models import ManuscriptVersion, EditorialEvent
from internal_notices import emit, dispatch

class LifecycleNotificationTests(unittest.TestCase):
    setUp=fixtures.StaffGovernanceTests.setUp
    tearDown=fixtures.StaffGovernanceTests.tearDown
    member=fixtures.StaffGovernanceTests.member
    signin=fixtures.StaffGovernanceTests.signin
    post=fixtures.StaffGovernanceTests.post
    manuscript=fixtures.StaffGovernanceTests.manuscript
    article=fixtures.StaffGovernanceTests.article

    def remove(self,kind,item):
        return self.post(f'/admin/remover/{kind}/{item.id}',confirm='yes')

    def document(self,member,payload=None):
        d=StaffDocument(member=member,title='Documento '+self.token,body='Versão documental original',payload=payload,filename='termo.txt' if payload else '',accepted_at=utcnow(),accepted_by=member.admin_id)
        db.session.add(d);db.session.commit();return d

    def notices(self,member,kind=None,ident=None):
        query=StaffNotice.query.filter_by(admin_id=member.admin_id,researcher_id=None)
        if kind:query=query.filter_by(resource_type=kind,resource_id=ident)
        return query.all()

    def test_all_four_actions_founder_only_confirmation_cancel_and_idempotence(self):
        member=self.member('direction');m,f=self.manuscript();d=self.document(member)
        report=AuditReport(title='Relatório isolado',snapshot=[]);db.session.add(report);db.session.commit()
        items=[('manuscript',m),('document',d),('report',report),('member',member)]
        for role in ['direction','coordination','secretariat','chief_editor','production','publisher']:
            outsider=self.member(role);self.signin(outsider.admin)
            for kind,item in items:
                with self.subTest(role=role,kind=kind):
                    url=f'/admin/remover/{kind}/{item.id}'
                    self.assertEqual(self.client.get(url).status_code,403)
                    self.assertEqual(self.post(url,confirm='yes').status_code,403)
                    self.assertIsNone(item.removed_at)
        self.signin(self.primary)
        for kind,item in items:
            url=f'/admin/remover/{kind}/{item.id}'
            body=self.client.get(url).data
            self.assertIn(b'Cancelar',body);self.assertIn(b'Confirmar remo',body)
            self.assertIsNone(item.removed_at) # GET and cancellation never mutate.
            self.assertEqual(self.post(url).status_code,400)
            self.assertEqual(self.client.post(url,data={'confirm':'yes'}).status_code,400)
            self.assertEqual(self.remove(kind,item).status_code,303)
            count=GovernanceAudit.query.filter_by(action=kind+'.removed',entity_id=item.id).count()
            self.assertEqual(self.remove(kind,item).status_code,303)
            self.assertEqual(GovernanceAudit.query.filter_by(action=kind+'.removed',entity_id=item.id).count(),count)
            self.assertIsNotNone(item.removed_at)
        self.assertEqual(self.client.get('/admin/historico-remocoes').status_code,200)

    def test_deleted_submission_preserves_files_reviews_decisions_publication_and_blocks_routes(self):
        editor=self.member('chief_editor',self.journal.id);reviewer=self.member('reviewer',self.journal.id)
        m,f=self.manuscript(editor);m.publication_id=self.other_journal.id;self.other_journal.published=True
        review=StaffPeerReview(manuscript_id=m.id,reviewer_id=reviewer.id,version_number=1,due_on=date.today(),status='submitted',report='Parecer preservado')
        decision=EditorialEvent(manuscript_id=m.id,previous_status='review',new_status='accepted',action='decision',actor='isolado',note='Decisão preservada')
        db.session.add_all([review,decision]);db.session.commit();self.signin(self.primary);self.remove('manuscript',m)
        self.assertEqual(m.publication_id,self.other_journal.id);self.assertTrue(self.other_journal.published)
        self.assertEqual(ManuscriptVersion.query.filter_by(manuscript_id=m.id).count(),1)
        self.assertEqual(f.payload,b'SECRETO!');self.assertEqual(review.report,'Parecer preservado');self.assertEqual(decision.note,'Decisão preservada')
        self.assertEqual(self.client.get(f'/admin/historico-submissoes/{m.id}').status_code,200)
        self.assertEqual(self.client.get(f'/submissoes/ficheiros/{f.id}').status_code,200)
        for account in [editor.admin,reviewer.admin]:
            self.signin(account)
            self.assertEqual(self.client.get(f'/submissoes/ficheiros/{f.id}').status_code,410)
            self.assertNotIn(f'href="/admin/submissoes/{m.id}"'.encode(),self.client.get('/admin/submissoes').data if account==editor.admin else b'')
        self.signin(editor.admin)
        self.assertEqual(self.post(f'/admin/submissoes/{m.id}',action='accepted',note='Decisão').status_code,404)
        self.assertEqual(self.post(f'/admin/submissoes/{m.id}/preparar').status_code,403)
        self.signin(reviewer.admin);self.assertEqual(self.post(f'/admin/pareceres/{review.id}',action='submit').status_code,410)

    def test_remove_member_blocks_already_open_session_and_preserves_public_authorship(self):
        member=self.member('secretariat');a=self.article(member);doc=self.document(member)
        self.signin(member.admin);cookie=self.client.get_cookie('session').value
        self.signin(self.primary);self.assertEqual(self.remove('member',member).status_code,303)
        self.assertFalse(member.admin.active);self.assertFalse(any(a.active for a in member.appointments));self.assertEqual(member.status,'ended')
        self.assertIsNotNone(a.author_id);self.assertIsNotNone(doc.accepted_at);self.assertIsNotNone(db.session.get(AdminUser,member.admin_id))
        other=app.test_client();other.set_cookie('session',cookie)
        self.assertEqual(other.get('/admin/trabalho').status_code,302)
        self.assertEqual(other.get('/admin/api/notificacoes').status_code,401)
        self.assertEqual(self.post(f'/admin/equipa/{member.id}/mandatos',role_id=member.appointments[0].role_id,starts_on=str(date.today())).status_code,409)

    def test_founder_cannot_be_removed(self):
        member=self.member();member.admin_id=self.primary.id;db.session.commit();self.signin(self.primary)
        self.assertEqual(self.remove('member',member).status_code,403);self.assertIsNone(member.removed_at);self.assertTrue(self.primary.active)

    def test_document_with_and_without_attachment_archives_version_and_acceptance(self):
        member=self.member();self.signin(self.primary)
        for payload in [None,b'Termo privado']:
            d=self.document(member,payload);accepted=d.accepted_at
            self.remove('document',d)
            self.assertEqual(d.body,'Versão documental original');self.assertEqual(d.payload,payload);self.assertEqual(d.accepted_at,accepted)
            self.assertNotIn(f'id="documento-{d.id}"'.encode(),self.client.get('/admin/documentos-equipa').data)
            self.assertIn(d.title.encode(),self.client.get('/admin/documentos-equipa?history=1').data)
            if payload:self.assertEqual(self.client.get(f'/admin/documentos-equipa/{d.id}/ficheiro').status_code,200)
            self.signin(member.admin);self.assertEqual(self.post(f'/admin/documentos-equipa/{d.id}/aceitar',confirm='on').status_code,410)
            self.assertEqual(self.client.get(f'/admin/documentos-equipa/{d.id}/ficheiro').status_code,410);self.signin(self.primary)

    def test_report_generation_snapshot_and_removal_preserve_source_events(self):
        self.signin(self.primary)
        from governance import audit
        with app.test_request_context('/admin/test'):
            audit('test.event','test',123,'Histórico isolado');db.session.commit()
        self.assertEqual(self.post('/admin/relatorios-equipa/guardar',title='Relatório '+self.token).status_code,303)
        report=AuditReport.query.filter_by(title='Relatório '+self.token).one();snapshot=report.snapshot
        self.assertTrue(any(e['entity_id']==123 for e in snapshot));ids=[e['id'] for e in snapshot]
        self.remove('report',report);self.assertEqual(report.snapshot,snapshot)
        self.assertEqual(GovernanceAudit.query.filter(GovernanceAudit.id.in_(ids)).count(),len(ids))
        reader=self.member('direction');self.signin(reader.admin);self.assertEqual(self.client.get(f'/admin/relatorios-equipa/{report.id}').status_code,410)

    def test_reassignment_validates_scopes_preserves_old_peer_review(self):
        old=self.member('associate_editor',self.journal.id);new=self.member('associate_editor',self.journal.id);wrong=self.member('associate_editor',self.other_journal.id)
        m,f=self.manuscript(old);task=StaffTask(title='Pendente',assignee=old,status='in_progress');db.session.add(task);db.session.commit()
        reviewer=self.member('reviewer',self.journal.id);newreviewer=self.member('reviewer',self.journal.id)
        peer=StaffPeerReview(manuscript_id=m.id,reviewer_id=reviewer.id,version_number=1,due_on=date.today(),status='accepted');db.session.add(peer);db.session.commit()
        self.signin(self.primary);self.remove('member',old)
        path=f'/admin/equipa/{old.id}/responsabilidades'
        self.assertIn(b'Pendente',self.client.get(path).data)
        self.assertEqual(self.post(path,kind='editor',resource_id=m.id,target_id=wrong.id).status_code,400)
        self.assertEqual(m.editor_id,old.admin_id)
        self.assertEqual(self.post(path,kind='editor',resource_id=m.id,target_id=new.id).status_code,303);self.assertEqual(m.editor_id,new.admin_id)
        self.assertEqual(self.post(path,kind='task',resource_id=task.id,target_id=new.id).status_code,303);self.assertEqual(task.assignee_id,new.id)
        self.remove('member',reviewer)
        self.assertEqual(self.post(f'/admin/equipa/{reviewer.id}/responsabilidades',kind='review',resource_id=peer.id,target_id=newreviewer.id).status_code,303)
        self.assertEqual(peer.status,'cancelled');self.assertEqual(peer.reviewer_id,reviewer.id)
        self.assertEqual(StaffPeerReview.query.filter_by(manuscript_id=m.id,reviewer_id=newreviewer.id).count(),1)

    def test_notification_ownership_read_delete_all_counter_persistence_and_repeat(self):
        member=self.member();other=self.member()
        emit(member.admin_id,'Aviso único',key='unique-'+self.token);emit(member.admin_id,'Duplicado',key='unique-'+self.token)
        emit(other.admin_id,'Outro destinatário',key='other-'+self.token);db.session.commit()
        own=self.notices(member)[0];foreign=self.notices(other)[0];self.signin(member.admin)
        self.assertEqual(self.client.get('/admin/api/notificacoes').json['unread'],1)
        for action in ['read','delete']:
            self.assertEqual(self.post('/admin/notificacoes',action=action,id=foreign.id).status_code,404)
        self.assertEqual(self.post('/admin/notificacoes',action='read',id=own.id).status_code,303)
        self.assertEqual(self.client.get('/admin/api/notificacoes').json['unread'],0)
        for _ in range(2):self.assertEqual(self.post('/admin/notificacoes',action='delete',id=own.id).status_code,303)
        self.signin(member.admin);self.assertNotIn(b'Aviso \xc3\xbanico',self.client.get('/admin/notificacoes').data)
        self.assertIsNotNone(own.removed_at);self.assertIsNone(foreign.removed_at);self.assertIsNone(foreign.read_at)
        emit(member.admin_id,'Não ressuscita',key='unique-'+self.token);db.session.commit();self.assertEqual(len(self.notices(member)),1)
        emit(member.admin_id,'Mais um');emit(member.admin_id,'Mais dois');db.session.commit()
        self.assertEqual(self.post('/admin/notificacoes',action='read_all').status_code,303)
        self.assertEqual(self.client.get('/admin/api/notificacoes').json['unread'],0)
        self.assertEqual(self.client.post('/admin/notificacoes',data={'action':'delete','id':foreign.id}).status_code,400)

    def test_task_assignment_comment_status_reassignment_deliver_and_noop_deduplicates(self):
        manager=self.member('secretariat');assignee=self.member();replacement=self.member();third=self.member()
        self.signin(manager.admin)
        self.post('/admin/trabalho',title='Tarefa '+self.token,assignee_id=assignee.id,due_on=str(date.today()))
        task=StaffTask.query.filter_by(title='Tarefa '+self.token).one()
        self.assertEqual(len(self.notices(assignee,'task',task.id)),1);self.assertEqual(len(self.notices(third,'task',task.id)),0)
        self.signin(assignee.admin);self.post('/admin/trabalho',id=task.id,status='in_progress',comment='Em curso')
        before=len(self.notices(assignee,'task',task.id));self.assertEqual(before,2)
        self.post('/admin/trabalho',id=task.id,status='in_progress',comment='Em curso');self.assertEqual(len(self.notices(assignee,'task',task.id)),before)
        self.signin(manager.admin);self.post('/admin/trabalho',id=task.id,status='in_progress',assignee_id=replacement.id)
        self.assertEqual(task.assignee_id,replacement.id);self.assertEqual(len(self.notices(replacement,'task',task.id)),1)

    def test_document_created_and_accept_notice_and_accept_repeat(self):
        manager=self.member('direction');member=self.member();self.signin(manager.admin)
        self.post('/admin/documentos-equipa',member_id=member.id,title='Termo '+self.token,kind='other',body='Versão 1')
        doc=StaffDocument.query.filter_by(title='Termo '+self.token).one();self.assertEqual(len(self.notices(member,'document',doc.id)),1)
        self.signin(member.admin);self.post(f'/admin/documentos-equipa/{doc.id}/aceitar',confirm='on')
        self.assertIsNotNone(doc.accepted_at);self.assertEqual(len(self.notices(manager,'document',doc.id)),1)
        count=len(self.notices(member,'document',doc.id));self.post(f'/admin/documentos-equipa/{doc.id}/aceitar',confirm='on');self.assertEqual(len(self.notices(member,'document',doc.id)),count)

    def test_editorial_events_scopes_inactive_expired_multiple_and_conflicts(self):
        editor=self.member('chief_editor',self.journal.id);wrong=self.member('chief_editor',self.other_journal.id)
        expired=self.member('chief_editor',self.journal.id);expired.appointments[0].ends_on=date.today()-timedelta(days=1)
        inactive=self.member('chief_editor',self.journal.id);inactive.admin.active=False
        multi=self.member('associate_editor',self.other_journal.id)
        role=TeamRole.query.filter_by(code='chief_editor').one();db.session.add(TeamAppointment(member=multi,role=role,journal_id=self.journal.id,starts_on=date.today()))
        m,f=self.manuscript(editor);db.session.commit()
        with app.test_request_context('/admin/test'):
            dispatch('manuscript.submitted','manuscript',m.id,key='submit-'+self.token);dispatch('manuscript.submitted','manuscript',m.id,key='submit-'+self.token);db.session.commit()
        for member in [editor,multi]:self.assertEqual(len(self.notices(member,'manuscript',m.id)),1)
        for member in [wrong,expired,inactive]:self.assertEqual(len(self.notices(member,'manuscript',m.id)),0)
        self.assertEqual(StaffNotice.query.filter_by(researcher_id=m.owner_id,resource_id=m.id).count(),1)
        self.signin(editor.admin);self.post(f'/admin/submissoes/{m.id}',action='accepted',note='Decisão fundamentada')
        self.assertEqual(m.status,'accepted');self.assertEqual(len(self.notices(editor,'manuscript',m.id)),2)
        count=len(self.notices(editor,'manuscript',m.id));self.post(f'/admin/submissoes/{m.id}',action='accepted',note='Decisão fundamentada');self.assertEqual(len(self.notices(editor,'manuscript',m.id)),count)

    def test_open_notice_revalidates_revoked_and_deleted_resources(self):
        editor=self.member('chief_editor',self.journal.id);m,f=self.manuscript(editor)
        emit(editor.admin_id,'Submissão',resource=('manuscript',m.id));db.session.commit();n=self.notices(editor)[0]
        self.signin(editor.admin);self.assertIn(f'/admin/submissoes/{m.id}',self.client.get(f'/admin/notificacoes/{n.id}/abrir').location)
        editor.appointments[0].active=False;db.session.commit()
        self.assertIn('/admin/notificacoes',self.client.get(f'/admin/notificacoes/{n.id}/abrir').location)
        editor.appointments[0].active=True;db.session.commit();self.signin(self.primary);self.remove('manuscript',m);self.signin(editor.admin)
        self.assertIn('/admin/notificacoes',self.client.get(f'/admin/notificacoes/{n.id}/abrir').location)

    def test_public_author_inbox_separate_from_admin_ownership(self):
        m,f=self.manuscript();other,of=self.manuscript();emit(None,'Aviso do autor',researcher_id=m.owner_id,resource=('manuscript',m.id));emit(None,'Privado do outro',researcher_id=other.owner_id);db.session.commit()
        n=StaffNotice.query.filter_by(researcher_id=m.owner_id).one();foreign=StaffNotice.query.filter_by(researcher_id=other.owner_id).one()
        with self.client.session_transaction() as s:s.clear();s.update(researcher_id=m.owner_id,researcher_nonce=m.owner.token_nonce,csrf_token='test')
        self.assertIn(b'Aviso do autor',self.client.get('/submissoes/notificacoes').data);self.assertNotIn(b'Privado do outro',self.client.get('/submissoes/notificacoes').data)
        self.assertEqual(self.post('/submissoes/notificacoes',action='delete',id=foreign.id).status_code,404)
        self.assertEqual(self.post('/submissoes/notificacoes',action='delete',id=n.id).status_code,303)
        self.assertIsNotNone(n.removed_at);self.assertIsNone(foreign.removed_at)

    def test_role_mandate_grants_revocation_notifications_and_no_duplicate_noop(self):
        member=self.member('secretariat');self.signin(self.primary)
        role=TeamRole.query.filter_by(code='secretariat').one();original=list(role.permissions)
        # Shared default catalogue restored at the end; only isolated permission is added.
        try:
            data=dict(id=role.id,name=role.name,purpose=role.purpose,duties=role.duties,limits=role.limits,permissions=original+['contacts.manage'])
            self.assertEqual(self.post('/admin/funcoes',**data).status_code,302)
            count=len(self.notices(member));self.assertGreater(count,0)
            self.post('/admin/funcoes',**data);self.assertEqual(len(self.notices(member)),count)
            self.signin(member.admin);self.assertEqual(self.client.get('/admin/contactos').status_code,200)
            self.signin(self.primary);self.post(f'/admin/mandatos/{member.appointments[0].id}/terminar')
            count=len(self.notices(member));self.post(f'/admin/mandatos/{member.appointments[0].id}/terminar');self.assertEqual(len(self.notices(member)),count)
            self.signin(member.admin);self.assertEqual(self.client.get('/admin/contactos').status_code,403)
        finally:role.permissions=original;db.session.commit()

    def test_portal_review_approval_publication_events_and_separation(self):
        owner=self.member();reviewer=self.member('portal_reviewer');editor=self.member('portal_editor');publisher=self.member('publisher')
        a=self.article(owner);flow=db.session.get(ArticleWorkflow,a.id);flow.stage='submitted';db.session.commit();path=f'/admin/fluxo-artigos/{a.id}'
        self.signin(editor.admin);self.assertEqual(self.post(path,action='assign',reviewer_id=reviewer.id).status_code,302)
        self.assertEqual(len(self.notices(reviewer,'article',a.id)),1)
        self.post(path,action='assign',reviewer_id=reviewer.id);self.assertEqual(len(self.notices(reviewer,'article',a.id)),1)
        self.signin(reviewer.admin);self.assertEqual(self.post(path,action='publish').status_code,403)
        self.assertEqual(self.post(path,action='reviewed',note='Parecer fundamentado. '*5).status_code,302)
        self.assertTrue(flow.reviewed_at)
        self.signin(editor.admin);self.assertEqual(self.post(path,action='approve').status_code,302);self.assertTrue(flow.approved_at)
        self.assertEqual(len(self.notices(publisher,'article',a.id)),1)
        self.assertEqual(self.post(path,action='publish').status_code,403)
        self.signin(publisher.admin);self.assertEqual(self.post(path,action='publish').status_code,302);self.assertEqual(a.status,'published')
        self.assertTrue(any('publicado' in n.body for n in self.notices(owner,'article',a.id)))
        count=len(self.notices(owner,'article',a.id));self.post(path,action='publish');self.assertEqual(len(self.notices(owner,'article',a.id)),count)

    def test_reviewer_assignment_accept_delivery_notifications_and_no_duplication(self):
        editor=self.member('chief_editor',self.journal.id);reviewer=self.member('reviewer',self.journal.id);wrong=self.member('reviewer',self.other_journal.id)
        m,f=self.manuscript(editor);self.signin(editor.admin)
        data=dict(manuscript_id=m.id,reviewer_id=reviewer.id,due_on=str(date.today()))
        self.assertEqual(self.post('/admin/pareceres',**data).status_code,302)
        peer=StaffPeerReview.query.filter_by(manuscript_id=m.id,reviewer_id=reviewer.id).one()
        self.assertEqual(len(self.notices(reviewer,'manuscript',m.id)),1);self.assertEqual(len(self.notices(wrong,'manuscript',m.id)),0)
        count=len(self.notices(reviewer,'manuscript',m.id));self.assertEqual(self.post('/admin/pareceres',**data).status_code,409);self.assertEqual(len(self.notices(reviewer,'manuscript',m.id)),count)
        self.signin(reviewer.admin);self.post(f'/admin/pareceres/{peer.id}',action='accept',no_conflict='on')
        self.assertEqual(self.post(f'/admin/pareceres/{peer.id}',action='submit',report='Parecer científico fundamentado. '*5,recommendation='accept').status_code,302)
        self.assertEqual(peer.status,'submitted');self.assertTrue(any('Parecer entregue' in n.body for n in self.notices(editor,'manuscript',m.id)))

    def test_notifications_rollback_and_same_event_distinct_recipients(self):
        member=self.member();other=self.member();key='transaction-'+self.token
        emit(member.admin_id,'Por confirmar',key=key);db.session.rollback();self.assertEqual(len(self.notices(member)),0)
        emit(member.admin_id,'Um evento',key=key);emit(other.admin_id,'Um evento',key=key);db.session.commit()
        self.assertEqual(len(self.notices(member)),1);self.assertEqual(len(self.notices(other)),1)
        self.signin(member.admin);self.post('/admin/notificacoes',action='delete',id=self.notices(member)[0].id);self.assertIsNone(self.notices(other)[0].removed_at)

    def test_summary_order_and_bar_page_same_data_after_read_delete(self):
        member=self.member();emit(member.admin_id,'Primeiro',key='first-'+self.token);emit(member.admin_id,'Segundo',key='second-'+self.token);db.session.commit();self.signin(member.admin)
        data=self.client.get('/admin/api/notificacoes').json;self.assertEqual([x['title'] for x in data['items']],['Segundo','Primeiro'])
        self.assertEqual(data['unread'],2)
        self.assertIn(b'Segundo',self.client.get('/admin/trabalho').data);self.assertIn(b'Segundo',self.client.get('/admin/notificacoes').data)
        ident=data['items'][0]['id'];self.post('/admin/notificacoes',id=ident,action='delete')
        self.assertEqual(self.client.get('/admin/api/notificacoes').json['unread'],1)
        self.assertNotIn(b'Segundo',self.client.get('/admin/notificacoes').data);self.assertNotIn(b'Segundo',self.client.get('/admin/trabalho').data)

    def test_draft_without_code_can_be_archived_and_cannot_be_submitted(self):
        member=self.member();m,f=self.manuscript();m.code=None;m.status='draft';db.session.commit()
        self.signin(self.primary);self.assertEqual(self.remove('manuscript',m).status_code,303)
        with self.client.session_transaction() as s:s.clear();s.update(researcher_id=m.owner_id,researcher_nonce=m.owner.token_nonce,csrf_token='test')
        self.assertEqual(self.post(f'/submissoes/{m.id}/confirmar',confirm='on').status_code,410)
        self.assertEqual(self.client.get(f'/submissoes/ficheiros/{f.id}').status_code,410)

    def test_scientific_preparation_publication_notices_and_publisher_destination(self):
        production=self.member('production',self.journal.id);publisher=self.member('publisher',self.journal.id);outsider=self.member('chief_editor',self.other_journal.id)
        role=TeamRole(code='scientific_publisher_'+self.token,name='Publicador científico de teste',permissions=['journal.publish'])
        db.session.add(role);publisher.appointments[0].role=role
        m,f=self.manuscript();m.status='accepted';db.session.commit();self.signin(production.admin)
        self.assertEqual(self.post(f'/admin/submissoes/{m.id}/preparar').status_code,302)
        self.assertEqual(len(self.notices(publisher,'manuscript',m.id)),1)
        self.assertEqual(StaffNotice.query.filter_by(researcher_id=m.owner_id,resource_id=m.id).count(),1)
        self.assertEqual(len(self.notices(outsider,'manuscript',m.id)),0)
        self.signin(publisher.admin)
        n=self.notices(publisher,'manuscript',m.id)[0]
        opened=self.client.get(f'/admin/notificacoes/{n.id}/abrir');self.assertIn(str(m.publication_id),opened.location)
        path=f'/admin/revistas/{m.publication_id}/publicacao';self.assertEqual(self.post(path).status_code,302);self.assertEqual(m.status,'published')
        self.assertEqual(len(self.notices(publisher,'manuscript',m.id)),2)
        self.assertEqual(StaffNotice.query.filter_by(researcher_id=m.owner_id,resource_id=m.id).count(),2)

    def test_existing_reader_bell_combines_internal_events_and_delete_keeps_following(self):
        from reader_accounts import ReaderJournal
        from datetime import datetime
        m,f=self.manuscript();account=m.owner
        self.journal.published=True
        row=ReaderJournal(owner_id=account.id,journal_id=self.journal.id,following=True,followed_at=datetime(2020,1,1))
        db.session.add(row);emit(None,'Decisão do próprio autor',researcher_id=account.id,resource=('manuscript',m.id));db.session.commit()
        with self.client.session_transaction() as s:s.clear();s.update(researcher_id=account.id,researcher_nonce=account.token_nonce,csrf_token='test')
        self.assertEqual(self.client.get('/conta/sessao').json['notification_count'],2)
        item=StaffNotice.query.filter_by(researcher_id=account.id,resource_type='reader_journal',resource_id=self.journal.id).one()
        self.assertEqual(self.client.get('/conta/sessao').json['notification_count'],2) # Same revision never duplicates.
        notifications_page=self.client.get('/conta/notificacoes')
        self.assertEqual(notifications_page.status_code,200)
        # A página pública já não apresenta o bloco de avisos internos removido da interface.
        self.assertNotIn(b'Decis',notifications_page.data)
        # Os avisos continuam registados e a eliminação não desactiva o acompanhamento.
        self.assertIsNone(item.removed_at)
        self.assertTrue(row.following)
        self.assertEqual(self.post('/conta/notificacoes',action='delete',id=item.id).status_code,303)
        self.assertTrue(row.following);self.assertFalse(row.saved);self.assertIsNotNone(item.removed_at)
        self.assertEqual(self.client.get('/conta/sessao').json['notification_count'],1)
        self.assertEqual(self.client.get('/submissoes/api/notificacoes').json['unread'],1)
        self.journal.updated_at=utcnow()+timedelta(seconds=1);db.session.commit()
        self.assertEqual(self.client.get('/conta/sessao').json['notification_count'],2)
        self.assertEqual(StaffNotice.query.filter_by(researcher_id=account.id,resource_type='reader_journal',resource_id=self.journal.id).count(),2)
        self.assertTrue(row.following)
