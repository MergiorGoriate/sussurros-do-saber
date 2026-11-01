import unittest
from explanatory_boxes import prepare_explanatory_boxes


class ExplanatoryBoxTests(unittest.TestCase):
    def render(self, text):
        self.embeds = []
        def store(prefix, html):
            self.embeds.append(html)
            return "EXPLAINER_TOKEN"
        return prepare_explanatory_boxes(text, store)

    def test_paragraphs_layout_and_surrounding_text(self):
        result = self.render("Antes\n\n[caixa: Conceito|right]\nPrimeiro parágrafo.\n\nSegundo parágrafo.\n[/caixa]\n\nDepois")
        self.assertEqual(result, "Antes\n\nEXPLAINER_TOKEN\n\nDepois")
        self.assertIn('article-explainer--right', self.embeds[0])
        self.assertIn('<p>Primeiro parágrafo.</p><p>Segundo parágrafo.</p>', self.embeds[0])

    def test_html_is_escaped_in_title_body_and_accessible_label(self):
        self.render('[caixa: <img src=x onerror=alert(1)>|full]\n<script>alert(1)</script>\n[/caixa]')
        self.assertNotIn('<script>', self.embeds[0])
        self.assertNotIn('<img', self.embeds[0])
        self.assertIn('&lt;script&gt;', self.embeds[0])
        self.assertIn('article-explainer--full', self.embeds[0])

    def test_optional_title_and_incomplete_or_empty_box(self):
        self.render('[caixa: |full]\nUma explicação.\n[/caixa]')
        self.assertIn('aria-label="Caixa explicativa"', self.embeds[0])
        for source in ('[caixa: Teste]\nSem fecho', '[caixa: Teste]\n\n[/caixa]'):
            self.assertEqual(self.render(source), source)
            self.assertEqual(self.embeds, [])

    def test_windows_and_classic_line_endings_are_rendered(self):
        for newline in ('\r\n', '\r', '\n'):
            source = newline.join(['[caixa: Conceito|right]', 'Primeiro.', '', 'Segundo.', '[/caixa]'])
            self.render(source)
            self.assertEqual(len(self.embeds), 1)
            self.assertIn('<p>Primeiro.</p><p>Segundo.</p>', self.embeds[0])

    def test_old_editor_delimiters_are_repaired_without_decoding_body_backslashes(self):
        source = r'Antes\n\n[caixa: Conceito|full]\nCaminho C:\novo e sequência \n literal.\n[/caixa]\n\nDepois'
        result = self.render(source)
        self.assertEqual(result, 'Antes\n\nEXPLAINER_TOKEN\n\nDepois')
        self.assertIn(r'C:\novo e sequência \n literal.', self.embeds[0])
        self.assertEqual(self.render(r'Fora de caixas: C:\novo e \n literal.'), r'Fora de caixas: C:\novo e \n literal.')


from bs4 import BeautifulSoup
from app import app
from models import db
import test_article_history as fixtures


class PublishedExplanatoryBoxTests(unittest.TestCase):
    setUp = fixtures.ArticleHistoryTests.setUp
    tearDown = fixtures.ArticleHistoryTests.tearDown
    member = fixtures.ArticleHistoryTests.member
    article = fixtures.ArticleHistoryTests.article
    signin = fixtures.ArticleHistoryTests.signin
    post = fixtures.ArticleHistoryTests.post
    edit = fixtures.ArticleHistoryTests.edit

    def test_windows_form_submission_renders_box_in_public_html_without_javascript(self):
        article = self.article(self.member())
        self.signin(self.primary)
        source = 'Parágrafo anterior.\r\n\r\n[caixa: Conceito|right]\r\nPrimeiro parágrafo explicativo.\r\n\r\nSegundo parágrafo explicativo.\r\n[/caixa]\r\n\r\nParágrafo seguinte.'
        self.assertEqual(self.edit(article, source, status='published').status_code, 302)
        db.session.refresh(article)
        self.assertEqual(article.body, source)
        response = app.test_client().get('/artigo/' + article.slug)
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.data, 'html.parser')
        box = soup.select_one('.article-explainer')
        self.assertIsNotNone(box)
        self.assertEqual(box.strong.text, 'Conceito')
        self.assertEqual([p.text for p in box.select('p')], ['Primeiro parágrafo explicativo.', 'Segundo parágrafo explicativo.'])
        self.assertNotIn('[caixa:', soup.get_text())
