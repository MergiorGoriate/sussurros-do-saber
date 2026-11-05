"""Public icon delivery, shared document heads and cache invalidation."""
import io
import json
import unittest
from urllib.parse import urljoin, urlsplit
from PIL import Image
from bs4 import BeautifulSoup
import test_platform as fixtures
from app import app, static_asset_version


class SiteIconTests(unittest.TestCase):
    def test_shared_heads_resolve_exact_icon_sizes_and_manifest(self):
        client = app.test_client()
        for path in ['/', '/admin/login', '/submissoes/entrar']:
            response = client.get(path)
            self.assertEqual(response.status_code, 200, path)
            soup = BeautifulSoup(response.data, 'html.parser')
            links = soup.head.select('link[rel="icon"], link[rel="apple-touch-icon"], link[rel="manifest"]')
            self.assertEqual(len(links), 5, path)
            self.assertEqual(len({link['href'] for link in links}), 5)
            for link in links:
                asset = client.get(link['href'])
                self.assertEqual(asset.status_code, 200, link['href'])
                self.assertIn('immutable', asset.headers['Cache-Control'])
                self.assertIn('v=', link['href'])
                if link['rel'] != ['manifest']:
                    self.assertEqual(asset.mimetype, 'image/png')
                    with Image.open(io.BytesIO(asset.data)) as icon:
                        self.assertEqual('%sx%s' % icon.size, link['sizes'])
                        self.assertEqual(icon.width, icon.height)
                asset.close()

    def test_manifest_urls_resolve_from_manifest_location_and_preserve_browser_mode(self):
        client = app.test_client()
        response = client.get('/static/site.webmanifest')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/manifest+json')
        self.assertIn('must-revalidate', response.headers['Cache-Control'])
        manifest = json.loads(response.data)
        self.assertEqual(manifest['name'], 'Sussurros do Saber')
        self.assertEqual(manifest['short_name'], 'Sussurros')
        self.assertEqual((manifest['start_url'], manifest['scope'], manifest['display']), ('/', '/', 'browser'))
        self.assertEqual({icon['sizes'] for icon in manifest['icons']}, {'192x192', '512x512'})
        for icon in manifest['icons']:
            self.assertEqual(icon['purpose'], 'any')
            url = urljoin('/static/site.webmanifest', icon['src'])
            asset = client.get(url)
            self.assertEqual(asset.status_code, 200)
            self.assertEqual(asset.mimetype, icon['type'])
            self.assertIn('immutable', asset.headers['Cache-Control'])
            with Image.open(io.BytesIO(asset.data)) as image:
                self.assertEqual('%sx%s' % image.size, icon['sizes'])
            filename = urlsplit(url).path.removeprefix('/static/')
            self.assertTrue(icon['src'].endswith('?v='+static_asset_version(filename)))
            asset.close()
        response.close()

    def test_unversioned_icons_revalidate_and_old_version_cannot_be_immutable(self):
        client = app.test_client()
        for suffix in ['', '?v=old-version']:
            response = client.get('/static/icons/favicon-32x32.png'+suffix)
            self.assertEqual(response.status_code, 200)
            self.assertIn('must-revalidate', response.headers['Cache-Control'])
            self.assertNotIn('immutable', response.headers['Cache-Control'])
            response.close()

    def test_root_favicon_is_public_and_revalidates(self):
        client = app.test_client()
        for method in ('get', 'head'):
            response = getattr(client, method)('/favicon.ico')
            self.assertEqual(response.status_code, 200)
            self.assertIn(response.mimetype, {'image/vnd.microsoft.icon', 'image/x-icon'})
            self.assertIn('must-revalidate', response.headers['Cache-Control'])
            self.assertNotIn('noindex', response.headers.get('X-Robots-Tag', ''))
            if method == 'get':
                with Image.open(io.BytesIO(response.data)) as icon:
                    self.assertEqual(icon.format, 'ICO')
                    self.assertTrue({(16, 16), (32, 32), (48, 48)}.issubset(icon.ico.sizes()))
            response.close()

    def test_home_declares_high_resolution_icon_and_root_ico(self):
        response = app.test_client().get('/')
        soup = BeautifulSoup(response.data, 'html.parser')
        self.assertIsNotNone(soup.head.select_one('link[rel="icon"][sizes="192x192"]'))
        self.assertEqual(soup.head.select_one('link[rel="shortcut icon"]')['href'], '/favicon.ico')
