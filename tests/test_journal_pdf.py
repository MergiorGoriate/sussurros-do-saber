import unittest
from io import BytesIO
from unittest.mock import patch
from PIL import Image as PillowImage
from reportlab.lib.pagesizes import A4
from reportlab.platypus import Paragraph, SimpleDocTemplate
from journal_pdf import article_flowables, load_image


class JournalPDFTests(unittest.TestCase):
    def test_body_starts_on_new_page_after_optional_front_matter(self):
        front = ''.join(f'<section data-article-field="{field}"><h2>{label}</h2><p>{label} de teste.</p></section>'
                        for field, label in (("summary", "Resumo"), ("keywords", "Palavras-chave"),
                                             ("abstract", "Abstract"), ("abstract_keywords", "Keywords")))
        for prefix in (front, ''):
            with self.subTest(front_matter=bool(prefix)):
                result = article_flowables(prefix + '<h2>Introdução</h2><p>Corpo do artigo.</p>',
                                          450, 700, '/tmp', 'https://example.org', start_body_new_page=True)
                breaks = [i for i, item in enumerate(result) if item.__class__.__name__ == 'PageBreak']
                self.assertEqual(len(breaks), 1)
                before = ' '.join(getattr(item, 'text', '') for item in result[:breaks[0]])
                after = ' '.join(getattr(item, 'text', '') for item in result[breaks[0] + 1:])
                self.assertNotIn('Introdução', before)
                self.assertIn('Introdução', after)
                self.assertIn('Corpo do artigo.', after)
                if prefix:
                    self.assertIn('Keywords de teste.', before)

    def test_article_contains_embedded_image_table_and_vector_chart(self):
        from app import render_markdown
        image = BytesIO()
        PillowImage.new('RGB', (1200, 800), '#1e4e8c').save(image, 'PNG')
        content = '# Resultados\n\n![Figura experimental](https://example.org/figure.png)\n\n| Grupo | Valor |\n|---|---|\n| A | 12 |\n\n[chart: bar|Comparação|A=12;B=8]\n\nConclusão científica.'
        buffer = BytesIO()
        document = SimpleDocTemplate(buffer, pagesize=A4)
        with patch('journal_pdf.load_image', return_value=image.getvalue()) as fetch:
            flowables = article_flowables(render_markdown(content), document.width, document.height, '/tmp', 'https://example.org')
            self.assertTrue(any(item.__class__.__name__ == "Table" for item in flowables))
            self.assertTrue(any(item.__class__.__name__ == "Drawing" for group in flowables for item in getattr(group, "_content", [group])))
            document.build(flowables)
        self.assertEqual(fetch.call_count, 1)
        pdf = buffer.getvalue()
        self.assertTrue(pdf.startswith(b'%PDF-'))
        self.assertIn(b'/Subtype /Image', pdf)

    def test_editorial_header_includes_journal_masthead_above_website(self):
        from types import SimpleNamespace
        from journal_pdf import editorial_header
        header = editorial_header(SimpleNamespace(issn="", current_issue="Vol. 1", doi=""), 450)
        brand = header._cellvalues[0][1]
        self.assertEqual(brand[0].__class__.__name__, "Image")
        self.assertEqual(brand[0].hAlign, "CENTER")
        self.assertEqual(header._cellStyles[0][1].alignment, "CENTER")
        self.assertAlmostEqual(brand[0].drawWidth, 220)
        self.assertLess(brand[0].drawHeight, brand[0].drawWidth)
        self.assertEqual(brand[-1].getPlainText(), "www.sussurrosdosaber.com")

    def test_academic_styles_and_compact_bilingual_labels(self):
        from journal_pdf import pdf_styles
        styles = pdf_styles()
        self.assertEqual(styles["Title"].alignment, 1)
        self.assertEqual(styles["BodyText"].alignment, 4)
        self.assertEqual(styles["BodyText"].fontName, "ArticleSerif")
        self.assertLessEqual(styles["Title"].fontSize, 14)
        self.assertLessEqual(styles["BodyText"].leading, 13)
        html = '<section data-article-field="summary"><h2>Resumo</h2><p>Texto em português.</p></section><section data-article-field="abstract"><h2>Abstract</h2><p>English text.</p></section>'
        result = article_flowables(html, 450, 700, '/tmp', 'https://example.org')
        paragraphs = [item for item in result if hasattr(item, 'text')]
        self.assertEqual(len(paragraphs), 2)
        self.assertIn('Resumo: ', paragraphs[0].text)
        self.assertIn('Texto em português.', paragraphs[0].text)
        self.assertIn('Abstract: ', paragraphs[1].text)

    def test_pdf_uses_the_article_title_from_the_public_page(self):
        from types import SimpleNamespace
        from app import journal_article_content
        journal = SimpleNamespace(title='Nome da revista', content_markdown='# Título do artigo\n\nConteúdo.', guidelines='')
        title, content = journal_article_content(journal)
        self.assertEqual(title, 'Título do artigo')
        self.assertNotIn('<h1>', content)
        self.assertIn('Conteúdo', content)

    def test_title_is_not_duplicated_and_lists_keep_numbering(self):
        result = article_flowables('<h1>Artigo</h1><ol><li>Primeiro</li><li>Segundo</li></ol>', 450, 700, '/tmp', 'https://example.org', title='Artigo')
        text = ' '.join(getattr(item, 'text', '') for item in result)
        self.assertNotIn('Artigo', text)
        self.assertIn('1. Primeiro', text)
        self.assertIn('2. Segundo', text)

    def test_download_embeds_article_images_without_cover_or_catalog_description(self):
        from types import SimpleNamespace
        from app import app, render_journal_pdf
        image = BytesIO()
        PillowImage.new('RGB', (160, 100), '#1e4e8c').save(image, 'PNG')
        journal = SimpleNamespace(title='Artigo', slug='artigo', description='Descrição do catálogo excluída',
                                  cover_image='https://example.org/cover.png',
                                  content_markdown='![Figura 1](https://example.org/figure.png)',
                                  guidelines='', references='Referência científica')
        with app.test_request_context(), patch('journal_pdf.load_image', return_value=image.getvalue()) as fetch, patch('app.Paragraph', wraps=Paragraph) as paragraph:
            response = render_journal_pdf(journal)
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.args[0], 'https://example.org/figure.png')
        self.assertNotIn('Descrição do catálogo excluída', ' '.join(str(call.args[0]) for call in paragraph.call_args_list))
        self.assertEqual(response.mimetype, 'application/pdf')
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertIn(b'/Subtype /Image', response.data)

    def test_pdf_includes_structured_fields_references_and_notes_in_order(self):
        from types import SimpleNamespace
        from app import app, render_journal_pdf
        journal = SimpleNamespace(title="Revista", slug="artigo", description="Descrição",
                                  content_markdown="# Artigo científico\n\n## Introdução\n\nTexto científico.",
                                  guidelines="", cover_image="", references="Referência verificável.",
                                  summary="Resumo português.", keywords="biologia; ciência",
                                  abstract="English abstract.", abstract_keywords="biology; science",
                                  author_contributions="Contributos científicos.", acknowledgements="Agradecimentos científicos.",
                                  funding="Financiamento confirmado.", conflicts_of_interest="Sem conflitos.",
                                  ethics_approval="Aprovação ética obtida.", informed_consent="Consentimento obtido.",
                                  data_availability="Dados disponíveis.", notes="Nota final.")
        with app.test_request_context(), patch("journal_pdf.article_flowables", wraps=article_flowables) as renderer:
            response = render_journal_pdf(journal)
        self.assertTrue(response.data.startswith(b"%PDF-"))
        body, references, notes = [str(call.args[0]) for call in renderer.call_args_list]
        positions = [body.index(value) for value in ("Resumo português.", "biologia; ciência", "English abstract.",
                     "biology; science", "Texto científico.", "Contributos científicos.", "Agradecimentos científicos.",
                     "Financiamento confirmado.", "Sem conflitos.", "Aprovação ética obtida.", "Consentimento obtido.", "Dados disponíveis.")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Referência verificável.", references)
        self.assertIn("Nota final.", notes)

    def test_failed_image_retains_article_and_visible_notice(self):
        with patch('journal_pdf.load_image', side_effect=ValueError('unavailable')):
            result = article_flowables('<p>Conteúdo</p><img src="https://example.org/a.png" alt="Figura 1"><p>Conclusão</p>', 450, 700, '/tmp', 'https://example.org')
        text = ' '.join(getattr(item, 'text', '') for item in result)
        self.assertIn('Conclusão', text)
        self.assertIn('Figura 1', text)
        self.assertIn('indisponível', text)

    def test_private_network_and_local_path_traversal_are_blocked(self):
        import time
        with patch('journal_pdf.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('127.0.0.1', 80))]):
            with self.assertRaises(ValueError):
                load_image('http://localhost/a.png', '/tmp/static', 'https://example.org', time.monotonic() + 10)
        with self.assertRaises(ValueError):
            load_image('/static/%2e%2e/secret', '/tmp/static', 'https://example.org', time.monotonic() + 10)


