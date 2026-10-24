"""Premium-only resource, learning, delegation and scheduling integration tests."""
import io
import json
import secrets
import zipfile
import unittest
from datetime import timedelta
from unittest.mock import patch

from bs4 import BeautifulSoup
from reportlab.pdfgen.canvas import Canvas
from werkzeug.datastructures import FileStorage
from sqlalchemy import create_engine, inspect, text

import test_premium as existing
from app import app
from models import db, utcnow, AdminUser
from premium_models import (PremiumContent, PremiumResource, PremiumFile, PremiumLesson, PremiumProgress,
    PremiumEvent, PremiumRegistration, PremiumCertificate, PremiumCollectionItem, PremiumSetting,
    PremiumStaff, PremiumPlanTerms, PremiumCategory, PremiumUsage, PremiumPlan)
from premium_features import process_publications, completion
from premium_resources import epub_chapters, save_file
from premium_schema import upgrade_learning_schema
from premium_settings import notify
from governance_models import StaffNotice

MODELS=(PremiumUsage,PremiumCertificate,PremiumRegistration,PremiumProgress,PremiumCollectionItem,
        PremiumLesson,PremiumFile,PremiumEvent,PremiumResource,PremiumPlanTerms,PremiumStaff,PremiumSetting,PremiumCategory)


def pdf_bytes(named=False):
    output=io.BytesIO();canvas=Canvas(output);canvas.drawString(40,700,'Documento educativo');canvas.save()
    if named:
        from pypdf import PdfReader,PdfWriter
        writer=PdfWriter();writer.append(PdfReader(io.BytesIO(output.getvalue())))
        writer.add_named_destination('seccao',0)
        result=io.BytesIO();writer.write(result);return result.getvalue()
    return output.getvalue()


def epub_bytes(active=False):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as archive:
        archive.writestr('mimetype','application/epub+zip')
        archive.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="OPS/book.opf"/></rootfiles></container>')
        archive.writestr('OPS/book.opf','<package xmlns="http://www.idpf.org/2007/opf"><manifest><item id="second" href="b.xhtml"/><item id="first" href="a.xhtml"/></manifest><spine><itemref idref="second"/><itemref idref="first"/></spine></package>')
        archive.writestr('OPS/b.xhtml','<html><body><h1>Segundo no ficheiro, primeiro no livro</h1>'+('<script>alert(1)</script><img src="https://evil.test/a"><p onclick="evil()">Seguro</p>' if active else '')+'</body></html>')
        archive.writestr('OPS/a.xhtml','<html><body><h1>Último capítulo</h1></body></html>')
    return output.getvalue()


class PremiumLearningTests(unittest.TestCase):
    admin=existing.PremiumTests.admin
    login=existing.PremiumTests.login
    grant=existing.PremiumTests.grant

    def setUp(self):
        existing.PremiumTests.setUp(self)
        for model in MODELS:model.query.delete(synchronize_session=False)
        db.session.commit()

    def tearDown(self):
        db.session.rollback()
        for model in MODELS:model.query.delete(synchronize_session=False)
        db.session.commit()
        existing.PremiumTests.tearDown(self)

    def make_resource(self,kind='ebook',**values):
        resource=PremiumResource(content_id=self.item.id,resource_type=kind,state='published',
            plan_ids=[],metadata_fields={'author':'Autoria verificada','rights_confirmed':True},download_allowed=False)
        for key,value in values.items():setattr(resource,key,value)
        db.session.add(resource);db.session.commit();return resource

    def form(self,**values):
        result=dict(csrf_token='premium-csrf',title=self.item.title,kind='course',summary=self.item.summary,
            body=self.item.body,category='Investigação',version=str(self.item.version),resource_type='ebook',
            resource_state='published',rights_confirmed='on',author='Autoria verificada',language='Português')
        result.update(values);return result

    def csrf(self):
        with self.client.session_transaction() as session:session['csrf_token']='premium-csrf'

    def test_admin_resource_editor_and_all_management_sections_render(self):
        self.admin()
        for path in ['/admin/premium/conteudos/novo','/admin/premium/relatorios']+[
            '/admin/premium/gestao/'+name for name in ['catalogo','cursos','videos','eventos','coleccoes','planos','beneficios','membros','notificacoes','configuracoes']]:
            response=self.client.get(path)
            self.assertEqual(response.status_code,200,path)
        self.assertIn('Adicionar recurso',self.client.get('/admin/premium').text)

    def test_resource_metadata_private_upload_and_server_plan_permissions(self):
        self.admin()
        response=self.client.post(f'/admin/premium/conteudos/{self.item.id}',data=self.form(
            attachment=(io.BytesIO(pdf_bytes()),'manual.pdf'),allowed_plan=str(self.plan.id)))
        self.assertEqual(response.status_code,302,response.text)
        file=PremiumFile.query.one()
        self.assertEqual(file.mime,'application/pdf')
        self.assertEqual(self.client.get(f'/premium/ficheiros/{file.id}').status_code,403)
        self.grant();self.login();self.csrf()
        response=self.client.get(f'/premium/ficheiros/{file.id}')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.data.startswith(b'%PDF-'))
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertEqual(self.client.get(f'/premium/ficheiros/{file.id}?download=1').status_code,403)
        other=PremiumPlan(name='Anual diferente',interval='annual',price_minor=10000,currency='MZN',active=True)
        db.session.add(other);db.session.flush();PremiumResource.query.one().plan_ids=[other.id];db.session.commit()
        self.assertEqual(self.client.get(f'/premium/ficheiros/{file.id}').status_code,403)

    def test_bad_upload_and_missing_rights_roll_back_catalogue_changes(self):
        self.admin();old=self.item.title
        response=self.client.post(f'/admin/premium/conteudos/{self.item.id}',data=self.form(
            title='Não deve persistir',attachment=(io.BytesIO(b'<html>fake</html>'),'falso.pdf')))
        self.assertEqual(response.status_code,400)
        db.session.refresh(self.item);self.assertEqual(self.item.title,old)
        self.assertEqual(PremiumFile.query.count(),0)
        response=self.client.post(f'/admin/premium/conteudos/{self.item.id}',data=self.form(rights_confirmed=''))
        self.assertEqual(response.status_code,400)

    def test_scheduled_publication_is_durable_and_not_done_by_page_requests(self):
        self.admin();future=utcnow()+timedelta(days=1)
        from premium_resources import local_input
        response=self.client.post(f'/admin/premium/conteudos/{self.item.id}',data=self.form(
            resource_state='scheduled',publish_at=local_input(future)))
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.get(f'/premium/conteudos/{self.item.id}').status_code,404)
        resource=PremiumResource.query.one()
        self.assertEqual(resource.state,'scheduled')
        resource.publish_at=utcnow()-timedelta(minutes=1);db.session.commit()
        self.assertEqual(process_publications(),1)
        self.assertEqual(process_publications(),0)
        self.assertTrue(self.item.published)

    def test_archive_restore_and_delete_confirmation(self):
        self.make_resource();self.admin()
        path=f'/admin/premium/conteudos/{self.item.id}/estado'
        self.assertEqual(self.client.post(path,data={'csrf_token':'premium-csrf','version':self.item.version,'action':'archive'}).status_code,302)
        self.assertEqual(self.client.get(f'/premium/conteudos/{self.item.id}').status_code,404)
        self.assertEqual(self.client.post(path,data={'csrf_token':'premium-csrf','version':self.item.version,'action':'restore'}).status_code,302)
        self.assertEqual(PremiumResource.query.one().state,'draft')
        self.assertEqual(self.client.post(path,data={'csrf_token':'premium-csrf','version':self.item.version,'action':'delete'}).status_code,400)
        self.assertEqual(self.client.post(path,data={'csrf_token':'premium-csrf','version':self.item.version,'action':'delete','confirm':'on'}).status_code,302)
        self.assertIsNone(db.session.get(PremiumContent,self.item.id))

    def test_used_resources_are_archived_instead_of_destroying_learning_history(self):
        self.make_resource();self.grant();self.login()
        self.assertEqual(self.client.get(f'/premium/conteudos/{self.item.id}').status_code,200)
        self.admin()
        response=self.client.post(f'/admin/premium/conteudos/{self.item.id}/estado',data={
            'csrf_token':'premium-csrf','version':self.item.version,'action':'delete','confirm':'on'})
        self.assertEqual(response.status_code,409)
        self.assertEqual(PremiumProgress.query.count(),1)

    def test_epub_uses_spine_order_and_removes_active_or_remote_content(self):
        chapters=epub_chapters(epub_bytes(active=True))
        self.assertIn('primeiro no livro',chapters[0])
        self.assertIn('Último capítulo',chapters[1])
        for value in ('script','alert(1)','onclick','evil.test'):self.assertNotIn(value,chapters[0])

    def test_epub_traversal_is_rejected(self):
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as archive:archive.writestr('../fora.xhtml','<p>fora</p>')
        with self.assertRaises(ValueError):epub_chapters(output.getvalue())

    def test_reader_keeps_position_and_bookmark_with_access_checks(self):
        self.make_resource();save_file(self.item,FileStorage(stream=io.BytesIO(epub_bytes()),filename='livro.epub'),'attachment');db.session.commit()
        self.grant();self.login();self.csrf()
        path=f'/premium/conteudos/{self.item.id}/leitor'
        self.assertEqual(self.client.get(path+'?chapter=2').status_code,200)
        progress=PremiumProgress.query.one()
        response=self.client.post(path,data={'csrf_token':'premium-csrf','version':progress.version,'position':'2','bookmark':'Rever esta passagem'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(PremiumProgress.query.one().bookmark,'Rever esta passagem')
        self.assertIn('Último capítulo',self.client.get(path).text)
        self.assertEqual(self.client.post(path,data={'csrf_token':'premium-csrf','version':progress.version,'position':'99'}).status_code,400)

    def test_pdf_reader_csp_exception_is_confined_to_reader(self):
        self.make_resource();save_file(self.item,FileStorage(stream=io.BytesIO(pdf_bytes()),filename='livro.pdf'),'attachment');db.session.commit()
        self.grant();self.login()
        response=self.client.get(f'/premium/conteudos/{self.item.id}/leitor')
        self.assertEqual(response.status_code,200)
        self.assertIn("frame-src 'self'",response.headers['Content-Security-Policy'])
        self.assertNotIn("frame-src 'self'",self.client.get('/').headers['Content-Security-Policy'])

    def test_expired_subscription_cannot_read_files_or_lessons(self):
        self.make_resource('course');sub=self.grant();self.login()
        file=save_file(self.item,FileStorage(stream=io.BytesIO(pdf_bytes()),filename='manual.pdf'),'attachment')
        lesson=PremiumLesson(content_id=self.item.id,title='Aula',body='Privado',published=True,questions=[])
        db.session.add(lesson);sub.ends_at=utcnow()-timedelta(seconds=1);db.session.commit()
        self.assertEqual(self.client.get(f'/premium/ficheiros/{file.id}').status_code,403)
        self.assertEqual(self.client.get(f'/premium/aulas/{lesson.id}').status_code,403)

    def test_assessment_is_graded_on_server_and_certificate_requires_all_lessons(self):
        self.make_resource('course',certificate_enabled=True);self.grant();self.login();self.csrf()
        lesson=PremiumLesson(content_id=self.item.id,title='Aula',body='Conteúdo protegido',questions=[{'prompt':'Qual é a resposta?','options':['Errada','Certa'],'answer':1}],published=True)
        db.session.add(lesson);db.session.commit()
        path=f'/premium/aulas/{lesson.id}'
        self.assertEqual(self.client.get(path).status_code,200)
        self.assertEqual(self.client.post(f'/premium/conteudos/{self.item.id}/certificado',data={'csrf_token':'premium-csrf'}).status_code,403)
        progress=PremiumProgress.query.one()
        form={'csrf_token':'premium-csrf','lesson_version':lesson.version,'progress_version':progress.version,'answer_0':'0','score':'100','passed':'true'}
        self.assertEqual(self.client.post(path,data=form).status_code,200)
        self.assertEqual(completion(self.item,self.account)[1],[])
        form.update(progress_version=progress.version,answer_0='1')
        self.assertEqual(self.client.post(path,data=form).status_code,200)
        self.assertEqual(completion(self.item,self.account)[1],[lesson.id])
        response=self.client.post(f'/premium/conteudos/{self.item.id}/certificado',data={'csrf_token':'premium-csrf'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.get(response.location).mimetype,'application/pdf')
        self.client.post(f'/premium/conteudos/{self.item.id}/certificado',data={'csrf_token':'premium-csrf'})
        self.assertEqual(PremiumCertificate.query.count(),1)
        lesson.body='Versão nova';db.session.commit()
        self.assertEqual(completion(self.item,self.account)[1],[])

    def test_lesson_editor_accepts_normal_fields_and_no_code_is_required(self):
        self.make_resource('course');self.admin()
        response=self.client.post(f'/admin/premium/conteudos/{self.item.id}/aulas',data={
            'csrf_token':'premium-csrf','version':self.item.version,'title':'Aula criada','module':'Módulo 1','body':'Conteúdo',
            'position':'1','published':'on','question_0':'Qual?','options_0':'Primeira\nSegunda','answer_0':'2'})
        self.assertEqual(response.status_code,302,response.text)
        lesson=PremiumLesson.query.one()
        self.assertEqual(lesson.questions[0]['answer'],1)
        self.assertEqual(self.client.get(f'/admin/premium/conteudos/{self.item.id}/aulas').status_code,200)

    def test_event_capacity_registration_idempotence_and_private_meeting_link(self):
        self.make_resource('event');self.grant();self.login();self.csrf()
        event=PremiumEvent(content_id=self.item.id,starts_at=utcnow()+timedelta(days=1),ends_at=utcnow()+timedelta(days=1,hours=2),capacity=1,mode='virtual',meeting_url='https://example.test/sessao-privada')
        db.session.add(event);db.session.commit()
        page=self.client.get(f'/premium/conteudos/{self.item.id}')
        self.assertNotIn('sessao-privada',page.text)
        path=f'/premium/eventos/{self.item.id}/inscricao'
        for _ in range(2):self.assertEqual(self.client.post(path,data={'csrf_token':'premium-csrf','action':'register'}).status_code,302)
        self.assertEqual(PremiumRegistration.query.count(),1)
        self.assertIn('sessao-privada',self.client.get(f'/premium/conteudos/{self.item.id}').text)
        self.client.post(path,data={'csrf_token':'premium-csrf','action':'cancel'})
        self.assertNotIn('sessao-privada',self.client.get(f'/premium/conteudos/{self.item.id}').text)

    def test_collection_links_do_not_bypass_child_plan_permission(self):
        self.make_resource('collection');self.grant();self.login()
        child=PremiumContent(title='Recurso de outro plano',kind='course',summary='Público',body='SEGREDO-OUTRO',published=True)
        db.session.add(child);db.session.flush()
        db.session.add(PremiumResource(content_id=child.id,resource_type='document',state='published',metadata_fields={},plan_ids=[2147483647]))
        db.session.add(PremiumCollectionItem(collection_id=self.item.id,content_id=child.id,position=1));db.session.commit()
        self.assertIn(child.title,self.client.get(f'/premium/conteudos/{self.item.id}').text)
        self.assertEqual(self.client.get(f'/premium/conteudos/{child.id}').status_code,403)

    def test_favourites_and_history_are_owned_and_usage_is_not_inflated_by_reload(self):
        self.make_resource();self.grant();self.login();self.csrf()
        for _ in range(3):self.client.get(f'/premium/conteudos/{self.item.id}')
        self.assertEqual(PremiumUsage.query.filter_by(action='content_view').count(),1)
        self.client.post(f'/premium/conteudos/{self.item.id}/favorito',data={'csrf_token':'premium-csrf'})
        self.assertIn(self.item.title,self.client.get('/premium/minha-aprendizagem?favourites=1').text)
        self.assertEqual(PremiumProgress.query.one().owner_id,self.account.id)

    def test_metadata_only_edits_invalidate_stale_editor_versions(self):
        self.make_resource();self.admin();version=self.item.version
        response=self.client.post(f'/admin/premium/conteudos/{self.item.id}',data=self.form(author='Novo autor'))
        self.assertEqual(response.status_code,302)
        self.assertGreater(self.item.version,version)
        response=self.client.post(f'/admin/premium/conteudos/{self.item.id}',data=self.form(version=version,author='Alteração concorrente'))
        self.assertEqual(response.status_code,409)

    def test_settings_versions_and_provider_configuration_cannot_be_fabricated(self):
        self.admin()
        for _ in range(2):
            row=PremiumSetting.query.first();version=str(row.version) if row else '1'
            response=self.client.post('/admin/premium/gestao/configuracoes',data={'csrf_token':'premium-csrf','version':version,'methods':'mpesa','currencies':'MZN'})
            self.assertEqual(response.status_code,302)
        from billing_providers import available_methods
        with patch.dict('os.environ',{'PREMIUM_PAYMENTS_ENABLED':'false'}):self.assertEqual(available_methods('MZN'),{})
        response=self.client.get('/admin/premium/gestao/configuracoes')
        self.assertIn('value="'+str(PremiumSetting.query.one().version)+'"',response.text)

    def test_notice_configuration_does_not_change_other_portal_notifications(self):
        db.session.add(PremiumSetting(id=1,values={'notifications':{'learning':False}}));db.session.commit()
        before=StaffNotice.query.filter_by(researcher_id=self.account.id).count()
        notify(self.account.id,'learning','Privado','Mensagem','test:'+secrets.token_hex(6));db.session.commit()
        self.assertEqual(StaffNotice.query.filter_by(researcher_id=self.account.id).count(),before)
        from internal_notices import emit
        emit(None,'Notificação geral','Preservada',researcher_id=self.account.id,key=secrets.token_hex(6));db.session.commit()
        self.assertEqual(StaffNotice.query.filter_by(researcher_id=self.account.id).count(),before+1)

    def test_publication_notices_are_bounded_and_deduplicated(self):
        self.make_resource(notification_done=False);self.grant()
        before=StaffNotice.query.filter_by(researcher_id=self.account.id).count()
        process_publications(10);process_publications(10)
        self.assertEqual(StaffNotice.query.filter_by(researcher_id=self.account.id).count(),before+1)

    def test_categories_are_managed_and_in_use_categories_are_not_deleted(self):
        self.admin()
        response=self.client.post('/admin/premium/categorias',data={'csrf_token':'premium-csrf','name':'Biologia','description':'Recursos'})
        self.assertEqual(response.status_code,302)
        row=PremiumCategory.query.one();self.item.category=row.name;db.session.commit()
        self.client.post('/admin/premium/categorias',data={'csrf_token':'premium-csrf','id':row.id,'name':'Ciência','description':'Recursos'})
        db.session.refresh(self.item);self.assertEqual(self.item.category,'Ciência')
        self.client.post('/admin/premium/categorias',data={'csrf_token':'premium-csrf','id':row.id,'action':'delete','confirm':'on'})
        self.assertEqual(PremiumCategory.query.count(),1)

    def test_bibliographic_search_and_format_filter_do_not_search_private_bodies(self):
        self.make_resource();save_file(self.item,FileStorage(stream=io.BytesIO(pdf_bytes()),filename='manual.pdf'),'attachment');db.session.commit()
        self.assertIn(self.item.title,self.client.get('/premium/biblioteca?q=Autoria&formato=pdf&recurso=ebook').text)
        self.assertNotIn(self.item.title,self.client.get('/premium/biblioteca?q=SEGREDO-PREMIUM').text)

    def test_new_mutations_require_csrf(self):
        self.make_resource();self.grant();self.login()
        for path in [f'/premium/conteudos/{self.item.id}/favorito',f'/premium/eventos/{self.item.id}/inscricao',f'/premium/conteudos/{self.item.id}/certificado']:
            self.assertEqual(self.client.post(path).status_code,400,path)

    def test_conditions_page_uses_configured_terms(self):
        db.session.add(PremiumPlanTerms(plan_id=self.plan.id,renewal='Renovação contratual definida.',refund='Condições de reembolso.'));db.session.commit()
        response=self.client.get(f'/premium/planos/{self.plan.id}/condicoes')
        self.assertEqual(response.status_code,200)
        self.assertIn('Renovação contratual definida.',response.text)

    def test_library_delegate_cannot_change_plans_finances_or_global_permissions(self):
        self.admin(primary=False)
        with self.client.session_transaction() as session:ident=session['admin_id']
        grant=PremiumStaff(admin_id=ident,permissions=['content']);db.session.add(grant);db.session.commit()
        self.assertEqual(self.client.get('/admin/premium/gestao/catalogo').status_code,200)
        self.assertEqual(self.client.get('/admin/premium/conteudos/novo').status_code,200)
        for path in ['/admin/premium/planos/novo','/admin/premium/financeiro','/admin/premium/gestao/configuracoes','/admin/premium/gestao/membros']:
            self.assertEqual(self.client.get(path).status_code,403,path)
        self.assertEqual(self.client.post('/admin/premium/permissoes',data={'csrf_token':'premium-csrf','admin_id':ident,'permissions':'finance'}).status_code,403)
        grant.permissions=[];db.session.commit()
        self.assertEqual(self.client.get('/admin/premium/conteudos/novo').status_code,403)

    def test_a_second_subscriber_cannot_exceed_event_capacity(self):
        from submission_models import Researcher
        self.make_resource('event');self.grant();self.login();self.csrf()
        db.session.add(PremiumEvent(content_id=self.item.id,starts_at=utcnow()+timedelta(days=1),ends_at=utcnow()+timedelta(days=2),capacity=1,mode='virtual'))
        db.session.commit()
        path=f'/premium/eventos/{self.item.id}/inscricao'
        self.assertEqual(self.client.post(path,data={'csrf_token':'premium-csrf','action':'register'}).status_code,302)
        other=Researcher(name='Outro participante',email=secrets.token_hex(6)+'@example.test',password_hash='unused',token_nonce='nonce',active=True,verified=True)
        db.session.add(other);db.session.commit();self.grant(owner_id=other.id);self.login(other);self.csrf()
        self.assertEqual(self.client.post(path,data={'csrf_token':'premium-csrf','action':'register'}).status_code,409)
        self.assertEqual(PremiumRegistration.query.filter_by(state='registered').count(),1)

    def test_multiple_videos_do_not_replace_material_of_previous_lessons(self):
        self.make_resource('course')
        first=save_file(self.item,FileStorage(stream=io.BytesIO(b'\0\0\0\x18ftypisom'+b'0'*20),filename='aula1.mp4'),'video')
        second=save_file(self.item,FileStorage(stream=io.BytesIO(b'\0\0\0\x18ftypisom'+b'1'*20),filename='aula2.mp4'),'video')
        db.session.commit()
        self.assertNotEqual(first.id,second.id)
        self.assertEqual(PremiumFile.query.count(),2)

    def test_private_range_request_and_enabled_download(self):
        self.make_resource(download_allowed=True);self.grant();self.login()
        # A names dictionary with ordinary destinations is not executable JavaScript.
        file=save_file(self.item,FileStorage(stream=io.BytesIO(pdf_bytes(named=True)),filename='manual.pdf'),'attachment');db.session.commit()
        response=self.client.get(f'/premium/ficheiros/{file.id}',headers={'Range':'bytes=0-9'})
        self.assertEqual(response.status_code,206)
        self.assertEqual(len(response.data),10)
        response=self.client.get(f'/premium/ficheiros/{file.id}?download=1')
        self.assertEqual(response.status_code,200)
        self.assertIn('attachment',response.headers['Content-Disposition'])

    def test_open_access_epub_can_be_read_without_a_paid_or_registered_account(self):
        self.make_resource();self.item.open_access_required=True
        save_file(self.item,FileStorage(stream=io.BytesIO(epub_bytes()),filename='livro.epub'),'attachment');db.session.commit()
        response=self.client.get(f'/premium/conteudos/{self.item.id}/leitor')
        self.assertEqual(response.status_code,200)
        self.assertIn('primeiro no livro',response.text)
        self.assertEqual(PremiumProgress.query.count(),0)

    def test_collection_editor_stores_selected_resources_in_defined_order(self):
        self.admin()
        first=PremiumContent(title='Primeiro recurso',kind='course',summary='Resumo',body='Texto',published=True)
        second=PremiumContent(title='Segundo recurso',kind='course',summary='Resumo',body='Texto',published=True)
        db.session.add_all([first,second]);db.session.commit()
        values=self.form(resource_type='collection',collection_picker='on',collection_member=[str(first.id),str(second.id)])
        values['collection_order_'+str(first.id)]='2';values['collection_order_'+str(second.id)]='1'
        response=self.client.post(f'/admin/premium/conteudos/{self.item.id}',data=values)
        self.assertEqual(response.status_code,302,response.text)
        self.assertEqual([r.content_id for r in PremiumCollectionItem.query.order_by(PremiumCollectionItem.position)],[second.id,first.id])


class PremiumLearningMigrationTests(unittest.TestCase):
    def test_learning_schema_is_additive_and_repeatable(self):
        engine=create_engine('sqlite://')
        with engine.begin() as connection:
            connection.execute(text('CREATE TABLE premium_content (id INTEGER PRIMARY KEY, body TEXT)'))
            connection.execute(text("INSERT INTO premium_content VALUES (7,'Texto preservado')"))
            upgrade_learning_schema(connection);upgrade_learning_schema(connection)
            self.assertEqual(connection.execute(text('SELECT body FROM premium_content')).scalar(),'Texto preservado')
            self.assertTrue({'premium_resource','premium_file','premium_lesson','premium_event','premium_staff'}.issubset(inspect(connection).get_table_names()))
