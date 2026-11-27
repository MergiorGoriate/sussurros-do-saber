"""Exercise every real grant through rendered UI and authorized/denied operations.
Fixtures are synthetic and use the test database only; no network or SMTP delivery.
"""
import secrets
from datetime import date, timedelta
import unittest
import test_staff_governance as fixtures
from governance import PERMISSIONS, JOURNAL_PERMISSIONS, has_permission, has_any_permission, mandates
from governance_models import TeamRole, TeamAppointment, ArticleWorkflow, StaffPeerReview, TeamMember, StaffTask
from models import db, ContactMessage, Subscriber, Comment, Author, Category, EditorialPolicy, utcnow


class PermissionMatrixTests(unittest.TestCase):
    setUp=fixtures.StaffGovernanceTests.setUp
    tearDown=fixtures.StaffGovernanceTests.tearDown
    member=fixtures.StaffGovernanceTests.member
    signin=fixtures.StaffGovernanceTests.signin
    post=fixtures.StaffGovernanceTests.post
    manuscript=fixtures.StaffGovernanceTests.manuscript
    article=fixtures.StaffGovernanceTests.article
    def grant(self, permission, scope=None):
        member=self.member()
        role=TeamRole(code='custom_'+secrets.token_hex(6),name='Função personalizada',permissions=[permission])
        db.session.add(role);db.session.flush()
        member.appointments[0].role=role
        member.appointments[0].journal_id=scope
        db.session.commit()
        return member

    def operation(self, permission, member):
        """Return GET UI, POST/GET action, payload, and persisted outcome check."""
        if permission.startswith('translations.'):
            from translation_models import ContentTranslation,TranslationVersion,TranslationJob
            from translation_service import source,digest
            article=self.article(self.member());article.status='published';db.session.commit()
            original=source('article',article.id)
            item=ContentTranslation(kind='article',source_id=article.id,version=1,state='review')
            db.session.add(item);db.session.flush()
            db.session.add(TranslationVersion(translation_id=item.id,number=1,source=original,source_hash=digest(original),content=original,report={'ready':True}))
            if permission=='translations.manage':
                job=TranslationJob(translation_id=item.id,state='queued');db.session.add(job);db.session.flush()
                db.session.commit()
                return '/admin/internacionalizacao/',f'/admin/internacionalizacao/tarefas/{job.id}',dict(action='cancel'),lambda:job.state=='cancelled'
            action='approve' if permission=='translations.approve' else 'publish'
            if action=='publish':item.state='approved';item.approved_version=1
            db.session.commit()
            return '/admin/internacionalizacao/',f'/admin/internacionalizacao/{item.id}/accao',dict(action=action,version=1,reviewed='yes'),lambda:item.state==('approved' if action=='approve' else 'published')
        if permission.startswith('dissemination.'):
            from dissemination_models import DisseminationMaterial, DisseminationVersion
            from dissemination_service import snapshot
            article=self.article(self.member());article.status='published';db.session.commit()
            item=DisseminationMaterial(source_kind='portal',source_id=article.id,network='facebook',kind='text',
                token=secrets.token_urlsafe(24),version=1,status='review')
            db.session.add(item);db.session.flush()
            db.session.add(DisseminationVersion(material_id=item.id,number=1,source=snapshot('portal',article.id),
                payload={'title':'Teste sintético','caption':'Texto de teste'},report={'ready':True},assets=[]))
            operation={'dissemination.manage':'correct','dissemination.approve':'reject','dissemination.publish':'published'}[permission]
            if operation=='published':
                item.status='approved';item.approved_version=1;item.approved_at=utcnow();item.approved_by=self.primary.id
            db.session.commit()
            data=dict(action=operation,version=1,note='Decisão sintética para verificar permissões.',publication_url='https://www.facebook.com/posts/123')
            state={'correct':'correction','reject':'rejected','published':'published'}[operation]
            return '/admin/divulgacao/',f'/admin/divulgacao/{item.id}/accao',data,lambda: item.status==state
        if permission=='team.manage':
            name='Novo membro '+secrets.token_hex(4)
            return '/admin/equipa','/admin/equipa',dict(name=name,email=name.split()[-1]+'@example.org',status='invited',group='support'),lambda: TeamMember.query.filter_by(name=name).count()==1
        if permission=='tasks.manage':
            title='Tarefa '+secrets.token_hex(4)
            return '/admin/trabalho','/admin/trabalho',dict(title=title,assignee_id=member.id,due_on=str(date.today())),lambda: StaffTask.query.filter_by(title=title).count()==1
        if permission == 'automation.read':
            return '/admin/automacao', '/admin/automacao/execucoes', None, lambda: True
        if permission == 'automation.manage':
            from automation.models import AutomationOperator
            operator = db.session.get(AutomationOperator, 'workflow')
            return '/admin/automacao', '/admin/automacao/operadores/workflow', dict(
                interval=180, retention=90, age_days=7), lambda: operator.interval_minutes == 180
        if permission=='reports.read':
            return '/admin/relatorios-equipa','/admin/relatorios-equipa',None,lambda: True
        if permission in {'authors.manage','categories.manage'}:
            name='Registo '+secrets.token_hex(6);model=Author if permission=='authors.manage' else Category
            path='/admin/autores' if model is Author else '/admin/categorias'
            return path,path,dict(name=name),lambda: model.query.filter_by(name=name).count()==1
        if permission=='policies.manage':
            marker='Política sintética '+secrets.token_hex(4)
            return '/admin/politicas-editoriais','/admin/politicas-editoriais',dict(ai_policy=marker),lambda: EditorialPolicy.query.first().ai_policy==marker
        if permission=='contacts.manage':
            obj=ContactMessage(name='Contacto sintético',email='contact@example.org',subject='Teste',message='Teste isolado')
            db.session.add(obj);db.session.commit();ident=obj.id
            return '/admin/contactos',f'/admin/contactos/{ident}/eliminar',{},lambda: db.session.get(ContactMessage,ident) is None
        if permission=='subscribers.manage':
            obj=Subscriber(email=secrets.token_hex(6)+'@example.org');db.session.add(obj);db.session.commit()
            return '/admin/subscritores',f'/admin/subscritores/{obj.id}/estado',{},lambda: not db.session.get(Subscriber,obj.id).active
        if permission.startswith('article.') or permission=='comments.manage':
            owner=member if permission=='article.write' else self.member()
            article=self.article(owner);workflow=db.session.get(ArticleWorkflow,article.id)
            if permission in {'article.write','article.edit'}:
                path='/admin/artigos/novo' if permission=='article.write' else f'/admin/artigos/{article.id}/editar'
                title='Texto alterado '+secrets.token_hex(6)
                return path,path,dict(title=title,summary='Resumo científico de teste',body='Texto com fundamentação. '*10,status='draft',author_id=owner.author_id,category_id=self.category.id),lambda: db.session.query(db.exists().where(__import__('models').Article.title==title)).scalar()
            if permission=='article.delete':
                return '/admin/artigos',f'/admin/artigos/{article.id}/eliminar',{},lambda: db.session.get(__import__('models').Article,article.id) is None
            if permission=='comments.manage':
                comment=Comment(article_id=article.id,name='Leitor',email='reader@example.org',body='Comentário sintético')
                db.session.add(comment);db.session.commit()
                return '/admin/comentarios',f'/admin/comentarios/{comment.id}/estado',dict(action='approve'),lambda: db.session.get(Comment,comment.id).approved
            workflow.stage='review';workflow.reviewer_id=member.id if permission=='article.review' else self.member('portal_reviewer').id
            if permission in {'article.approve','article.publish'}:workflow.reviewed_at=utcnow()
            if permission=='article.publish':workflow.stage=article.status='approved';workflow.approved_at=utcnow()
            db.session.commit();path=f'/admin/fluxo-artigos/{article.id}'
            action={'article.review':'reviewed','article.approve':'approve','article.publish':'publish'}[permission]
            return path,path,dict(action=action,note='Parecer científico isolado. '*5),lambda: bool(workflow.reviewed_at) if action=='reviewed' else bool(workflow.approved_at) if action=='approve' else article.status=='published'
        if permission in {'journal.manage','journal.publish'}:
            path=f'/admin/revistas/{self.journal.id}/eliminar' if permission=='journal.manage' else f'/admin/revistas/{self.journal.id}/publicacao'
            ident=self.journal.id
            if permission=='journal.manage':
                from models import Journal
                j=Journal(title='Revista descartável',slug=secrets.token_hex(6),field='Biologia',description='Teste')
                db.session.add(j);db.session.commit();ident=j.id;path=f'/admin/revistas/{ident}/eliminar'
            return '/admin/revistas',path,{},lambda: db.session.get(__import__('models').Journal,ident) is None if permission=='journal.manage' else db.session.get(__import__('models').Journal,ident).published
        if permission=='submissions.configure':
            return '/admin/submissoes/configuracao','/admin/submissoes/configuracao',dict(journal_id=self.journal.id,article_types='Artigo original',main_formats=['txt'],editorial_email='editorial@example.org',enabled='on'),lambda: db.session.get(__import__('submission_models').SubmissionSetting,self.journal.id).enabled
        if permission.startswith('manuscript.'):
            item,file=self.manuscript(member)
            if permission=='manuscript.production':item.status='accepted'
            db.session.commit();path=f'/admin/submissoes/{item.id}'
            if permission=='manuscript.read':return path,f'/submissoes/ficheiros/{file.id}',None,lambda: True
            if permission=='manuscript.edit':return path,path,dict(action='note',note='Nota sintética'),lambda: any(e.note=='Nota sintética' for e in item.events)
            if permission=='manuscript.assign':
                editor=self.member('associate_editor',self.journal.id)
                return path,path,dict(action='assign',editor_id=editor.admin_id),lambda: item.editor_id==editor.admin_id
            if permission=='manuscript.decide':return path,path,dict(action='accepted',note='Decisão fundamentada sintética'),lambda: item.status=='accepted'
            if permission=='manuscript.production':return path,path+'/preparar',{},lambda: bool(item.publication_id) and item.status=='production'
            review=StaffPeerReview(manuscript_id=item.id,reviewer_id=member.id,version_number=1,due_on=date.today())
            db.session.add(review);db.session.commit();path=f'/admin/pareceres/{review.id}'
            return path,path,dict(action='accept',no_conflict='on'),lambda: review.status=='accepted'
        raise AssertionError(permission)

    def test_every_permission_ui_action_denial_expiry_inactivity_and_revocation(self):
        # Each grant is isolated: no unrelated permissions to make its UI appear.
        for permission in PERMISSIONS:
            with self.subTest(permission=permission):
                member=self.grant(permission)
                ui,action,data,check=self.operation(permission,member)
                self.signin(member.admin)
                self.assertEqual(self.client.get(ui).status_code,200,(permission,ui))
                self.assertIn('no-store',self.client.get(ui).headers['Cache-Control'])
                grant=member.appointments[0];saved=grant.role.permissions[:]
                for invalid in ['revoked','expired','future','suspended','unaccepted']:
                    grant.role.permissions=[] if invalid=='revoked' else saved
                    grant.ends_on=date.today()-timedelta(days=1) if invalid=='expired' else date.today()+timedelta(days=10)
                    grant.starts_on=date.today()+timedelta(days=1) if invalid=='future' else date.today()-timedelta(days=1)
                    member.status='suspended' if invalid=='suspended' else 'active'
                    member.accepted_at=None if invalid=='unaccepted' else utcnow()
                    db.session.commit()
                    response=self.client.post(action,data={'csrf_token':'test',**data}) if data is not None else self.client.get(action)
                    self.assertIn(response.status_code,[403,404],(permission,invalid,response.status_code))
                grant.role.permissions=saved;member.status='active';member.accepted_at=utcnow();db.session.commit()
                member.admin.active=False;db.session.commit()
                response=self.post(action,**data) if data is not None else self.client.get(action)
                if permission=='manuscript.read':
                    self.assertEqual(response.status_code,404)
                else:
                    self.assertEqual(response.status_code,302,(permission,'inactive account'))
                    self.assertIn('/admin/login',response.location)
                member.admin.active=True;db.session.commit();self.signin(member.admin)
                response=self.post(action,**data) if data is not None else self.client.get(action)
                self.assertEqual(response.status_code,200 if data is None or permission=='categories.manage' else 302,(permission,response.data[:400]))
                self.assertTrue(check(),permission)

    def test_scope_union_is_permission_specific_and_general_portal_grants_are_explicit(self):
        member=self.grant('manuscript.assign',self.journal.id)
        role=TeamRole(code='scope_'+self.token,name='Outra função',permissions=['manuscript.decide','contacts.manage'])
        db.session.add(role);db.session.flush()
        db.session.add(TeamAppointment(member=member,role=role,journal_id=self.other_journal.id,starts_on=date.today()))
        db.session.commit();self.signin(member.admin)
        first,_=self.manuscript();second,_=self.manuscript(journal=self.other_journal)
        self.assertEqual(self.client.get('/admin/submissoes').status_code,200)
        for item in [first,second]:self.assertEqual(self.client.get(f'/admin/submissoes/{item.id}').status_code,200)
        self.assertEqual(self.post(f'/admin/submissoes/{first.id}',action='accepted',note='Teste').status_code,403)
        self.assertEqual(self.post(f'/admin/submissoes/{second.id}',action='assign',editor_id=member.admin_id).status_code,403)
        self.assertEqual(self.client.get('/admin/contactos').status_code,403)
        self.assertIn('exige um mandato geral'.encode(),self.client.get('/admin/trabalho').data)
        role.permissions=['contacts.manage'];db.session.add(TeamAppointment(member=member,role=role,starts_on=date.today()))
        db.session.commit();self.assertEqual(self.client.get('/admin/contactos').status_code,200)

    def test_every_journal_grant_rejects_other_journal_action(self):
        for permission in JOURNAL_PERMISSIONS:
            with self.subTest(permission=permission):
                member=self.grant(permission,self.other_journal.id)
                ui,action,data,_=self.operation(permission,member);self.signin(member.admin)
                response=self.post(action,**data) if data is not None else self.client.get(action)
                self.assertIn(response.status_code,[403,404],(permission,response.status_code))

    def test_role_form_persists_custom_choices_without_logout_and_seed_does_not_reset(self):
        member=self.grant('tasks.manage');role=member.appointments[0].role
        self.signin(self.primary)
        response=self.post('/admin/funcoes',id=role.id,name=role.name,purpose='Teste',duties='Teste',limits='Teste',permissions=['tasks.manage','contacts.manage','reports.read','article.write'])
        self.assertEqual(response.status_code,302)
        db.session.expire_all();self.assertEqual(set(role.permissions),{'tasks.manage','contacts.manage','reports.read','article.write'})
        self.signin(member.admin);response=self.client.get('/admin/trabalho')
        for text in [b'Distribuir tarefa',b'/admin/contactos',b'/admin/relatorios-equipa',b'/admin/artigos']:
            self.assertIn(text,response.data)
        role.permissions=['tasks.manage'];db.session.commit()
        response=self.client.get('/admin/trabalho');self.assertNotIn(b'href="/admin/contactos"',response.data)
        self.assertEqual(self.client.get('/admin/contactos').status_code,403)
        from governance import seed_roles
        seed_roles();self.assertEqual(role.permissions,['tasks.manage'])

    def test_new_workflow_first_submit_and_get_is_read_only(self):
        member=self.grant('article.write');article=self.article(member)
        ArticleWorkflow.query.filter_by(article_id=article.id).delete();db.session.commit()
        self.signin(member.admin);path=f'/admin/fluxo-artigos/{article.id}'
        self.assertEqual(self.client.get(path).status_code,200)
        self.assertIsNone(db.session.get(ArticleWorkflow,article.id))
        self.assertEqual(self.post(path,action='submit').status_code,302)
        self.assertEqual(db.session.get(ArticleWorkflow,article.id).stage,'submitted')

    def test_publisher_can_publish_without_editing_and_cannot_change_other_content(self):
        publisher=self.grant('article.publish');owner=self.member();article=self.article(owner)
        workflow=db.session.get(ArticleWorkflow,article.id);workflow.stage=article.status='approved';workflow.approved_at=workflow.reviewed_at=utcnow();db.session.commit()
        self.signin(publisher.admin);path=f'/admin/fluxo-artigos/{article.id}'
        self.assertIn(b'Publicar artigo aprovado',self.client.get(path).data)
        self.assertNotIn(b'Abrir editor',self.client.get(path).data)
        self.assertEqual(self.client.get(f'/admin/artigos/{article.id}/editar').status_code,403)
        self.assertEqual(self.post(path,action='publish').status_code,302)
        self.assertEqual(article.status,'published')

    def test_portal_grants_in_journal_mandate_do_not_gain_global_powers(self):
        for permission in set(PERMISSIONS)-JOURNAL_PERMISSIONS:
            with self.subTest(permission=permission):
                member=self.grant(permission,self.journal.id)
                _,action,data,_=self.operation(permission,member);self.signin(member.admin)
                response=self.post(action,**data) if data is not None else self.client.get(action)
                self.assertIn(response.status_code,[403,404],(permission,response.status_code))
                self.assertIn('exige um mandato geral'.encode(),self.client.get('/admin/trabalho').data)

    def test_assign_reviewer_executes_in_submission_context_and_checks_scope(self):
        assigner=self.grant('manuscript.assign',self.journal.id)
        reviewer=self.member('reviewer',self.journal.id);item,_=self.manuscript()
        self.signin(assigner.admin);path='/admin/pareceres'
        self.assertEqual(self.post(path,manuscript_id=item.id,reviewer_id=reviewer.id,due_on=str(date.today())).status_code,302)
        review=StaffPeerReview.query.filter_by(manuscript_id=item.id,reviewer_id=reviewer.id).one()
        self.assertEqual(review.version_number,item.current_version)
        other,_=self.manuscript(journal=self.other_journal)
        self.assertEqual(self.post(path,manuscript_id=other.id,reviewer_id=reviewer.id,due_on=str(date.today())).status_code,403)
        self.signin(reviewer.admin)
        self.assertEqual(self.post(path,manuscript_id=item.id,reviewer_id=reviewer.id,due_on=str(date.today())).status_code,403)

    def test_production_and_publishing_use_source_journal_scope_and_separate_powers(self):
        production=self.grant('manuscript.production',self.journal.id)
        publisher=self.grant('journal.publish',self.journal.id)
        outsider=self.grant('journal.publish',self.other_journal.id)
        item,_=self.manuscript();item.status='accepted';db.session.commit()
        self.signin(production.admin)
        self.assertEqual(self.post(f'/admin/submissoes/{item.id}/preparar').status_code,302)
        publication=db.session.get(__import__('models').Journal,item.publication_id)
        path=f'/admin/revistas/{publication.id}/publicacao'
        self.assertEqual(self.post(path).status_code,403)
        self.signin(outsider.admin);self.assertEqual(self.post(path).status_code,403)
        self.signin(publisher.admin)
        page=self.client.get('/admin/revistas');self.assertEqual(page.status_code,200)
        self.assertIn(path.encode(),page.data)
        self.assertNotIn(f'/admin/revistas/{publication.id}/editar'.encode(),page.data)
        self.assertEqual(self.client.get(f'/admin/revistas/{publication.id}/editar').status_code,403)
        self.assertEqual(self.post(path).status_code,302)
        self.assertTrue(publication.published);self.assertEqual(item.status,'published')

    def test_readonly_database_audit_includes_custom_role_and_never_changes_data(self):
        from scripts.audit_permissions import inspect_database
        member=self.grant('contacts.manage',self.journal.id)
        before=db.session.query(TeamRole).count()
        result=inspect_database(db.engine.url.render_as_string(hide_password=False))
        self.assertEqual(db.session.query(TeamRole).count(),before)
        self.assertIn(member.appointments[0].role.code,[r['code'] for r in result['roles']])
        record=next(r for r in result['members'] if r['member_id']==member.id)
        self.assertNotIn('contacts.manage',record['effective_general'])
        self.assertEqual(record['blocked'][0]['permission'],'contacts.manage')
        self.assertNotIn('password_hash',str(result));self.assertNotIn('totp_secret',str(result))

    def test_upload_and_policy_preview_apis_use_same_grants(self):
        member=self.grant('reports.read');self.signin(member.admin)
        for path in ['/admin/api/imagens','/admin/api/videos','/admin/politicas-editoriais/previsualizar','/admin/revistas/previsualizar-markdown']:
            response=self.post(path,author_guidelines='Texto')
            self.assertEqual(response.status_code,403,path)
        member.appointments[0].role.permissions=['policies.manage'];db.session.commit()
        response=self.post('/admin/politicas-editoriais/previsualizar',author_guidelines='## Orientações sintéticas')
        self.assertEqual(response.status_code,200);self.assertIn('Orientações sintéticas',response.get_json()['html'])

    def test_unknown_stored_identifiers_are_preserved_but_never_authorize(self):
        member=self.grant('tasks.manage');role=member.appointments[0].role
        role.permissions=['tasks.manage','legacy_unknown'];db.session.commit()
        self.signin(self.primary)
        self.assertEqual(self.post('/admin/funcoes',id=role.id,name=role.name,permissions=['contacts.manage']).status_code,302)
        self.assertEqual(set(role.permissions),{'contacts.manage','legacy_unknown'})
        self.signin(member.admin)
        from app import app
        with app.test_request_context():
            from flask import session
            session['admin_id']=member.admin_id
            self.assertFalse(has_permission('legacy_unknown'))
            self.assertFalse(has_any_permission('legacy_unknown'))

    def test_scheduling_rejects_invalid_date_and_requires_approval_and_publication_grant(self):
        publisher=self.grant('article.publish');owner=self.member();article=self.article(owner)
        workflow=db.session.get(ArticleWorkflow,article.id)
        self.signin(publisher.admin);path=f'/admin/fluxo-artigos/{article.id}'
        self.assertEqual(self.post(path,action='schedule',scheduled_at='2099-01-01T12:00').status_code,409)
        workflow.stage=article.status='approved';workflow.approved_at=utcnow();db.session.commit()
        self.assertEqual(self.post(path,action='schedule',scheduled_at='invalid').status_code,400)
        self.assertEqual(self.post(path,action='schedule',scheduled_at='2099-01-01T12:00+02:00').status_code,302)
        self.assertEqual(article.status,'scheduled');self.assertEqual(article.scheduled_at.hour,10)
        publisher.appointments[0].role.permissions=[];db.session.commit()
        self.assertEqual(self.post(path,action='publish').status_code,404)

