"""Article heading semantics, safe rendering and real editorial persistence."""
import re
import unittest

import test_platform  # Select the existing isolated SQLite fixture before app import.
import test_article_history as history
from app import app, render_markdown, render_article_markdown, journal_article_content
from bs4 import BeautifulSoup
from governance_models import ArticleRevision
from models import db, Journal

LEVELS = '\n\n'.join('#' * level + ' Nível ' + str(level) for level in range(1, 7))


def soup(html):
    return BeautifulSoup(str(html), 'html.parser')


def headings(html):
    return [(h.name, h.get_text(' ', strip=True), h.get('id'))
            for h in soup(html).find_all(re.compile(r'^h[1-6]$'))]


class HeadingRenderingTests(unittest.TestCase):
    def test_existing_processor_converts_all_six_levels(self):
        self.assertEqual([(h[0], h[1]) for h in headings(render_markdown(LEVELS))],
                         [(f'h{i}', f'Nível {i}') for i in range(1, 7)])

    def test_article_body_reserves_h1_without_changing_other_levels(self):
        self.assertEqual([h[0] for h in headings(render_article_markdown(LEVELS))],
                         ['h2', 'h2', 'h3', 'h4', 'h5', 'h6'])
        self.assertEqual(headings(render_article_markdown('<h1>Antigo</h1><h4>Detalhe</h4>'))[0][:2],
                         ('h2', 'Antigo'))

    def test_code_escapes_inline_text_and_indented_code_are_literal(self):
        source = ('```markdown\n# Código\n## Código também\n```\n\n'
                  '~~~\n###### Literal\n~~~\n\n'
                  '    ### Código indentado\n\n'
                  r'\# Escapado' + '\n\n`## Inline` e texto com # no meio.')
        result = soup(render_article_markdown(source))
        self.assertFalse(result.find_all(re.compile(r'^h[1-6]$')))
        self.assertEqual(len(result.select('pre')), 3)
        self.assertIn('# Escapado', result.get_text())
        self.assertIn('## Inline', result.select('code')[-1].get_text())

    def test_anchors_are_stable_unique_and_separate_from_references(self):
        source = '## Introdução\n\n## Introdução\n\n### Métodos e **análise**\n\n[Voltar](#sec-introducao)'
        first = render_article_markdown(source)
        self.assertEqual(str(first), str(render_article_markdown(source)))
        ids = [h[2] for h in headings(first)]
        self.assertEqual(ids, ['sec-introducao', 'sec-introducao-2',
                               'sec-metodos-e-analise'])
        self.assertEqual(headings(render_article_markdown('## Introdução', 'ref-sec'))[0][2],
                         'ref-sec-introducao')
        self.assertIsNotNone(soup(first).find(id=soup(first).a['href'][1:]))

    def test_numbered_bibliography_anchors_resolve_without_extra_headings(self):
        calls = r'Texto \[[12](#ref-12), [13](#ref-13)\].'
        references = ('<ol><li id="ref-12">Fonte A</li>'
                      '<li id="ref-13">Fonte B</li></ol>')
        for html in (render_article_markdown(calls + '\n\n' + references),
                     str(render_article_markdown(calls)) +
                     str(render_article_markdown(references, 'ref-sec'))):
            result = soup(html)
            for number in (12, 13):
                link = result.select_one(f'a[href="#ref-{number}"]')
                self.assertIsNotNone(link)
                target = result.find(id=link['href'][1:])
                self.assertIsNotNone(target)
                self.assertEqual(target.name, 'li')
                self.assertEqual(len(result.select(f'#ref-{number}')), 1)
            self.assertFalse(result.select('h2, h3, h4, h5, h6'))

    def test_bibliography_ids_are_restricted_to_numbered_article_list_items(self):
        source = ('<ol><li id="ref-12" onclick="alert(1)">A</li>'
                  '<li id="location">B</li><li id="ref-xyz">C</li>'
                  '<li id="ref-0">D</li></ol><p id="ref-13">E</p>')
        self.assertEqual([el['id'] for el in soup(render_article_markdown(source)).select('[id]')],
                         ['ref-12'])
        self.assertFalse(soup(render_article_markdown(source)).select('[onclick]'))
        self.assertFalse(soup(render_markdown(source)).select('[id]'))

    def test_security_and_existing_content_features_survive(self):
        source = ('## <script>alert(1)</script>Título\n\n'
                  '<h3 id="location" onclick="alert(1)">HTML antigo</h3>\n\n'
                  '<img src="https://example.org/a.png" onerror="alert(1)">\n\n'
                  '[Perigoso](javascript:alert%281%29)\n\n'
                  '> Uma citação\n\n- Um\n- Dois\n\n'
                  '| A | B |\n|---|---|\n| 1 | 2 |\n\n'
                  '![Diagrama](https://example.org/diagrama.png)\n\n'
                  '[capitular] Parágrafo $E=mc^2$ e **ênfase**.\n\n'
                  '[destaque: Texto destacado | Autor]\n\n'
                  'Chamada[^n].\n\n[^n]: [Fonte](https://example.org)')
        result = soup(render_article_markdown(source))
        self.assertFalse(result.select('script,[onclick],[onerror],#location,[href^="javascript:"]'))
        for selector in ['h2', 'h3', 'blockquote', 'ul li', 'table td', 'figure img[alt="Diagrama"]',
                         '.article-dropcap', '.article-pullquote', '.footnote', '.footnote-ref']:
            self.assertTrue(result.select(selector), selector)
        self.assertIn('$E=mc^2$', result.get_text())
        for link in result.select('a.footnote-ref, a.footnote-backref'):
            self.assertIsNotNone(result.find(id=link['href'][1:]))

    def test_journal_title_extraction_and_generic_markdown_are_unchanged(self):
        journal = Journal(title='Revista', content_markdown='# Título científico\n\n## Introdução')
        title, content = journal_article_content(journal)
        self.assertEqual(title, 'Título científico')
        self.assertEqual(headings(content)[0][:2], ('h2', 'Introdução'))
        self.assertEqual(headings(render_markdown('# Título'))[0][0], 'h1')


class HeadingPersistenceTests(unittest.TestCase):
    setUp = history.ArticleHistoryTests.setUp
    tearDown = history.ArticleHistoryTests.tearDown
    member = history.ArticleHistoryTests.member
    article = history.ArticleHistoryTests.article
    signin = history.ArticleHistoryTests.signin
    post = history.ArticleHistoryTests.post
    edit = history.ArticleHistoryTests.edit

    def test_manual_save_reopen_publication_and_preview_have_same_headings(self):
        item = self.article(self.member())
        self.signin(self.primary)
        body = LEVELS + '\n\n```\n# Literal\n```\n\nParágrafo e [fonte](https://example.org).'
        original_title, original_slug = item.title, item.slug
        self.assertEqual(self.edit(item, body, references='# Fonte antiga\n\n###### Nota').status_code, 302)
        db.session.refresh(item)
        self.assertEqual(item.body, body)
        self.assertEqual((item.title, item.slug), (original_title, original_slug))
        self.assertEqual(ArticleRevision.query.filter_by(article_id=item.id).order_by(
            ArticleRevision.number.desc()).first().snapshot['body'], body)
        form = self.client.get(f'/admin/artigos/{item.id}/editar')
        self.assertEqual(soup(form.text).select_one('#bodyEditor').text, body)
        self.assertEqual(headings(soup(form.text).select_one('#markdownPreview')), headings(render_article_markdown(body)))
        response = self.post('/admin/artigos/previsualizar', content=body)
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response.headers['Cache-Control'])
        item.status = 'published'
        db.session.commit()
        public = self.client.get('/artigo/' + original_slug)
        self.assertEqual(public.status_code, 200)
        dom = soup(public.text)
        self.assertEqual([h.text.strip() for h in dom.select('h1')], [original_title])
        self.assertEqual(headings(dom.select_one('.article-markdown')), headings(response.json['html']))
        all_ids = [el['id'] for el in dom.select('[id]')]
        self.assertEqual(len(all_ids), len(set(all_ids)))
        self.assertEqual(item.body, body)

    def test_autosave_keeps_raw_markdown_and_history(self):
        item = self.article(self.member())
        self.signin(self.primary)
        body = LEVELS + '\n\n    # Código\n\n\\# Literal'
        values = {name: getattr(item, name) or '' for name in
                  ('title', 'summary', 'references', 'keywords', 'doi')}
        values.update(body=body, read_minutes=item.read_minutes, version_token=item.updated_at.isoformat())
        response = self.post(f'/admin/artigos/{item.id}/rascunho', **values)
        self.assertEqual(response.status_code, 200)
        db.session.refresh(item)
        self.assertEqual(item.body, body)
        reopened = soup(self.client.get(f'/admin/artigos/{item.id}/editar').text)
        self.assertEqual(reopened.select_one('#bodyEditor').text, body)
        self.assertEqual(item.status, 'draft')
        self.assertEqual(ArticleRevision.query.filter_by(article_id=item.id).order_by(
            ArticleRevision.number.desc()).first().snapshot['body'], body)

    def test_legacy_html_rendering_does_not_rewrite_database(self):
        item = self.article(self.member())
        body = '<h1>Antigo</h1><h2>Secção</h2><h6>Nota</h6><p>Texto existente.</p>'
        item.body = body
        item.status = 'published'
        db.session.commit()
        page = self.client.get('/artigo/' + item.slug)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(len(soup(page.text).select('h1')), 1)
        self.assertEqual(headings(soup(page.text).select_one('.article-markdown'))[0][:2], ('h2', 'Antigo'))
        db.session.refresh(item)
        self.assertEqual(item.body, body)
