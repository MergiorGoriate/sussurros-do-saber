"""Exercise actual HTTP routes, editorial forms and historical snapshots in SQLite."""
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

# Existing platform fixture selects a temporary database before importing Flask.
import test_platform
import test_staff_governance as fixtures
from app import app, render_markdown
from models import AdminUser, Article, Journal, db
from governance_models import ArticleRevision
from sqlalchemy import MetaData, Table, select
from bs4 import BeautifulSoup
from test_article_seo_maintenance import seo


class ArticleSEOIntegrationTests(unittest.TestCase):
    tearDown = fixtures.StaffGovernanceTests.tearDown
    member = fixtures.StaffGovernanceTests.member
    article = fixtures.StaffGovernanceTests.article
    signin = fixtures.StaffGovernanceTests.signin
    post = fixtures.StaffGovernanceTests.post

    def setUp(self):
        fixtures.StaffGovernanceTests.setUp(self)
        from extensions import limiter
        limiter_patch = patch.object(limiter, 'enabled', False)
        limiter_patch.start()
        self.addCleanup(limiter_patch.stop)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.output = Path(temp.name)

    def test_real_page_metadata_hierarchy_and_decorative_images(self):
        owner = self.member()
        item = self.article(owner)
        item.status = 'published'
        item.title = 'Processos celulares: ' + self.token
        item.summary = 'Este artigo descreve processos celulares e explica a relação entre a estrutura e a função das células.'
        item.body = '## Secção\n\n### Parte\n\n#### Detalhe\n\n##### Contexto\n\n###### Nota\n\n![](https://example.org/decorativa.jpg)\n\n![Diagrama de uma célula](https://example.org/celula.jpg)'
        db.session.commit()
        response = app.test_client().get('/artigo/' + item.slug)
        self.assertEqual(response.status_code, 200)
        report = seo.inspect_html(response.text)
        self.assertTrue(report['passed'], report)
        self.assertEqual(report['h1'], [item.title])
        soup = BeautifulSoup(response.data, 'html.parser')
        self.assertEqual(soup.select_one('.article-markdown h5').text, 'Contexto')
        self.assertEqual(soup.select_one('.article-markdown h6').text, 'Nota')
        self.assertEqual([im['alt'] for im in soup.select('.article-markdown img')], ['', 'Diagrama de uma célula'])

    def test_data_changes_visible_publicly_and_editable_in_existing_panel(self):
        owner = self.member()
        item = self.article(owner)
        item.status = 'published'
        item.title = 'Processos celulares: ' + self.token
        item.summary = 'Este artigo descreve processos celulares e explica a relação entre a estrutura e a função das células.'
        item.body = '# ' + item.title + '\n\n### Secção\n\n##### Subsecção\n\nTexto e [fonte](https://example.org).'
        item.references = 'Referência preservada.'
        item.doi = '10.0000/exemplo-' + self.token
        db.session.commit()
        primary_id = self.primary.id
        original_url = '/artigo/' + item.slug
        table = Table('article', MetaData(), autoload_with=db.engine)
        with db.engine.connect() as connection:
            before = dict(connection.execute(select(table).where(table.c.id == item.id)).mappings().one())
        after = {'title': 'Estrutura celular: ' + self.token,
                 'summary': 'O artigo examina a estrutura das células e a relação das suas partes com os processos celulares descritos.',
                 'body': seo.structure_body(item.body, item.title)}
        plan = {'articles': [{'id': item.id, 'fingerprint': seo.digest(before), 'after': after,
                             'reviewed': True, 'reason': 'Caso sintético de integração.'}]}
        db.session.remove()
        result = seo.change(db.engine, plan, self.output / 'before.json', 'Teste de integração')
        self.assertEqual(result['changed'], 1)
        saved = db.session.get(Article, before['id'])
        for name in ('slug', 'doi', 'references', 'author_id', 'category_id', 'status', 'published_at', 'created_at', 'image'):
            self.assertEqual(getattr(saved, name), before[name])
        response = app.test_client().get(original_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(seo.inspect_html(response.text)['passed'])
        self.signin(db.session.get(AdminUser, primary_id))
        form = self.client.get(f'/admin/artigos/{saved.id}/editar')
        self.assertEqual(form.status_code, 200)
        soup = BeautifulSoup(form.data, 'html.parser')
        self.assertEqual(soup.select_one('[name="title"]')['value'], after['title'])
        self.assertEqual(soup.select_one('[name="summary"]').text, after['summary'])
        self.assertEqual(soup.select_one('[name="body"]').text, after['body'])
        versions = ArticleRevision.query.filter_by(article_id=saved.id).order_by(ArticleRevision.number).all()
        self.assertEqual(len(versions), 2)
        self.assertEqual(versions[0].snapshot['body'], before['body'])
        recovery = json.loads((self.output / 'before.json').read_text())
        db.session.remove()
        seo.change(db.engine, recovery, self.output / 'undo.json', 'Teste de integração', restore=True)
        self.assertEqual(db.session.get(Article, before['id']).body, before['body'])
        self.assertEqual(app.test_client().get(original_url).status_code, 200)

    def test_editor_title_change_without_slug_preserves_existing_address(self):
        owner = self.member()
        item = self.article(owner)
        old_slug = item.slug
        self.signin(self.primary)
        response = self.post(f'/admin/artigos/{item.id}/editar', title='Novo título científico',
            summary=item.summary, body=item.body, status='draft', author_id=item.author_id,
            category_id=item.category_id, version_token=item.updated_at.isoformat())
        self.assertEqual(response.status_code, 302)
        db.session.refresh(item)
        self.assertEqual(item.slug, old_slug)
        self.assertEqual(item.title, 'Novo título científico')

    def test_journal_form_keeps_its_own_slug_path_without_article_variable(self):
        self.signin(self.primary)
        response = self.post('/admin/revistas/nova', title='Revista de teste ' + self.token,
            field='Biologia', description='Uma revista para verificar o formulário científico existente.')
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(Journal.query.filter_by(title='Revista de teste ' + self.token).one())

    def test_existing_article_permissions_still_reject_another_author(self):
        owner = self.member()
        other = self.member()
        item = self.article(owner)
        self.signin(other.admin)
        self.assertEqual(self.client.get(f'/admin/artigos/{item.id}/editar').status_code, 404)
