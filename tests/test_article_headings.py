"""Article headings share one safe rendering path through editing and publication."""
import unittest
from bs4 import BeautifulSoup
from app import app, render_article_markdown, render_markdown
from article_notes import render_notes_markdown
from models import Article, db, utcnow
from governance_models import ArticleRevision
import test_article_history as history


SOURCE = '\n\n'.join('#' * level + ' Secção ' + str(level) for level in range(1, 7))


class HeadingRenderingTests(unittest.TestCase):
    def render(self, source):
        return BeautifulSoup(str(render_article_markdown(source)), 'html.parser')

    def test_existing_processor_converts_all_six_levels(self):
        rendered, _ = render_notes_markdown(SOURCE, strict_headings=True)
        soup = BeautifulSoup(rendered, 'html.parser')
        self.assertEqual([h.name for h in soup.find_all(['h1','h2','h3','h4','h5','h6'])],
                         ['h1','h2','h3','h4','h5','h6'])

    def test_only_article_body_h1_is_presented_as_h2(self):
        soup = self.render(SOURCE)
        self.assertEqual([h.name for h in soup.find_all(['h1','h2','h3','h4','h5','h6'])],
                         ['h2','h2','h3','h4','h5','h6'])
        self.assertIn('<h1>', str(render_markdown('# Título fora dos artigos')))
        self.assertEqual(self.render('<h1>Título HTML antigo</h1>').h2.text, 'Título HTML antigo')
        self.assertEqual(self.render('Título antigo\n=============').h2.text, 'Título antigo')

    def test_fenced_indented_inline_and_escaped_code_stays_literal(self):
        for source in ['```markdown\n# Um\n###### Seis\n```', '~~~\n## Dois\n~~~',
                       '    ## Código indentado', '`# Código em linha`', r'\# Escapado',
                       '#sem-espaço', '####### Sete', 'Texto # normal']:
            with self.subTest(source=source):
                soup = self.render(source)
                self.assertFalse(soup.find_all(['h1','h2','h3','h4','h5','h6']))
                self.assertIn('#', soup.get_text())

    def test_hashes_in_raw_code_are_not_changed(self):
        soup = self.render('<pre><code># Um\n## Dois</code></pre>')
        self.assertEqual(soup.code.text, '# Um\n## Dois')
        self.assertFalse(soup.select('h1,h2,h3,h4,h5,h6'))

    def test_stable_unique_accented_and_empty_heading_anchors(self):
        source = '## Introdução\n\n### Introdução\n\n#### 中文\n\n###### **Métodos**'
        a, b = self.render(source), self.render(source)
        ids = [h['id'] for h in a.select('h2,h3,h4,h5,h6')]
        self.assertEqual(ids, ['sec-introducao', 'sec-introducao-2', 'sec-seccao', 'sec-metodos'])
        self.assertEqual(ids, [h['id'] for h in b.select('h2,h3,h4,h5,h6')])
        linked = self.render('[Métodos](#sec-metodos)\n\n## Métodos')
        self.assertIsNotNone(linked.find(id=linked.a['href'][1:]))

    def test_sanitization_precedes_heading_policy(self):
        soup = self.render('## <img src="x" onerror="alert(1)"> Teste\n\n'
                           '<h6 id="clobber" onclick="alert(1)">Título</h6>\n\n'
                           '<script>alert(1)</script><iframe src="javascript:alert(1)"></iframe>\n\n'
                           '[ligação](javascript:alert(1))')
        self.assertFalse(soup.select('script,iframe,[onclick],[onerror],#clobber,[href^="javascript:"]'))
        self.assertEqual(soup.h6['id'], 'sec-titulo')

    def test_supported_content_survives_heading_processing(self):
        source = ('## Métodos\n\nParágrafo **forte** e *ênfase*, $E=mc^2$.\n\n'
                  '- Primeiro\n- Segundo\n\n> Uma citação\n\n'
                  '| A | B |\n| --- | --- |\n| 1 | 2 |\n\n'
                  '![Descrição](https://example.org/image.png)\n\n'
                  '[portrait: Retrato|Legenda|Crédito](https://example.org/portrait.png)\n\n'
                  '[video: Legenda do vídeo](https://youtu.be/abcdefghijk)\n\n'
                  '[chart: bar|Contagem|A=1; B=2]\n\n'
                  'Uma nota[^a].\n\n[^a]: [Fonte](https://example.org)')
        soup = self.render(source)
        for selector in ['p strong','p em','ul li','blockquote','table th','table td','figure img',
                         'figcaption','.article-video','.article-chart','.footnote','a.footnote-ref']:
            self.assertTrue(soup.select(selector), selector)
        self.assertIn('$E=mc^2$', soup.text)
        for a in soup.select('a.footnote-ref,a.footnote-backref'):
            self.assertIsNotNone(soup.find(id=a['href'][1:]))


class HeadingEditingTests(unittest.TestCase):
    setUp = history.ArticleHistoryTests.setUp
    tearDown = history.ArticleHistoryTests.tearDown
    member = history.ArticleHistoryTests.member
    article = history.ArticleHistoryTests.article
    signin = history.ArticleHistoryTests.signin
    post = history.ArticleHistoryTests.post
    edit = history.ArticleHistoryTests.edit

    def test_save_reopen_revision_preview_and_public_page(self):
        owner = self.member()
        article = self.article(owner)
        self.signin(self.primary)
        original = (article.title, article.slug, article.summary)
        source = SOURCE + '\n\n```\n# Literal\n```\n\n[Ir](#sec-seccao-6)'
        response = self.edit(article, source, references='# Fonte principal\n\n## Secção 2')
        self.assertEqual(response.status_code, 302)
        db.session.expire_all()
        article = db.session.get(Article, article.id)
        self.assertEqual(article.body, source)
        self.assertEqual((article.title, article.slug, article.summary), original)
        self.assertEqual(ArticleRevision.query.filter_by(article_id=article.id).order_by(ArticleRevision.number.desc()).first().snapshot['body'], source)
        edit = BeautifulSoup(self.client.get(f'/admin/artigos/{article.id}/editar').text, 'html.parser')
        self.assertEqual(edit.select_one('#bodyEditor').text, source)
        self.assertEqual([b['data-heading'] for b in edit.select('[data-heading]')], ['2','3','4','5','6'])
        article.status, article.published_at = 'published', utcnow()
        db.session.commit()
        preview = self.post('/admin/artigos/previsualizar', content=source)
        self.assertEqual(preview.status_code, 200)
        public = BeautifulSoup(app.test_client().get('/artigo/' + article.slug).text, 'html.parser')
        self.assertEqual(len(public.select('h1')), 1)
        self.assertEqual(public.h1.text.strip(), article.title)
        body = public.select_one('.article-headings')
        self.assertEqual(str(body.decode_contents()), preview.json['html'])
        self.assertEqual(body.code.text.strip(), '# Literal')
        ids = [el['id'] for el in public.select('[id]')]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(public.select_one('.article-references h2[id^="ref-sec-"]').text, 'Fonte principal')

    def test_autosave_preserves_source_and_preview_safety(self):
        owner = self.member()
        article = self.article(owner)
        self.signin(owner.admin)
        source = SOURCE + '\n\n<img src="x" onerror="alert(1)">'
        values = {name: getattr(article, name) or '' for name in ('title','summary','references','keywords','doi')}
        response = self.post(f'/admin/artigos/{article.id}/rascunho', body=source,
                             read_minutes=article.read_minutes, **values,
                             version_token=article.updated_at.isoformat())
        self.assertEqual(response.status_code, 200)
        db.session.expire_all()
        self.assertEqual(db.session.get(Article, article.id).body, source)
        result = self.post('/admin/artigos/previsualizar', content=source)
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('onerror', result.json['html'])
        self.assertIn('<h6', result.json['html'])

    def test_old_html_and_markdown_articles_need_no_rewrite(self):
        owner = self.member()
        article = self.article(owner)
        for source in ['<h2>Introdução</h2><p>Texto antigo.</p><h4>Método</h4>',
                       '## Introdução\n\nTexto antigo.\n\n#### Método']:
            article.body, article.status, article.published_at = source, 'published', utcnow()
            db.session.commit()
            public = BeautifulSoup(app.test_client().get('/artigo/' + article.slug).text, 'html.parser')
            self.assertEqual(public.select_one('.article-headings h2').text, 'Introdução')
            self.assertEqual(public.select_one('.article-headings h4').text, 'Método')
            self.assertEqual(db.session.get(Article, article.id).body, source)
