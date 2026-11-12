import unittest
from unittest.mock import patch, Mock
from xml.etree import ElementTree

from bs4 import BeautifulSoup
import requests
import test_platform
from app import app, SITE_URL
from extensions import limiter
from models import Author


class PublicAuditTests(unittest.TestCase):
    def setUp(self):
        previous = limiter.enabled
        limiter.enabled = False
        self.addCleanup(setattr, limiter, 'enabled', previous)
        self.client = app.test_client()
        with app.app_context():
            self.slug = Author.query.filter_by(active=True).first().slug

    def test_author_page_two_canonical_and_alternates(self):
        with patch('internationalization.interface_ready', return_value=True):
            for prefix in ('', '/en'):
                path = '/autor/' + self.slug
                response = self.client.get(prefix + path + '?pagina=2&utm_source=test')
                self.assertEqual(response.status_code, 200)
                soup = BeautifulSoup(response.text, 'html.parser')
                expected = SITE_URL + prefix + path + '?pagina=2'
                self.assertEqual(soup.find('link', rel='canonical')['href'], expected)
                self.assertEqual(soup.find('meta', property='og:url')['content'], expected)
                self.assertEqual(soup.find('link', hreflang='en')['href'], SITE_URL + '/en' + path + '?pagina=2')
                self.assertEqual(soup.find('link', hreflang='pt-MZ')['href'], SITE_URL + path + '?pagina=2')
                self.assertIn('2', soup.title.text)

    def test_author_profiles_have_reciprocal_sitemap_entries(self):
        with patch('internationalization.interface_ready', return_value=True):
            response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9', 'x': 'http://www.w3.org/1999/xhtml'}
        entries = {e.find('s:loc', ns).text: e for e in ElementTree.fromstring(response.data)}
        pt = SITE_URL + '/autor/' + self.slug
        en = SITE_URL + '/en/autor/' + self.slug
        for url in (pt, en):
            links = {e.attrib['hreflang']: e.attrib['href'] for e in entries[url].findall('x:link', ns)}
            self.assertEqual(links['pt-MZ'], pt)
            self.assertEqual(links['en'], en)

    def test_assistant_forwards_supported_language(self):
        worker = Mock()
        worker.json.return_value = {'ok': True, 'answer': 'Answer', 'links': []}
        for requested, expected in [('en', 'en'), ('pt', 'pt'), ('unknown', 'pt')]:
            with patch('app.requests.post', return_value=worker) as send:
                response = self.client.post('/api/assistente', json={'message': 'Question', 'language': requested})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(send.call_args.kwargs['json'], {'message': 'Question', 'language': expected, 'history': []})

    def test_assistant_english_validation_and_outage(self):
        response = self.client.post('/api/assistente', json={'message': '', 'language': 'en'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('Enter a question', response.json['answer'])
        with patch('app.requests.post', side_effect=requests.Timeout):
            response = self.client.post('/api/assistente', json={'message': 'Question', 'language': 'en'})
        self.assertEqual(response.status_code, 502)
        self.assertIn('temporarily unavailable', response.json['answer'])
