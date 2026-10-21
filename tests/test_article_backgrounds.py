"""Article presentation follows the existing editor, permissions and lifecycle."""
import unittest
from datetime import timedelta
from bs4 import BeautifulSoup
import test_article_history as history
from app import app
from models import Article, db, utcnow
from governance_models import ArticleRevision, ArticleWorkflow


class ArticleBackgroundTests(unittest.TestCase):
    setUp = history.ArticleHistoryTests.setUp
    tearDown = history.ArticleHistoryTests.tearDown
    member = history.ArticleHistoryTests.member
    article = history.ArticleHistoryTests.article
    signin = history.ArticleHistoryTests.signin
    post = history.ArticleHistoryTests.post

    def edit(self, article, **extra):
        values={name:getattr(article,name) or '' for name in ('title','summary','body','references','keywords','doi','image','cover_video','slug')}
        values.update(author_id=article.author_id,category_id=article.category_id,read_minutes=article.read_minutes,
                      status=article.status,version_token=article.updated_at.isoformat())
        values.update(extra)
        return self.post(f'/admin/artigos/{article.id}/editar',**values)

    def public(self, article):
        return app.test_client().get('/artigo/'+article.slug)

    def test_new_article_and_absent_or_invalid_values_use_default(self):
        owner=self.member();article=self.article(owner);self.signin(owner.admin)
        self.assertEqual(article.background,'default')
        self.assertEqual(Article(background=None).background_style,'default')
        for value in ['aged_paper injected-class','<style>body{display:none}</style>','',None]:
            kwargs={} if value is None else {'background':value}
            article.background='aged_paper';db.session.commit()
            self.assertEqual(self.edit(article,**kwargs).status_code,302)
            self.assertEqual(article.background,'default')
        # Create through the actual form, omitting the additive field.
        values=dict(title='Artigo novo com fundo padrão',summary='Resumo científico para criação de artigo.',body='Conteúdo científico. '*10,
                    status='draft',author_id=article.author_id,category_id=article.category_id)
        self.assertEqual(self.post('/admin/artigos/novo',**values).status_code,302)
        self.assertEqual(Article.query.filter_by(title=values['title']).one().background,'default')

    def test_save_reopen_public_isolation_and_presentation_scope(self):
        owner=self.member();article=self.article(owner);other=self.article(owner);self.signin(owner.admin)
        self.assertEqual(self.edit(article,background='aged_paper').status_code,302)
        ident=article.id;db.session.expire_all()
        self.assertEqual(db.session.get(Article,ident).background,'aged_paper')
        page=BeautifulSoup(self.client.get(f'/admin/artigos/{ident}/editar').data,'html.parser')
        self.assertIsNotNone(page.select_one('input[name=background][value=aged_paper][checked]'))
        article.status=other.status='published';db.session.commit()
        response=self.public(article);self.assertEqual(response.status_code,200)
        soup=BeautifulSoup(response.data,'html.parser');paper=soup.select_one('.article-page>.article-paper')
        self.assertIsNotNone(paper.select_one('.article-title'));self.assertIsNotNone(paper.select_one('.article-markdown'))
        self.assertIsNone(paper.select_one('.share-panel,.article-comments,.article-related,nav,footer'))
        self.assertFalse(BeautifulSoup(self.public(other).data,'html.parser').select('.article-paper'))
        self.assertEqual(other.background,'default')
        # An unknown legacy/database value never becomes an HTML class or style.
        article.background='aged_paper arbitrary-css';db.session.commit()
        self.assertNotIn('article-paper"',self.public(article).text)
        self.assertNotIn('arbitrary-css',self.public(article).text)

    def test_background_survives_publication_scheduling_and_text_autosave(self):
        owner=self.member();article=self.article(owner);self.signin(self.primary)
        self.assertEqual(self.edit(article,background='aged_paper').status_code,302)
        flow=db.session.get(ArticleWorkflow,article.id);flow.approved_at=flow.reviewed_at=utcnow();flow.stage='approved';db.session.commit()
        future=utcnow()+timedelta(days=2)
        self.assertEqual(self.edit(article,background='aged_paper',status='scheduled',scheduled_at=future.strftime('%Y-%m-%dT%H:%M')).status_code,302)
        self.assertEqual(article.background,'aged_paper');self.assertEqual(self.public(article).status_code,404)
        article.scheduled_at=utcnow()-timedelta(minutes=1);db.session.commit()
        Article.publish_due_scheduled()
        self.assertEqual(article.status,'published');self.assertEqual(article.background,'aged_paper')
        self.assertIn('data-article-background="aged_paper"',self.public(article).text)
        self.assertEqual(self.edit(article,background='default',status='published',scheduled_at='').status_code,302)
        self.assertEqual(article.background,'default')
        article.status=flow.stage='draft';article.background='aged_paper';db.session.commit()
        data={name:getattr(article,name) or '' for name in ('title','summary','body','references','keywords','doi')}
        data.update(body='Novo texto guardado automaticamente. '*8,read_minutes=5,version_token=article.updated_at.isoformat(),background='default')
        self.assertEqual(self.post(f'/admin/artigos/{article.id}/rascunho',**data).status_code,200)
        self.assertEqual(article.background,'aged_paper')

    def test_history_restores_background_and_old_snapshots_fall_back_to_default(self):
        owner=self.member();article=self.article(owner);self.signin(owner.admin)
        self.assertEqual(self.edit(article,background='aged_paper').status_code,302)
        versions=ArticleRevision.query.filter_by(article_id=article.id).order_by(ArticleRevision.number).all()
        self.assertEqual(versions[0].snapshot['background'],'default');self.assertEqual(versions[1].snapshot['background'],'aged_paper')
        previous=dict(versions[0].snapshot);previous.pop('background');versions[0].snapshot=previous;db.session.commit()
        self.assertEqual(self.post(f'/admin/artigos/{article.id}/historico/{versions[0].id}/recuperar',confirm='yes',version_token=article.updated_at.isoformat()).status_code,303)
        self.assertEqual(article.background,'default');self.assertEqual(article.status,'draft')
        self.assertEqual(self.post(f'/admin/artigos/{article.id}/historico/{versions[1].id}/recuperar',confirm='yes',version_token=article.updated_at.isoformat()).status_code,303)
        self.assertEqual(article.background,'aged_paper')

    def test_unauthorized_csrf_and_stale_edits_do_not_change_background(self):
        owner=self.member();other=self.member();article=self.article(owner)
        self.signin(other.admin);self.assertEqual(self.edit(article,background='aged_paper').status_code,404)
        self.signin(owner.admin)
        self.assertEqual(self.client.post(f'/admin/artigos/{article.id}/editar',data={'background':'aged_paper'}).status_code,400)
        self.assertEqual(self.edit(article,background='aged_paper',version_token='stale').status_code,409)
        self.assertEqual(article.background,'default')
        owner.appointments[0].active=False;db.session.commit()
        self.assertIn(self.edit(article,background='aged_paper').status_code,(302,403))
        self.assertEqual(article.background,'default')
