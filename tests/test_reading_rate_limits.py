"""Article reading is unlimited; mutations retain their existing protection."""
import secrets
import unittest
from flask import Flask, redirect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from extensions import default_rate_limits


class ReadingRateLimitTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        self.app.config.update(TESTING=True)
        self.limiter=Limiter(key_func=get_remote_address,app=self.app,
            default_limits=[default_rate_limits],storage_uri='memory://',key_prefix=secrets.token_hex(6))
        def reading(slug):return 'Article '+slug
        def journal(slug):return 'Journal '+slug
        def api():return 'API'
        def login():return 'Login'
        def comment():return 'Comment'
        self.app.add_url_rule('/artigo/<slug>',endpoint='article',
            view_func=reading,methods=['GET','HEAD','POST'])
        self.app.add_url_rule('/en/artigo/<slug>',endpoint='article',
            view_func=reading,methods=['GET','HEAD'])
        self.app.add_url_rule('/revistas/<slug>',endpoint='journal_detail',
            view_func=journal,methods=['GET','HEAD'])
        self.app.add_url_rule('/api/reading',endpoint='api_reading',view_func=api)
        self.app.add_url_rule('/admin/login',endpoint='login',methods=['POST'],
            view_func=self.limiter.limit('5 per minute; 20 per hour')(login))
        self.app.add_url_rule('/comentario',endpoint='comment',methods=['POST'],
            view_func=self.limiter.limit('5 per hour')(comment))
        def choose_language(locale):
            response = redirect('/en/' if locale == 'en' else '/')
            response.set_cookie('sds_language', locale)
            return response
        self.app.add_url_rule('/idioma/<locale>', endpoint='language.choose',
            view_func=choose_language, methods=['GET', 'HEAD', 'POST'])
        self.client=self.app.test_client()

    def test_article_reading_exceeds_previous_hourly_daily_and_minute_limits(self):
        for index in range(400):
            self.assertEqual(self.client.get('/artigo/'+str(index)).status_code,200)
            self.assertEqual(self.client.head('/en/artigo/'+str(index)).status_code,200)
            self.assertEqual(self.client.get('/revistas/'+str(index)).status_code,200)

    def test_posts_and_apis_retain_original_default_limits(self):
        for _ in range(100):
            self.assertEqual(self.client.post('/artigo/test').status_code,200)
            self.assertEqual(self.client.get('/api/reading').status_code,200)
        self.assertEqual(self.client.post('/artigo/test').status_code,429)
        self.assertEqual(self.client.get('/api/reading').status_code,429)

    def test_login_and_comment_limits_are_unchanged(self):
        for path in ('/admin/login','/comentario'):
            for _ in range(5):self.assertEqual(self.client.post(path).status_code,200)
            self.assertEqual(self.client.post(path).status_code,429)

    def test_language_choice_exceeds_previous_limits_and_keeps_redirect_and_cookie(self):
        for index in range(310):
            locale = 'en' if index % 2 == 0 else 'pt'
            response = self.client.get('/idioma/' + locale)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.location, '/en/' if locale == 'en' else '/')
            self.assertIn('sds_language=' + locale, response.headers['Set-Cookie'])
        self.assertEqual(self.client.head('/idioma/en').status_code, 302)

    def test_language_post_keeps_default_limits(self):
        for _ in range(100):
            self.assertEqual(self.client.post('/idioma/en').status_code, 302)
        self.assertEqual(self.client.post('/idioma/en').status_code, 429)
