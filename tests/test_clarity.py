import os
import unittest
from unittest.mock import patch

from flask import Flask, g, session
from clarity_tracking import project_id


class ClarityPolicyTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        self.app.secret_key='isolated-policy-test'
        for endpoint,path in [('home','/'),('articles','/artigos'),('private','/conta'),
                              ('article','/artigo/teste'),('privacy','/politica-de-privacidade')]:
            self.app.add_url_rule(path,endpoint,lambda:'OK',methods=['GET','POST'])

    def test_public_pages_and_only_confirmed_public_articles(self):
        for path in ['/','/artigos','/politica-de-privacidade']:
            with self.app.test_request_context(path):
                self.assertEqual(project_id(),'zdbchcjjtg')
        with self.app.test_request_context('/artigo/teste'):
            self.assertEqual(project_id(),'')
            g.google_cmp_public_content=True
            self.assertEqual(project_id(),'zdbchcjjtg')

    def test_private_queries_methods_and_authenticated_sessions_are_excluded(self):
        for path in ['/conta','/artigos?q=private','/?email=private','/missing']:
            with self.app.test_request_context(path):self.assertEqual(project_id(),'')
        with self.app.test_request_context('/',method='POST'):self.assertEqual(project_id(),'')
        for key in ['admin_authenticated','admin_id','pending_2fa_username','researcher_id']:
            with self.app.test_request_context('/'):
                session[key]=1
                self.assertEqual(project_id(),'')

    def test_operator_can_disable_or_change_public_project_identifier(self):
        for value,expected in [('', ''),('bad/id',''),('another123','another123')]:
            with patch.dict(os.environ,{'CLARITY_PROJECT_ID':value}),self.app.test_request_context('/'):
                self.assertEqual(project_id(),expected)


class ClarityPageTests(unittest.TestCase):
    def test_template_and_csp_allow_only_public_analytics(self):
        from app import app
        client=app.test_client()
        for path in ['/','/artigos','/en/artigos']:
            response=client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertIn('js/clarity.js',response.text)
            self.assertIn('data-project-id="zdbchcjjtg"',response.text)
            self.assertIn('https://*.clarity.ms https://c.bing.com',response.headers['Content-Security-Policy'])
        for path in ['/admin/login','/conta/biblioteca','/contacto','/artigos?q=private','/artigo/not-found-clarity']:
            response=client.get(path)
            self.assertNotIn('js/clarity.js',response.text)
            self.assertNotIn('https://*.clarity.ms',response.headers.get('Content-Security-Policy',''))
        with patch.dict(os.environ,{'CLARITY_PROJECT_ID':''}):
            self.assertNotIn('js/clarity.js',client.get('/').text)

    def test_privacy_disclosure_is_present_in_both_languages(self):
        from app import app
        client=app.test_client()
        for path,notice in [('/politica-de-privacidade','mapas de cliques'),
                            ('/en/politica-de-privacidade','click maps')]:
            response=client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertIn('Microsoft Clarity',response.text)
            self.assertIn(notice,response.text)


if __name__=='__main__':unittest.main()
