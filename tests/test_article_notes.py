"""Footnote navigation, isolation, sanitization and private preview."""
import unittest
from bs4 import BeautifulSoup
from app import app, render_markdown
import test_article_history as history


class NotesRenderingTests(unittest.TestCase):
    def render(self, source):
        return BeautifulSoup(str(render_markdown(source)), 'html.parser')

    def test_repeated_calls_have_distinct_targets_and_return_links(self):
        soup = self.render('Uma[^n] e outra[^n].\n\n[^n]: **Fonte** https://example.org')
        calls = soup.select('a.footnote-ref')
        returns = soup.select('a.footnote-backref')
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(returns), 2)
        self.assertEqual(len(soup.select('.footnote li')), 1)
        for link in calls + returns:
            self.assertIsNotNone(soup.find(id=link['href'][1:]))
        self.assertEqual(len({link['href'] for link in returns}), 2)
        self.assertEqual(soup.select_one('.footnote strong').text, 'Fonte')
        self.assertEqual(soup.select_one('.footnote a[href^="https"]')['href'], 'https://example.org')

    def test_order_and_namespaces(self):
        with app.test_request_context():
            first = self.render('B[^b] A[^a].\n\n[^a]: Primeiro na definição.\n[^b]: Primeiro no texto.')
            second = self.render('Nota[^b].\n\n[^b]: Outra secção.')
        self.assertIn('Primeiro no texto', first.select('.footnote li')[0].text)
        self.assertFalse({el['id'] for el in first.select('[id]')} & {el['id'] for el in second.select('[id]')})

    def test_literal_missing_and_unused_notes(self):
        for source in ['Sem definição[^ausente].', '```\nTexto[^n]\n```', r'Escapado \[^n]']:
            self.assertEqual(len(self.render(source).select('a.footnote-ref')), 0)
        soup = self.render('Texto.\n\n[^n]: Nota não chamada.')
        self.assertEqual(len(soup.select('a.footnote-backref')), 0)

    def test_html_is_sanitized_inside_notes(self):
        soup = self.render('Texto[^n].\n\n[^n]: <script>alert(1)</script><img src="x" onerror="alert(1)"><a href="javascript:alert(1)" id="clobber" style="color:red">x</a>')
        self.assertFalse(soup.select('script, [onerror], [style], #clobber'))
        self.assertFalse(soup.select('[href^="javascript:"]'))
        self.assertEqual(len(soup.select('a.footnote-ref')), 1)


class NotesPreviewTests(unittest.TestCase):
    setUp = history.ArticleHistoryTests.setUp
    tearDown = history.ArticleHistoryTests.tearDown
    member = history.ArticleHistoryTests.member
    signin = history.ArticleHistoryTests.signin
    post = history.ArticleHistoryTests.post

    def test_preview_requires_login_csrf_and_permission(self):
        path = '/admin/artigos/previsualizar'
        self.assertEqual(app.test_client().post(path).status_code, 302)
        author = self.member()
        self.signin(author.admin)
        self.assertEqual(self.client.post(path, data={'content': 'Texto'}).status_code, 400)
        response = self.post(path, content='Texto[^n].\n\n[^n]: Fonte.')
        self.assertEqual(response.status_code, 200)
        self.assertIn('doc-endnotes', response.json['html'])
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertEqual(self.post(path, content='x' * 400001).status_code, 400)
        reviewer = self.member('portal_reviewer')
        self.signin(reviewer.admin)
        self.assertEqual(self.post(path, content='Texto').status_code, 403)
