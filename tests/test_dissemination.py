"""Approval, immutable versions, source integrity, quota and failure boundaries."""
import copy
import io
import os
import secrets
import tempfile
import time
import unittest
import zipfile
from datetime import date, timedelta
from unittest.mock import patch, Mock
from PIL import Image
import test_platform
from app import app
from models import db, Article, Journal, AdminUser, Author, Category, utcnow
from extensions import limiter
from governance_models import TeamMember, TeamRole, TeamAppointment
from dissemination_models import (DisseminationMaterial as Material, DisseminationVersion as Version,
    DisseminationEvent as Event, DisseminationJob as Job, DisseminationBudget as Budget, DisseminationClick as Click)
from dissemination_ai import GenerationError
from security_test_support import authenticate_test_session
import dissemination_service as service

BODY = 'As plantas utilizam luz na fotossíntese. A resposta depende das condições ambientais.'
PAYLOAD = dict(title='A luz e as plantas', caption='As plantas utilizam luz na fotossíntese.',
    claims=[dict(text='As plantas utilizam luz na fotossíntese.', evidence=BODY)],
    slides=[dict(heading='A luz e as plantas', body='As plantas utilizam luz na fotossíntese.', claim_ids=[0])],
    illustration='Uma planta iluminada pelo Sol, sem escalas nem texto.',
    visual_label='Ilustração conceptual', layout='balanced', accent='teal')
REPORT = dict(scientific_ok=True, language_ok=True, visual_ok=True, issues=[],
              claim_checks=[dict(id=0, supported=True, reason='O artigo sustenta a afirmação.')])


class DisseminationTests(unittest.TestCase):
    def setUp(self):
        self.ctx = app.app_context(); self.ctx.push()
        self.previous = limiter.enabled; limiter.enabled = False
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, dict(OPENAI_API_KEY='test-only', DISSEMINATION_TEXT_MODEL='fixture',
            DISSEMINATION_REVIEW_MODEL='fixture', DISSEMINATION_IMAGE_MODEL='fixture',
            DISSEMINATION_JOB_UNITS='10', DISSEMINATION_DAILY_UNITS='100', DISSEMINATION_DAILY_JOBS='10',
            DISSEMINATION_STORAGE_DIR=self.temp.name))
        self.env.start()
        for model in (Click, Event, Job, Version, Material, Budget):
            model.query.delete()
        token = secrets.token_hex(5)
        self.article = Article(title='Fotossíntese ' + token, slug='dissemination-' + token, summary=BODY,
            body=BODY, references='', status='published', author_rel=Author.query.first(), category_rel=Category.query.first())
        db.session.add(self.article); db.session.commit()
        self.client = app.test_client()
        self.signin()

    def tearDown(self):
        db.session.rollback(); self.env.stop(); self.temp.cleanup()
        limiter.enabled = self.previous; self.ctx.pop()

    def signin(self, account=None):
        with self.client.session_transaction() as session:
            session.clear()
            session.update(admin_authenticated=True, admin_superuser=account is None,
                admin_last_activity_at=time.time(), csrf_token='dc-test')
            if account:
                session['admin_id'] = account.id
                session['admin_2fa_verified'] = True
            authenticate_test_session(session)

    def post(self, ident, action, **values):
        material = db.session.get(Material, ident)
        return self.client.post(f'/admin/divulgacao/{ident}/accao', data=dict(
            csrf_token='dc-test', version=material.version, action=action, **values))

    def create(self, kind='text', network='facebook'):
        with self.client.session_transaction() as session:
            actor = session['admin_id']
        with app.test_request_context('/'):
            from flask import session
            session['admin_id'] = actor
            item = service.create('portal', self.article.id, network, kind)
            db.session.commit()
        return item

    def process(self, payload=None, report=None):
        with patch('dissemination_ai.generate', return_value=copy.deepcopy(payload or PAYLOAD)), \
             patch('dissemination_ai.review', return_value=copy.deepcopy(report or REPORT)):
            self.assertTrue(service.process_one())

    def ready(self, kind='text'):
        item = self.create(kind)
        if kind != 'text':
            raw = io.BytesIO(); Image.new('RGB', (1024,1024), '#d3e6cf').save(raw, format='PNG')
            with patch('dissemination_ai.illustration', return_value=raw.getvalue()):
                self.process()
        else:
            self.process()
        db.session.refresh(item)
        return item

    def approve(self, item):
        response = Mock(status_code=200)
        with patch('dissemination_service.requests.get', return_value=response):
            result = self.post(item.id, 'approve', human_review='yes')
        db.session.refresh(item)
        return result

    def test_generation_is_queued_and_does_not_call_provider_in_http(self):
        with patch('dissemination_ai.generate') as provider:
            response = self.client.post('/admin/divulgacao/gerar', data=dict(csrf_token='dc-test',
                source=f'portal:{self.article.id}', kind='text', network='facebook'))
        self.assertEqual(response.status_code, 302)
        provider.assert_not_called()
        self.assertEqual(Material.query.one().status, 'generating')
        self.assertEqual(Job.query.one().status, 'queued')

    def test_end_to_end_approved_export_and_manual_publication(self):
        item = self.ready('curiosity')
        self.assertEqual(item.status, 'review')
        self.assertEqual(self.client.get(f'/admin/divulgacao/{item.id}/descarregar').status_code, 409)
        self.assertEqual(self.approve(item).status_code, 302)
        self.assertEqual(item.approved_version, item.version)
        response = self.client.get(f'/admin/divulgacao/{item.id}/descarregar')
        self.assertEqual(response.status_code, 200)
        archive = zipfile.ZipFile(io.BytesIO(response.data))
        self.assertIn('slide-1.png', archive.namelist())
        self.assertIn('/divulgacao/', archive.read('texto.txt').decode())
        self.assertEqual(self.post(item.id, 'published', publication_url='https://www.facebook.com/posts/123').status_code,302)
        self.assertEqual(item.status, 'published')
        self.assertTrue(Event.query.filter_by(material_id=item.id,action='publication_reported').first())

    def test_all_five_networks_have_export_text_limits_and_utms(self):
        for network in service.NETWORKS:
            item = self.create(network=network); self.process()
            self.approve(item)
            response = self.client.get('/divulgacao/' + item.token, headers={'User-Agent': 'Mozilla/5.0'})
            self.assertIn('utm_source=' + network, response.location)
            self.assertIn('utm_content=v1', response.location)
        self.assertEqual(Click.query.count(), 5)

    def test_numeric_or_missing_evidence_blocks_approval(self):
        payload = copy.deepcopy(PAYLOAD)
        payload['claims'][0]['text'] = 'As plantas captam 97% da luz.'
        item = self.create(); self.process(payload)
        self.assertFalse(service.current_version(item).report['ready'])
        self.assertEqual(self.approve(item).status_code, 409)
        self.assertEqual(item.status, 'review')

    def test_semantic_review_flags_unsupported_claims(self):
        report = copy.deepcopy(REPORT)
        report.update(scientific_ok=False, issues=['A afirmação extrapola o artigo.'])
        report['claim_checks'][0]['supported'] = False
        item = self.create(); self.process(report=report)
        self.assertEqual(self.approve(item).status_code,409)
        self.assertIn('extrapola', self.client.get(f'/admin/divulgacao/{item.id}').text)

    def test_incomplete_review_fails_closed(self):
        item = self.create()
        self.process(report={'scientific_ok': True})
        self.assertEqual(item.status, 'failed')
        self.assertEqual(Version.query.count(), 0)
        self.assertEqual(self.approve(item).status_code, 409)

    def test_visual_and_linguistic_failure_block_approval(self):
        for key in ('visual_ok', 'language_ok'):
            report = copy.deepcopy(REPORT); report[key] = False
            item = self.create(); self.process(report=report)
            self.assertEqual(self.approve(item).status_code, 409)

    def test_rejection_is_terminal_and_recorded(self):
        item = self.ready()
        self.assertEqual(self.post(item.id,'reject', note='Conceito incorrecto.').status_code,302)
        self.assertEqual(item.status,'rejected')
        for operation in ('approve','regenerate','restore','published'):
            self.assertEqual(self.post(item.id, operation, human_review='yes').status_code,409)
        self.assertEqual(self.client.get(f'/admin/divulgacao/{item.id}/descarregar').status_code,409)
        self.assertEqual(Event.query.filter_by(material_id=item.id,action='rejected').one().detail,'Conceito incorrecto.')

    def test_correction_revokes_export_and_old_tracking_link(self):
        item = self.ready(); self.approve(item); token = item.token
        self.assertEqual(self.post(item.id,'correct',note='Rever a legenda.').status_code,302)
        self.assertIsNone(item.approved_version)
        self.assertEqual(self.client.get('/divulgacao/' + token).status_code,404)
        self.assertEqual(self.client.get(f'/admin/divulgacao/{item.id}/descarregar').status_code,409)
        self.assertEqual(self.approve(item).status_code,409)

    def test_manual_edit_and_restore_create_new_versions_requiring_review(self):
        item = self.ready()
        fields = dict(title='Plantas e luz',caption=PAYLOAD['caption'],layout='compact',accent='blue',
            visual_label='Ilustração conceptual',heading_0='Luz e fotossíntese',body_0=PAYLOAD['slides'][0]['body'],
            claim_0=PAYLOAD['claims'][0]['text'],evidence_0=BODY)
        self.assertEqual(self.post(item.id,'edit',**fields).status_code,302)
        self.assertEqual(item.status,'generating'); self.assertEqual(item.version,2)
        self.assertFalse(service.current_version(item).report['ready'])
        self.assertEqual(self.approve(item).status_code,409)
        self.process(); self.assertEqual(item.version,3)
        self.assertEqual(service.current_version(item).payload['title'],'Plantas e luz')
        self.assertEqual(self.post(item.id,'restore',restore_version='1').status_code,302)
        self.assertEqual(item.version,4); self.process(); self.assertEqual(item.version,5)
        self.assertEqual(service.current_version(item).payload['title'],PAYLOAD['title'])
        self.assertEqual(Version.query.filter_by(material_id=item.id,number=1).one().payload,PAYLOAD)

    def test_source_changes_block_approval_exports_and_tracking(self):
        item = self.ready(); self.approve(item)
        self.article.body += ' Informação nova.'; db.session.commit()
        self.assertEqual(self.approve(item).status_code,409)
        self.assertEqual(self.client.get(f'/admin/divulgacao/{item.id}/descarregar').status_code,409)
        self.assertEqual(self.client.get('/divulgacao/' + item.token).status_code,404)

    def test_draft_source_cannot_be_selected_or_exported(self):
        item = self.ready(); self.approve(item)
        self.article.status = 'draft'; db.session.commit()
        with self.assertRaises(GenerationError): self.create()
        db.session.rollback()
        self.assertEqual(self.client.get('/divulgacao/' + item.token).status_code,404)
        self.assertNotIn(self.article.title, self.client.get('/admin/divulgacao/').text)

    def test_link_http_failure_and_missing_human_confirmation_block(self):
        item = self.ready()
        self.assertEqual(self.post(item.id,'approve').status_code,409)
        with patch('dissemination_service.requests.get',return_value=Mock(status_code=404)):
            self.assertEqual(self.post(item.id,'approve',human_review='yes').status_code,409)

    def test_stale_form_cannot_decide_new_version(self):
        item = self.ready()
        response = self.client.post(f'/admin/divulgacao/{item.id}/accao',data=dict(csrf_token='dc-test',version='0',action='reject',note='Old form'))
        self.assertEqual(response.status_code,409); self.assertEqual(item.status,'review')

    def test_daily_budget_and_job_caps_reject_without_provider_calls(self):
        with patch.dict(os.environ,{'DISSEMINATION_DAILY_UNITS':'10'}):
            self.create()
            with self.assertRaises(GenerationError): self.create()
            db.session.rollback()
        self.assertEqual(Job.query.count(),1)
        self.assertEqual(db.session.get(Budget,utcnow().date()).units,10)

    def test_no_configuration_no_generation(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
            self.assertEqual(self.client.post('/admin/divulgacao/gerar',data=dict(csrf_token='dc-test',source=f'portal:{self.article.id}',network='x',kind='text')).status_code,400)
        self.assertEqual(Job.query.count(),0)

    def test_worker_failure_redacts_sensitive_errors_and_no_automatic_retry(self):
        item = self.create()
        with patch('dissemination_ai.generate',side_effect=RuntimeError('secret-sk-123')):
            service.process_one()
        self.assertEqual(item.status,'failed')
        self.assertNotIn('secret-sk',item.error)
        self.assertFalse(service.process_one())
        self.assertEqual(Job.query.one().status,'failed')

    def test_worker_expiry_marks_interrupted_jobs_failed(self):
        item = self.create(); job = Job.query.one()
        job.status='running'; job.started_at=utcnow()-timedelta(hours=1); db.session.commit()
        service.expire_jobs()
        self.assertEqual(item.status,'failed')
        self.assertEqual(job.status,'failed')
        self.assertFalse(service.process_one())

    def test_tracking_excludes_head_bots_and_identified_prefetch(self):
        item = self.ready(); self.approve(item); path='/divulgacao/'+item.token
        self.client.head(path,headers={'User-Agent':'Mozilla/5.0'})
        self.client.get(path,headers={'User-Agent':'Googlebot'})
        self.client.get(path,headers={'User-Agent':'Mozilla/5.0','Sec-Purpose':'prefetch'})
        self.assertEqual(Click.query.count(),0)
        self.client.get(path,headers={'User-Agent':'Mozilla/5.0'})
        self.assertEqual(Click.query.count(),1)

    def test_no_cross_network_or_arbitrary_publication_url(self):
        item = self.ready(); self.approve(item)
        for address in ('https://evil.test/post','https://facebook.com.evil.test/','http://facebook.com/','https://facebook.com@evil.test/'):
            self.assertEqual(self.post(item.id,'published',publication_url=address).status_code,409)
        self.assertEqual(item.status,'approved')

    def test_unauthenticated_and_legacy_secondary_have_no_access(self):
        self.assertEqual(app.test_client().get('/admin/divulgacao/').status_code,302)
        account=AdminUser(username=secrets.token_hex(6),display_name='Legacy account',password_hash='fixture',
            active=True,is_superadmin=False,two_factor_enabled=True,totp_secret='JBSWY3DPEHPK3PXP')
        db.session.add(account);db.session.commit();self.signin(account)
        self.assertEqual(self.client.get('/admin/divulgacao/').status_code,403)
        self.assertEqual(self.client.post('/admin/divulgacao/gerar',data={'csrf_token':'dc-test'}).status_code,403)

    def test_explicit_manage_permission_does_not_allow_approval_or_export(self):
        item=self.ready()
        token=secrets.token_hex(5)
        account=AdminUser(username='dc-'+token,display_name='Gestor',password_hash='fixture',governance_managed=True,
            two_factor_enabled=True,totp_secret='JBSWY3DPEHPK3PXP')
        role=TeamRole(code='dc-'+token,name='Gestor de divulgação',permissions=['dissemination.manage'])
        member=TeamMember(name='Gestor',email=token+'@example.test',admin=account,status='active',accepted_at=utcnow())
        db.session.add_all([account,role,member]);db.session.flush()
        db.session.add(TeamAppointment(member=member,role=role,starts_on=date.today()-timedelta(days=1),active=True));db.session.commit()
        self.signin(account)
        self.assertEqual(self.client.get('/admin/divulgacao/').status_code,200)
        self.assertEqual(self.approve(item).status_code,403)
        self.assertEqual(self.client.get(f'/admin/divulgacao/{item.id}/descarregar').status_code,403)

    def test_csrf_and_tampered_asset_are_blocked(self):
        item=self.ready('curiosity')
        self.assertEqual(self.client.post(f'/admin/divulgacao/{item.id}/accao',data={'action':'approve','version':item.version}).status_code,400)
        asset=service.current_version(item).assets[-1]
        (service.asset_root()/asset['name']).write_bytes(b'tampered')
        self.assertEqual(self.approve(item).status_code,409)

    def test_published_scientific_article_source_supported_without_mutation(self):
        token=secrets.token_hex(6)
        item=Journal(title='Revista '+token,article_title='Fotossíntese',slug='dc-journal-'+token,
            field='Biologia',description=BODY,content_markdown=BODY,published=True)
        db.session.add(item);db.session.commit()
        source=service.snapshot('journal',item.id)
        self.assertEqual(source['path'],'/revistas/'+item.slug)
        self.assertEqual(item.content_markdown,BODY)
        item.published=False;db.session.commit()
        with self.assertRaises(GenerationError):service.snapshot('journal',item.id)

    def test_dashboard_detail_and_historical_versions_render(self):
        item=self.ready('curiosity')
        for path in ('/admin/divulgacao/',f'/admin/divulgacao/{item.id}'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200,response.text[:200])
            self.assertIn('dissemination.css',response.text)
        self.assertEqual(self.client.get(f'/admin/divulgacao/{item.id}/imagem/1/1').status_code,200)
        self.assertEqual(self.client.get(f'/admin/divulgacao/{item.id}/imagem/1/999').status_code,404)

    def test_carousel_composes_all_slides_and_instagram_dimensions(self):
        item=self.create('carousel','instagram')
        payload=copy.deepcopy(PAYLOAD);payload['slides']=payload['slides']*3
        raw=io.BytesIO();Image.new('RGB',(1024,1024),'#d3e6cf').save(raw,format='PNG')
        with patch('dissemination_ai.illustration',return_value=raw.getvalue()):self.process(payload)
        assets=[asset for asset in service.current_version(item).assets if asset['role']=='slide']
        self.assertEqual(len(assets),3)
        for asset in assets:
            with Image.open(io.BytesIO(service.read_asset(asset))) as image:self.assertEqual(image.size,(1080,1350))

    def test_x_export_length_includes_title_caption_and_campaign_url(self):
        item=self.create(network='x');payload=copy.deepcopy(PAYLOAD)
        payload['title']='T'*90;payload['caption']='C'*180
        with self.assertRaises(GenerationError):service.validate_payload(payload,service.snapshot('portal',self.article.id),item)

    def test_documentation_download_is_private_and_available(self):
        self.assertEqual(app.test_client().get('/admin/divulgacao/documentacao').status_code,302)
        response=self.client.get('/admin/divulgacao/documentacao')
        self.assertEqual(response.status_code,200)
        self.assertIn('processar-divulgacao',response.text)
        response.close()

    def test_provider_errors_are_sanitized_and_do_not_follow_redirects(self):
        from dissemination_ai import api
        with patch('dissemination_ai.requests.post',return_value=Mock(status_code=429,text='secret-key-body')) as supplier:
            with self.assertRaises(GenerationError) as failure:api('chat/completions',{})
        self.assertNotIn('secret-key-body',str(failure.exception))
        self.assertFalse(supplier.call_args.kwargs['allow_redirects'])


if __name__ == '__main__': unittest.main()
