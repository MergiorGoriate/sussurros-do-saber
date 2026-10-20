import io
import json
import re
import secrets
import time
import unittest
import zipfile
from unittest.mock import patch, MagicMock
from PIL import Image
from werkzeug.security import generate_password_hash
from werkzeug.datastructures import FileStorage
from app import app, seed_database, render_journal_pdf
from models import Journal, db
from submission_models import (Researcher, SubmissionSetting, Manuscript, ManuscriptAuthor, ManuscriptVersion,
                               ManuscriptFile, EditorialEvent, EditorialNotification, PublicationAsset)
from submissions import account_token, REQUIRED_DECLARATIONS, OPTIONAL_DECLARATIONS
from submission_uploads import validate_upload


def docx_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types/>')
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Conteúdo científico importado.</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Grupo</w:t></w:r></w:p></w:tc></w:tr><w:tr><w:tc><w:p><w:r><w:t>A</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>')
    return buffer.getvalue()


from security_test_support import authenticate_test_session

class SubmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        with app.app_context():
            seed_database()

    def setUp(self):
        self.context = app.app_context()
        self.context.push()
        self.client = app.test_client()
        token = secrets.token_hex(6)
        self.owner = Researcher(name='Investigador', email=token+'@example.org', password_hash=generate_password_hash('secure-password-123'), verified=True, token_nonce=token)
        self.other = Researcher(name='Outro', email='other-'+token+'@example.org', password_hash='unused', verified=True, token_nonce=token+'x')
        self.journal = Journal(title='Revista '+token, slug='submission-'+token, field='Biologia', description='Revista de teste científico.')
        db.session.add_all([self.owner,self.other,self.journal]);db.session.flush()
        self.setting = SubmissionSetting(journal_id=self.journal.id, enabled=True, article_types='Artigo original\nRevisão', main_formats='docx,pdf,txt', editorial_email='editorial@example.org')
        db.session.add(self.setting);db.session.commit()
        self.sign_in()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    def sign_in(self, account=None):
        account=account or self.owner
        with self.client.session_transaction() as session:
            session.clear();session['researcher_id']=account.id;session['researcher_nonce']=account.token_nonce;session['csrf_token']='test-token'

    def admin(self):
        with self.client.session_transaction() as session:
            session.clear();session['admin_authenticated']=True;session['admin_last_activity_at']=time.time();session['admin_superuser']=True;session['csrf_token']='test-token'

            authenticate_test_session(session)
    def post(self, path, data=None, **kwargs):
        return self.client.post(path, data={'csrf_token':'test-token', **(data or {})}, **kwargs)

    def draft(self):
        response=self.post('/submissoes/nova',{'journal_id':self.journal.id})
        self.assertEqual(response.status_code,302)
        return Manuscript.query.filter_by(owner_id=self.owner.id).order_by(Manuscript.id.desc()).first()

    def complete(self):
        manuscript=self.draft()
        base=f'/submissoes/{manuscript.id}/etapa/'
        self.post(base+'1',{'journal_id':self.journal.id,'article_type':'Artigo original','field':'Biologia','language':'Português'})
        self.post(base+'2',{'author_name':['Investigador','Coautor'],'author_email':[self.owner.email,'coautor@example.org'],
                            'author_orcid':['0000-0002-1825-0097',''],'author_affiliation':['UniRovuma',''], 'corresponding':'0'})
        self.post(base+'3',{'title':'Estudo científico','summary':'Resumo científico','keywords':'biologia; ciência','abstract':'Scientific abstract','abstract_keywords':'biology; science','author_contributions':'Contribuição informada','references':'Referência científica.'})
        self.post(f'/submissoes/{manuscript.id}/ficheiros',{'kind':'main','file':(io.BytesIO(docx_bytes()),'manuscript.docx')})
        declarations={key:'on' for key in REQUIRED_DECLARATIONS}
        declarations.update({key+'_applicable':'no' for key in OPTIONAL_DECLARATIONS})
        declarations.update({'funding_applicable':'yes','funding_text':'Financiamento declarado'})
        self.post(base+'5', declarations)
        db.session.refresh(manuscript)
        return manuscript

    def submitted(self):
        manuscript=self.complete()
        response=self.post(f'/submissoes/{manuscript.id}/confirmar',{'confirm':'on'})
        self.assertEqual(response.status_code,302)
        db.session.refresh(manuscript)
        self.assertEqual(manuscript.status,'submitted')
        return manuscript

    def test_draft_continue_seven_steps_and_private_responses(self):
        manuscript=self.draft()
        self.assertIsNone(manuscript.code)
        for step in range(1,8):
            response=self.client.get(f'/submissoes/{manuscript.id}/etapa/{step}')
            self.assertEqual(response.status_code,200)
            self.assertIn('no-store',response.headers['Cache-Control'])
            self.assertIn('noindex',response.headers['X-Robots-Tag'])
            self.assertNotIn(b'googlesyndication',response.data)
        self.post(f'/submissoes/{manuscript.id}/etapa/3',{'title':'Rascunho guardado','action':'draft'})
        response=self.client.get('/submissoes/')
        self.assertIn('Rascunho guardado'.encode(),response.data)
        self.assertEqual(manuscript.status,'draft')

    def test_incomplete_csrf_or_unverified_cannot_submit(self):
        manuscript=self.draft()
        self.post(f'/submissoes/{manuscript.id}/confirmar',{'confirm':'on'})
        self.assertEqual(manuscript.status,'draft')
        self.assertEqual(self.client.post(f'/submissoes/{manuscript.id}/confirmar',data={'confirm':'on'}).status_code,400)
        self.owner.verified=False;db.session.commit()
        self.assertIn('/confirmacao',self.client.get('/submissoes/nova').location)

    def test_final_submission_idempotent_snapshot_and_no_direct_edits(self):
        manuscript=self.submitted()
        code=manuscript.code
        count=EditorialNotification.query.count()
        self.post(f'/submissoes/{manuscript.id}/confirmar',{'confirm':'on'})
        self.assertEqual(manuscript.code,code)
        self.assertEqual(EditorialNotification.query.count(),count)
        self.assertRegex(code,r'^RSS-\d{4}-\d{6,}$')
        version=manuscript.versions[0]
        self.assertEqual(version.snapshot['title'],'Estudo científico')
        self.assertTrue(version.finalized_at)
        self.post(f'/submissoes/{manuscript.id}/etapa/3',{'title':'Alteração indevida'})
        self.assertEqual(manuscript.title,'Estudo científico')
        self.assertEqual(self.post(f'/submissoes/{manuscript.id}/ficheiros',{'kind':'main','file':(io.BytesIO(docx_bytes()),'new.docx')}).status_code,409)

    def test_other_author_cannot_access_metadata_files_or_mutations(self):
        manuscript=self.submitted();file=ManuscriptFile.query.join(ManuscriptVersion).filter(ManuscriptVersion.manuscript_id==manuscript.id).first()
        self.sign_in(self.other)
        for path in (f'/submissoes/{manuscript.id}',f'/submissoes/{manuscript.id}/etapa/1',f'/submissoes/ficheiros/{file.id}'):
            self.assertEqual(self.client.get(path).status_code,404)
        self.assertEqual(self.post(f'/submissoes/{manuscript.id}/confirmar',{'confirm':'on'}).status_code,404)
        self.assertEqual(self.post(f'/submissoes/ficheiros/{file.id}/remover').status_code,404)
        self.assertEqual(self.client.get('/admin/submissoes').status_code,302)
        with self.client.session_transaction() as session:session.clear()
        self.assertEqual(self.client.get(f'/submissoes/ficheiros/{file.id}').status_code,404)

    def test_download_requires_owner_and_is_attachment(self):
        manuscript=self.complete();file=ManuscriptFile.query.join(ManuscriptVersion).filter(ManuscriptVersion.manuscript_id==manuscript.id).first()
        response=self.client.get(f'/submissoes/ficheiros/{file.id}')
        self.assertEqual(response.status_code,200)
        self.assertIn('attachment',response.headers['Content-Disposition'])
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertEqual(response.data,file.payload)

    def test_configurable_types_and_orcid_validation(self):
        manuscript=self.draft()
        self.post(f'/submissoes/{manuscript.id}/etapa/1',{'journal_id':self.journal.id,'article_type':'Tipo não autorizado','field':'Biologia','language':'Português'})
        self.assertEqual(manuscript.article_type,'')
        self.post(f'/submissoes/{manuscript.id}/etapa/2',{'author_name':'Investigador','author_email':self.owner.email,'author_orcid':'0000-0002-1825-0098','corresponding':'0'})
        self.assertEqual(manuscript.authors,[])
        self.admin()
        self.assertEqual(self.client.get('/admin/submissoes/configuracao').status_code,200)
        self.post('/admin/submissoes/configuracao',{'journal_id':self.journal.id,'article_types':'Ensaio','main_formats':['docx'],'editorial_email':'editor@example.org','enabled':'on'})
        db.session.refresh(self.setting)
        self.assertEqual(self.setting.article_types,'Ensaio')

    def test_editorial_decisions_internal_notes_revision_and_publication(self):
        manuscript=self.submitted();first_file=manuscript.versions[0].files[0];first_hash=first_file.sha256
        self.admin()
        self.assertEqual(self.client.get('/admin/submissoes').status_code,200)
        self.assertEqual(self.client.get(f'/admin/submissoes/{manuscript.id}').status_code,200)
        self.post(f'/admin/submissoes/{manuscript.id}',{'action':'accepted','note':'Salto não autorizado'})
        self.assertEqual(manuscript.status,'submitted')
        self.post(f'/admin/submissoes/{manuscript.id}',{'action':'screening','note':'Iniciar triagem'})
        self.post(f'/admin/submissoes/{manuscript.id}',{'action':'note','note':'NOTA INTERNA CONFIDENCIAL'})
        self.post(f'/admin/submissoes/{manuscript.id}',{'action':'revision_requested','note':'Rever os métodos'})
        self.sign_in()
        page=self.client.get(f'/submissoes/{manuscript.id}')
        self.assertIn(b'Rever os m',page.data)
        self.assertNotIn(b'NOTA INTERNA CONFIDENCIAL',page.data)
        self.post(f'/submissoes/{manuscript.id}/ficheiros',{'kind':'main','file':(io.BytesIO(docx_bytes()),'revised.docx')})
        self.post(f'/submissoes/{manuscript.id}/nova-versao',{'response_to_editor':'Métodos revistos.'})
        self.post(f'/submissoes/{manuscript.id}/nova-versao',{'response_to_editor':'Duplicado'})
        self.assertEqual(manuscript.current_version,2)
        self.assertEqual(first_file.sha256,first_hash)
        self.assertEqual(len(manuscript.versions),2)
        self.admin()
        self.post(f'/admin/submissoes/{manuscript.id}',{'action':'reevaluation','note':'Reavaliar'})
        self.post(f'/admin/submissoes/{manuscript.id}',{'action':'accepted','note':'Aceite após revisão'})
        source_title=self.journal.title
        self.post(f'/admin/submissoes/{manuscript.id}/preparar')
        db.session.refresh(manuscript)
        publication=manuscript.publication
        self.assertEqual(manuscript.status,'production')
        self.assertFalse(publication.published)
        self.assertEqual(self.journal.title,source_title)
        self.assertIn('Conteúdo científico',publication.content_markdown)
        self.assertIn('| Grupo |',publication.content_markdown)
        self.assertEqual(publication.references,'Referência científica.')
        self.assertEqual(publication.author_contributions,'Contribuição informada')
        self.assertEqual(publication.funding,'Financiamento declarado')
        self.assertEqual(publication.article_title,manuscript.title)
        self.assertEqual(publication.authors_data.count('Investigador'),1)
        publication_id=publication.id
        self.post(f'/admin/submissoes/{manuscript.id}/preparar')
        self.assertEqual(manuscript.publication_id,publication_id)
        self.assertEqual(self.client.get(f'/admin/revistas/{publication_id}/editar').status_code,200)
        self.post(f'/admin/revistas/{publication_id}/publicacao')
        self.assertEqual(manuscript.status,'published')
        self.sign_in()
        self.assertEqual(self.client.get(f'/submissoes/{manuscript.id}').status_code,200)
        self.assertEqual(self.client.get('/revistas/'+publication.slug).status_code,200)

    def test_figure_private_until_explicit_publication_and_embedded_in_pdf(self):
        manuscript=self.complete()
        image=io.BytesIO();Image.new('RGB',(180,100),'blue').save(image,'PNG')
        self.post(f'/submissoes/{manuscript.id}/ficheiros',{'kind':'figure','file':(io.BytesIO(image.getvalue()),'figure.png')})
        self.post(f'/submissoes/{manuscript.id}/confirmar',{'confirm':'on'})
        self.admin()
        self.post(f'/admin/submissoes/{manuscript.id}',{'action':'screening','note':'Triagem'})
        self.post(f'/admin/submissoes/{manuscript.id}',{'action':'accepted','note':'Aceite'})
        self.post(f'/admin/submissoes/{manuscript.id}/preparar')
        asset=PublicationAsset.query.filter_by(journal_id=manuscript.publication_id).first()
        self.assertIsNotNone(asset)
        response=self.client.get(f'/submissoes/figuras/{asset.id}')
        self.assertEqual(response.status_code,200)
        with app.test_request_context():
            from flask import session
            session['admin_authenticated']=True;session['admin_last_activity_at']=time.time()
            authenticate_test_session(session)
            pdf=render_journal_pdf(manuscript.publication).data
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(pdf))
        image_count=sum(len(page.images) for page in reader.pages)
        self.assertGreaterEqual(image_count,2)
        self.assertNotIn('imagem indisponível', '\n'.join(page.extract_text() for page in reader.pages))
        self.sign_in()
        self.assertEqual(self.client.get(f'/submissoes/figuras/{asset.id}').status_code,404)
        self.admin();self.post(f'/admin/revistas/{manuscript.publication_id}/publicacao')
        with self.client.session_transaction() as session:session.clear()
        self.assertEqual(self.client.get(f'/submissoes/figuras/{asset.id}').status_code,200)
        original=ManuscriptFile.query.join(ManuscriptVersion).filter(ManuscriptVersion.manuscript_id==manuscript.id,ManuscriptFile.kind=='main').first()
        self.assertEqual(self.client.get(f'/submissoes/ficheiros/{original.id}').status_code,404)

    def test_administrator_must_complete_two_factor_before_private_download(self):
        from models import AdminUser
        manuscript=self.complete()
        file=ManuscriptFile.query.join(ManuscriptVersion).filter(ManuscriptVersion.manuscript_id==manuscript.id).first()
        administrator=AdminUser(username='submission-2fa-'+secrets.token_hex(6),display_name='Editor',password_hash='unused',active=True,two_factor_enabled=False)
        db.session.add(administrator);db.session.commit()
        self.admin()
        with self.client.session_transaction() as session:
            session['admin_id']=administrator.id;session['admin_2fa_verified']=True
        self.assertEqual(self.client.get(f'/submissoes/ficheiros/{file.id}').status_code,404)
        administrator.two_factor_enabled=True;db.session.commit()
        with self.client.session_transaction() as session:
            authenticate_test_session(session)
        self.assertEqual(self.client.get(f'/submissoes/ficheiros/{file.id}').status_code,200)

    def test_account_confirmation_reset_and_outbox(self):
        with self.client.session_transaction() as session:session.clear();session['csrf_token']='test-token'
        email=secrets.token_hex(8)+'@example.org'
        self.post('/submissoes/criar-conta',{'name':'Nova investigadora','email':email,'password':'a-secure-password'})
        account=Researcher.query.filter_by(email=email).one()
        self.assertFalse(account.verified)
        token=account_token(account,'verify')
        self.assertEqual(self.client.get('/submissoes/confirmar/'+token).status_code,200)
        self.post('/submissoes/confirmar/'+token)
        self.assertTrue(account.verified)
        reset=account_token(account,'reset')
        self.post('/submissoes/recuperar/'+reset,{'password':'another-secure-password'})
        self.assertEqual(self.client.get('/submissoes/recuperar/'+reset).status_code,400)
        self.assertTrue(EditorialNotification.query.filter_by(recipient=email).first())
        runner=app.test_cli_runner()
        with patch.dict('os.environ',{'SMTP_HOST':'smtp.example.org','SMTP_FROM':'editorial@example.org','SMTP_USERNAME':'','SMTP_TLS':'true'}),patch('submissions.smtplib.SMTP') as smtp:
            smtp.return_value.__enter__.return_value.send_message.return_value={}
            result=runner.invoke(args=['enviar-notificacoes','--limit','500'])
        self.assertEqual(result.exit_code,0,result.output)
        self.assertTrue(EditorialNotification.query.filter_by(recipient=email).first().sent_at)

    def test_upload_integrity_mime_limits_and_executable_rejection(self):
        for name,data,mime in [('fake.docx',b'not-a-zip','application/octet-stream'),('bad.pdf',b'%PDF-1.7\n%%EOF','application/pdf'),
                              ('fake.png',b'not-an-image','image/png'),('script.html',b'<script>','text/html'),
                              ('wrong.txt',b'valid text','image/png'),('binary.txt',b'\x00','text/plain')]:
            with self.subTest(name=name),self.assertRaises(ValueError):
                validate_upload(FileStorage(stream=io.BytesIO(data),filename=name,content_type=mime),'supplement','docx,pdf')
        with self.assertRaises(ValueError):
            validate_upload(FileStorage(stream=io.BytesIO(b'a'*(8*1024*1024+1)),filename='large.txt',content_type='text/plain'),'main','txt')
        data=validate_upload(FileStorage(stream=io.BytesIO(docx_bytes()),filename='../../article.docx',content_type='application/octet-stream'),'main','docx')
        self.assertNotIn('/',data['original_name'])
        self.assertNotEqual(data['internal_name'],data['original_name'])

    def test_existing_preparation_proposal_and_journal_functions_preserved(self):
        response=self.client.get('/revistas')
        self.assertIn(b'/servicos/edicao-cientifica',response.data)
        self.assertIn(b'Preparar manuscrito',response.data)
        self.assertIn(b'/submissoes/nova',response.data)
        self.assertIn(b'/contacto?assunto=',response.data)
        self.assertEqual(self.client.get('/servicos/edicao-cientifica').status_code,200)

if __name__=='__main__':unittest.main()
