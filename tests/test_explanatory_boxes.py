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
