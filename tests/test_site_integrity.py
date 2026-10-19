"""Reproduced persistence and numeric-input regressions from the site audit."""
import unittest
from bs4 import BeautifulSoup
import test_article_history as history
import test_article_autosave as autosave
import test_reader_accounts as readers
from app import app, render_markdown
from models import db
from governance_models import ArticleRevision
from request_values import pagination_page


class RequestValueTests(unittest.TestCase):
    def test_pages_are_positive_bounded_and_keep_valid_navigation(self):
        for value, expected in [('2',2),('0002',2),('0',1),('-2',1),('abc',1),('9'*100,1),('2147483647',2147483647),('2147483648',1)]:
            with self.subTest(value=value), app.test_request_context('/?page='+value+'&pagina=3'):
                self.assertEqual(pagination_page(), expected)
                self.assertEqual(pagination_page('pagina'),3)


class EditorialIntegrityTests(unittest.TestCase):
    setUp = history.ArticleHistoryTests.setUp
    tearDown = history.ArticleHistoryTests.tearDown
    member = history.ArticleHistoryTests.member
    article = history.ArticleHistoryTests.article
    signin = history.ArticleHistoryTests.signin
    post = history.ArticleHistoryTests.post
    edit = history.ArticleHistoryTests.edit
    save = autosave.ArticleAutosaveTests.save

    def test_manual_and_automatic_save_preserve_markdown_and_history(self):
        owner=self.member(); article=self.article(owner); self.signin(owner.admin)
        for automatic in [False,True]:
            body='    print("indentação preservada")\n\nParágrafo '+str(automatic)+'  \n'
            references='    fonte indentada\n\nReferência final  \n'
            response=self.save(article,body=body,references=references) if automatic else self.edit(article,body,references=references)
            self.assertEqual(response.status_code,200 if automatic else 302)
            db.session.refresh(article)
            self.assertEqual(article.body,body)
            self.assertEqual(article.references,references)
            latest=ArticleRevision.query.filter_by(article_id=article.id).order_by(ArticleRevision.number.desc()).first()
            self.assertEqual(latest.snapshot['body'],body)
            soup=BeautifulSoup(str(render_markdown(article.body)),'html.parser')
            self.assertIn('indentação preservada',soup.select_one('pre code').text)

    def test_journal_save_preserves_content_and_reference_indentation(self):
        self.signin(self.primary)
        body='    exemplo de código\n\nTexto  \n'
        references='    referência indentada\n'
        response=self.post('/admin/revistas/'+str(self.journal.id)+'/editar',title=self.journal.title,
            field=self.journal.field,description=self.journal.description,slug=self.journal.slug,
            content_markdown=body,references=references,save_mode='draft')
        self.assertEqual(response.status_code,302)
        db.session.refresh(self.journal)
        self.assertEqual(self.journal.content_markdown,body)
        self.assertEqual(self.journal.references,references)

    def test_public_and_editorial_pagination_and_route_ids_cannot_overflow(self):
        owner=self.member(); article=self.article(owner)
        huge='9'*100
        for path in ['/artigos?page='+huge,'/autor/'+owner.author.slug+'?pagina='+huge]:
            self.assertEqual(self.client.get(path).status_code,200)
        for path in ['/artigo/'+huge,'/autor/'+huge,'/admin/artigos/'+huge+'/editar','/submissoes/'+huge]:
            self.assertEqual(self.client.get(path).status_code,404)
        self.signin(self.primary)
        self.assertEqual(self.client.get('/admin/submissoes?page='+huge).status_code,200)
        self.assertEqual(self.post('/admin/notificacoes',action='read',id=huge).status_code,404)


class ReaderIntegrityTests(unittest.TestCase):
    setUpClass=classmethod(readers.ReaderAccountTests.setUpClass.__func__)
    setUp=readers.ReaderAccountTests.setUp
    tearDown=readers.ReaderAccountTests.tearDown
    sign_in=readers.ReaderAccountTests.sign_in

    def test_account_lists_handle_oversized_pages_and_notice_ids(self):
        self.sign_in()
        huge='9'*100
        for path in ['/conta/notificacoes','/submissoes/notificacoes','/submissoes/']:
            self.assertEqual(self.client.get(path+'?page='+huge).status_code,200)
        response=self.client.post('/conta/notificacoes',data={'csrf_token':'reader-csrf','action':'delete','id':huge})
        self.assertEqual(response.status_code,404)
