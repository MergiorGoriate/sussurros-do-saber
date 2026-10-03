import unittest
from io import BytesIO
from unittest.mock import patch
from PIL import Image as PillowImage
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate
from journal_pdf import article_flowables, load_image


class JournalPDFTests(unittest.TestCase):
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

    def test_title_is_not_duplicated_and_lists_keep_numbering(self):
        result = article_flowables('<h1>Artigo</h1><ol><li>Primeiro</li><li>Segundo</li></ol>', 450, 700, '/tmp', 'https://example.org', title='Artigo')
        text = ' '.join(getattr(item, 'text', '') for item in result)
        self.assertNotIn('Artigo', text)
        self.assertIn('1. Primeiro', text)
        self.assertIn('2. Segundo', text)

    def test_download_response_embeds_body_and_cover_images(self):
        from types import SimpleNamespace
        from app import app, render_journal_pdf
        image = BytesIO()
        PillowImage.new('RGB', (160, 100), '#1e4e8c').save(image, 'PNG')
        journal = SimpleNamespace(title='Artigo', slug='artigo', description='Resumo',
                                  cover_image='https://example.org/cover.png',
                                  content_markdown='![Figura 1](https://example.org/figure.png)',
                                  guidelines='', references='Referência científica')
        with app.test_request_context(), patch('journal_pdf.load_image', return_value=image.getvalue()) as fetch:
            response = render_journal_pdf(journal)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(response.mimetype, 'application/pdf')
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertIn(b'/Subtype /Image', response.data)

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
