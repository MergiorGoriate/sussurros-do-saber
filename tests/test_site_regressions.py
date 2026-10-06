import io
import os
import secrets
import time
import unittest
from unittest.mock import Mock, patch
from bs4 import BeautifulSoup
from werkzeug.datastructures import FileStorage
from app import app, seed_database
from models import Article, Author, Category, db
from storage import upload_article_video, VideoUploadError
from extensions import limiter


from security_test_support import authenticate_test_session

class SiteRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        with app.app_context():
            seed_database()

    def setUp(self):
        self.rate_limit_patch = patch.object(limiter, "enabled", False)
        self.rate_limit_patch.start()
        self.context = app.app_context()
        self.context.push()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()
        self.rate_limit_patch.stop()

    def admin(self):
        with self.client.session_transaction() as session:
            session['admin_authenticated'] = True
            session['admin_superuser'] = True
            session['admin_last_activity_at'] = time.time()
            session['csrf_token'] = 'regression-csrf'

            authenticate_test_session(session)
    def fields(self):
        return dict(csrf_token='regression-csrf', title='Título de regressão '+secrets.token_hex(4),
            summary='Resumo introduzido pelo editor.',body='Texto científico que deve permanecer no formulário. '*3,
            references='Referência que deve ser preservada.',keywords='ciência',doi='',slug='',
            status='draft',read_minutes='7',author_id=str(Author.query.first().id),
            category_id=str(Category.query.first().id),featured='on')

    def test_json_wrong_types_return_validation_errors(self):
        for path, field in [('/api/newsletter','email'),('/api/assistente','message'),('/api/contacto','name')]:
            for payload in [['invalid'], {field:None}, {field:123}, {field:{'bad':'value'}}]:
                with self.subTest(path=path,payload=payload):
                    response = self.client.post(path,json=payload)
                    self.assertEqual(response.status_code,400)
                    self.assertFalse(response.json['ok'])

    def test_invalid_favorite_ids_do_not_return_unrelated_articles(self):
        for ids in ['²', '99999999999999999999999999999999','2147483648','invalid','']:
            with self.subTest(ids=ids):
                response = self.client.get('/api/artigos',query_string={'ids':ids})
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.json,[])

    def test_unexpected_assistant_response_is_controlled(self):
        for payload in [['unexpected'], {'ok':True}, {'ok':True,'answer':123}]:
            response = Mock()
            response.json.return_value = payload
            with patch('app.requests.post',return_value=response):
                result = self.client.post('/api/assistente',json={'message':'Pergunta científica'})
            self.assertEqual(result.status_code,502)
            self.assertFalse(result.json['ok'])

    def test_form_retains_text_after_upload_error(self):
        self.admin()
        data=self.fields()
        data['image_file']=(io.BytesIO(b'not-image'),'photo.png')
        response=self.client.post('/admin/artigos/novo',data=data)
        self.assertEqual(response.status_code,200)
        html=BeautifulSoup(response.data,'html.parser')
        for name in ['title','summary','body','references','keywords','read_minutes']:
            element=html.select_one('[name="'+name+'"]')
            self.assertEqual(element.get('value',element.get_text()),data[name])
        self.assertIsNotNone(html.select_one('[name="featured"][checked]'))
        self.assertIsNone(Article.query.filter_by(title=data['title']).first())

    def test_schedule_and_field_limits_are_checked_before_upload(self):
        self.admin()
        for extra in [{'status':'scheduled','scheduled_at':''},{'keywords':'x'*501},{'body':'x'*400001}]:
            data=self.fields()
            data.update(extra)
            data['cover_video_file']=(io.BytesIO(b'video'),'video.mp4')
            with patch('admin.upload_article_video') as upload:
                response=self.client.post('/admin/artigos/novo',data=data)
            self.assertEqual(response.status_code,200)
            upload.assert_not_called()
            self.assertIsNone(Article.query.filter_by(title=data['title']).first())

    def test_large_upload_has_localized_json_and_html(self):
        previous=app.config['MAX_CONTENT_LENGTH']
        app.config['MAX_CONTENT_LENGTH']=32
        self.admin()
        try:
            response=self.client.post('/admin/api/videos',data={'video':(io.BytesIO(b'x'*200),'video.mp4')})
            self.assertEqual(response.status_code,413)
            self.assertIn('50 MB',response.json['error'])
            response=self.client.post('/admin/artigos/novo',data={'body':'x'*200})
            self.assertEqual(response.status_code,413)
            self.assertIn('Carregamento demasiado grande'.encode(),response.data)
        finally:
            app.config['MAX_CONTENT_LENGTH']=previous

    def test_video_formats_and_storage_failures_are_validated(self):
        credentials={key:'test-value' for key in ['CLOUDINARY_CLOUD_NAME','CLOUDINARY_API_KEY','CLOUDINARY_API_SECRET']}
        for name,header in [('sample.mp4',b'\x00\x00\x00\x18ftypisom'),
                            ('sample.webm',b'\x1a\x45\xdf\xa3payload'),('sample.ogg',b'OggSpayload')]:
            with self.subTest(name=name),patch.dict(os.environ,credentials),patch('storage.cloudinary.uploader.upload',return_value={'secure_url':'https://example.org/video.mp4'}) as upload:
                self.assertEqual(upload_article_video(FileStorage(stream=io.BytesIO(header),filename=name)),'https://example.org/video.mp4')
                self.assertEqual(upload.call_args.kwargs['resource_type'],'video')
                self.assertEqual(upload.call_args.kwargs['format'],'mp4')
        with self.assertRaises(VideoUploadError):
            upload_article_video(FileStorage(stream=io.BytesIO(b'garbage'),filename='fake.mp4'))
        with patch.dict(os.environ,credentials),patch('storage.cloudinary.uploader.upload',return_value={}):
            with self.assertRaises(VideoUploadError):
                upload_article_video(FileStorage(stream=io.BytesIO(b'OggSpayload'),filename='sample.ogg'))

    def test_video_size_limit_rejects_before_storage(self):
        with patch('storage.MAX_VIDEO_BYTES',8),patch('storage.cloudinary.uploader.upload') as upload:
            with self.assertRaises(VideoUploadError):
                upload_article_video(FileStorage(stream=io.BytesIO(b'OggS12345'),filename='sample.ogg'))
            upload.assert_not_called()

