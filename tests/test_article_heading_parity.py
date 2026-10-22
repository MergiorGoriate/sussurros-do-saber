"""Headings share one safe renderer without rewriting saved Markdown."""
import unittest
from bs4 import BeautifulSoup
import test_article_history as history
from app import app, render_markdown, render_article_markdown
from models import db
from governance_models import ArticleRevision

SOURCE = '\n\n'.join('#' * level + f' Nível {level}' for level in range(1, 7))


class HeadingRenderingTests(unittest.TestCase):
    def soup(self, source, article=True):
        return BeautifulSoup(str((render_article_markdown if article else render_markdown)(source)), 'html.parser')

    def test_shared_parser_recognizes_all_six_levels(self):
        soup = self.soup(SOURCE, article=False)
        self.assertEqual([el.name for el in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])],
                         ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        self.assertEqual([el.text for el in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])],
                         [f'Nível {level}' for level in range(1, 7)])

    def test_article_body_demotes_h1_and_handles_legacy_html_and_setext(self):
        for source in [SOURCE, '<h1>Antigo</h1>\n<h5>Detalhe</h5>\n<h6>Nota</h6>', 'Antigo\n======\n\n## Secção']:
            with self.subTest(source=source):
                soup = self.soup(source)
                self.assertIsNone(soup.h1)
                self.assertIsNotNone(soup.h2)

    def test_hashes_in_code_escaped_and_inline_text_stay_literal(self):
        source = '```python\n# comentário\n## código\n```\n\n~~~\n### literal\n~~~\n\n    #### indentado\n\n`##### inline`\n\n\\###### escapado\n\nTexto # literal.'
        soup = self.soup(source)
        self.assertFalse(soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']))
        self.assertIn('# comentário', soup.pre.text)
        self.assertIn('###### escapado', soup.text)
        self.assertEqual(len(soup.select('pre code')), 3)

    def test_ids_are_stable_unique_safe_and_isolated_from_references(self):
        source = '## Métodos\n\n## Métodos\n\n## Metodos-2\n\n### **Detalhes**\n\n###### 中文'
        first, second = self.soup(source), self.soup(source)
        ids = [el['id'] for el in first.select('[id]')]
        self.assertEqual(ids, [el['id'] for el in second.select('[id]')])
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[:2], ['sec-metodos', 'sec-metodos-2'])
        refs = BeautifulSoup(str(render_article_markdown(source, 'article-reference')), 'html.parser')
        self.assertFalse(set(ids) & {el['id'] for el in refs.select('[id]')})
        self.assertIsNotNone(first.select_one('#sec-detalhes strong'))

    def test_existing_elements_and_directives_are_preserved(self):
        source = '## Secção\n\nParágrafo **forte**, *ênfase* e $E=mc^2$.\n\n- Um\n- Dois\n\n> Citação\n\n[ligação](https://example.org)\n\n![Legenda](https://example.org/a.png)\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nTexto[^n].\n\n[^n]: Fonte.\n\n[destaque: Citação | Autor]\n\n[chart: bar|Título|A=2;B=3]'
        soup = self.soup(source)
        for selector in ['h2', 'p strong', 'p em', 'ul li', 'blockquote', 'a[href="https://example.org"]',
                         'img[alt="Legenda"]', 'table th', '.footnote', '.article-pullquote', 'svg']:
            self.assertIsNotNone(soup.select_one(selector), selector)
        self.assertIn('$E=mc^2$', soup.text)
        for link in soup.select('a.footnote-ref, a.footnote-backref'):
            self.assertIsNotNone(soup.find(id=link['href'][1:]))
        for container in soup.select('[aria-labelledby]'):
            self.assertIsNotNone(soup.find(id=container['aria-labelledby']))

    def test_untrusted_html_cannot_inject_attributes_or_executable_urls(self):
        soup = self.soup('## <img src="x" onerror="alert(1)"> Título\n\n<h1 id="clobber" onclick="alert(1)">Antigo</h1>\n<script>alert(1)</script><iframe src="https://example.org"></iframe>\n<a href="javascript:alert(1)">x</a>')
        self.assertFalse(soup.select('script, iframe, [onclick], [onerror], #clobber, [href^="javascript:"]'))
        self.assertIsNone(soup.h1)


class HeadingIntegrationTests(unittest.TestCase):
    setUp = history.ArticleHistoryTests.setUp
    tearDown = history.ArticleHistoryTests.tearDown
    member = history.ArticleHistoryTests.member
    article = history.ArticleHistoryTests.article
    signin = history.ArticleHistoryTests.signin
    post = history.ArticleHistoryTests.post
    edit = history.ArticleHistoryTests.edit

    def test_manual_save_reopen_revision_and_public_preview_match(self):
        item = self.article(self.member())
        self.signin(self.primary)
        source = SOURCE + '\n\n```\n# literal\n```\n\nTexto científico. '
        slug, title = item.slug, item.title
        response = self.edit(item, source, references='# Fontes\n\nReferência.')
        self.assertEqual(response.status_code, 302)
        db.session.refresh(item)
        self.assertEqual(item.body, source)
        self.assertEqual((item.slug, item.title), (slug, title))
        form = BeautifulSoup(self.client.get(f'/admin/artigos/{item.id}/editar').data, 'html.parser')
        self.assertEqual(form.select_one('#bodyEditor').text, source)
        self.assertEqual([el['value'] for el in form.select('#headingLevel option')], ['', '2', '3', '4', '5', '6'])
        revision = ArticleRevision.query.filter_by(article_id=item.id).order_by(ArticleRevision.number.desc()).first()
        self.assertEqual(revision.snapshot['body'], source)
        preview = self.post('/admin/artigos/previsualizar', content=source)
        self.assertEqual(preview.status_code, 200)
        self.assertIn('no-store', preview.headers['Cache-Control'])
        item.status = 'published'
        db.session.commit()
        page = self.client.get('/artigo/' + slug)
        self.assertEqual(page.status_code, 200)
        public = BeautifulSoup(page.data, 'html.parser')
        self.assertEqual([el.text.strip() for el in public.select('h1')], [title])
        self.assertEqual(public.select_one('.article-markdown').decode_contents(), preview.json['html'])
        ids = [el['id'] for el in public.select('.article-markdown [id]')]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIsNotNone(public.select_one('#ref-sec-fontes'))

    def test_autosave_keeps_all_markdown_and_code_exactly(self):
        from test_article_autosave import ArticleAutosaveTests
        item = self.article(self.member())
        self.signin(self.primary)
        source = '  \n' + SOURCE + '\n\n```\n# literal\n```\n\nTexto.  \n'
        response = ArticleAutosaveTests.save(self, item, body=source)
        self.assertEqual(response.status_code, 200)
        db.session.refresh(item)
        self.assertEqual(item.body, source)
        form = BeautifulSoup(self.client.get(f'/admin/artigos/{item.id}/editar').data, 'html.parser')
        self.assertEqual(form.select_one('#bodyEditor').text, source)
