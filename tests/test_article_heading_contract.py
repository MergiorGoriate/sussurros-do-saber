"""ATX marker boundaries in the existing article-only Markdown pipeline."""
import unittest
from bs4 import BeautifulSoup
from app import render_article_markdown, render_markdown


class HeadingMarkerContractTests(unittest.TestCase):
    def test_article_markers_require_whitespace_after_one_to_six_hashes(self):
        source = '#sem espaço\n\n##sem espaço\n\n####### Inválido\n\nTexto # literal\n\n## Secção'
        soup = BeautifulSoup(str(render_article_markdown(source)), 'html.parser')
        self.assertEqual([h.text for h in soup.find_all(['h1','h2','h3','h4','h5','h6'])], ['Secção'])
        self.assertIn('#sem espaço', soup.text)
        self.assertIn('####### Inválido', soup.text)

    def test_article_contract_preserves_six_levels_and_literal_contexts(self):
        source = '\n\n'.join('#' * level + ' Nível ' + str(level) for level in range(1,7))
        source += '\n\n```python\n# Código\n## Literal\n```\n\n`### Em linha`\n\n\\#### Escapado'
        soup = BeautifulSoup(str(render_article_markdown(source)), 'html.parser')
        self.assertEqual([h.name for h in soup.find_all(['h1','h2','h3','h4','h5','h6'])], ['h2','h2','h3','h4','h5','h6'])
        self.assertIn('# Código', soup.pre.text)
        self.assertIn('### Em linha', soup.text)
        self.assertIn('#### Escapado', soup.text)

    def test_non_article_consumers_keep_the_existing_parser_behaviour(self):
        soup = BeautifulSoup(str(render_markdown('#Titulo antigo')), 'html.parser')
        self.assertEqual(soup.h1.text, 'Titulo antigo')

    def test_tabs_are_valid_heading_separators(self):
        source = '\n\n'.join('#' * level + '\tSecção ' + str(level) for level in range(1, 7))
        soup = BeautifulSoup(str(render_article_markdown(source)), 'html.parser')
        self.assertEqual([h.name for h in soup.select('h2,h3,h4,h5,h6')], ['h2','h2','h3','h4','h5','h6'])
