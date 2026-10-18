"""Private history, restoration and protection against concurrent edits."""
import unittest
from unittest.mock import patch
import test_staff_governance as fixtures
from app import app
from models import db, utcnow
from governance_models import ArticleRevision, ArticleWorkflow, PortalReview

class ArticleHistoryTests(unittest.TestCase):
    def setUp(self):
        fixtures.StaffGovernanceTests.setUp(self)
        from extensions import limiter
        patcher=patch.object(limiter,'enabled',False);patcher.start();self.addCleanup(patcher.stop)
    tearDown=fixtures.StaffGovernanceTests.tearDown
    member=fixtures.StaffGovernanceTests.member
    article=fixtures.StaffGovernanceTests.article
    signin=fixtures.StaffGovernanceTests.signin
    post=fixtures.StaffGovernanceTests.post

    def edit(self,article,body,**extra):
        data=dict(title=article.title,summary=article.summary,body=body,status='draft',slug=article.slug,author_id=article.author_id,category_id=article.category_id,version_token=article.updated_at.isoformat())
        data.update(extra)
        return self.post(f'/admin/artigos/{article.id}/editar',**data)

    def test_history_baseline_comparison_and_restore_preserve_review_but_unpublish(self):
        owner=self.member();reviewer=self.member('portal_reviewer');article=self.article(owner)
        original=article.body;slug=article.slug;author=article.author_id
        self.signin(self.primary)
        path=f'/admin/artigos/{article.id}/historico'
        self.assertEqual(self.client.get(path).status_code,200)
        self.assertEqual(ArticleRevision.query.filter_by(article_id=article.id).count(),0)
        self.assertEqual(self.edit(article,'Texto novo completo. '*8,references='Fontes novas').status_code,302)
        versions=ArticleRevision.query.filter_by(article_id=article.id).order_by(ArticleRevision.number).all()
        self.assertEqual([v.number for v in versions],[1,2])
        self.assertEqual(versions[0].snapshot['body'],original)
        self.assertEqual(versions[1].actor_id,self.primary.id)
        self.assertIn('Texto novo',self.client.get(path+'?version='+str(versions[0].id)).text)
        flow=db.session.get(ArticleWorkflow,article.id)
        flow.stage=article.status='published';flow.approved_at=flow.reviewed_at=utcnow();flow.reviewer=reviewer
        report=PortalReview(article_id=article.id,reviewer_id=reviewer.id,action='reviewed',report='Parecer que deve permanecer no histórico.')
        db.session.add(report);db.session.commit()
        restore=f'/admin/artigos/{article.id}/historico/{versions[0].id}/recuperar'
        token=article.updated_at.isoformat()
        self.assertEqual(self.post(restore,confirm='yes',version_token=token).status_code,303)
        self.assertEqual(article.body,original)
        self.assertEqual((article.status,flow.stage),('draft','draft'))
        self.assertIsNone(flow.approved_at);self.assertIsNone(flow.reviewed_at)
        self.assertEqual(article.slug,slug);self.assertEqual(article.author_id,author)
        self.assertIsNotNone(db.session.get(PortalReview,report.id))
        self.assertEqual(ArticleRevision.query.filter_by(article_id=article.id).count(),3)
        self.assertEqual(app.test_client().get('/artigo/'+slug).status_code,404)

    def test_ownership_scoping_csrf_confirmation_and_stale_restore(self):
        owner=self.member();other=self.member();article=self.article(owner);another=self.article(other)
        self.signin(owner.admin)
        self.edit(article,'Novo conteúdo de teste. '*10)
        revision=ArticleRevision.query.filter_by(article_id=article.id).first()
        path=f'/admin/artigos/{article.id}/historico/{revision.id}/recuperar'
        self.assertEqual(self.post(path,version_token=article.updated_at.isoformat()).status_code,400)
        self.assertEqual(self.client.post(path,data={'confirm':'yes'}).status_code,400)
        self.assertEqual(self.post(path,confirm='yes',version_token='stale').status_code,409)
        self.assertEqual(self.post(f'/admin/artigos/{another.id}/historico/{revision.id}/recuperar',confirm='yes').status_code,404)
        self.signin(other.admin)
        self.assertEqual(self.client.get(f'/admin/artigos/{article.id}/historico').status_code,404)
        self.signin(self.primary)
        self.assertEqual(self.client.get(f'/admin/artigos/{another.id}/historico?version={revision.id}').status_code,404)
        self.assertEqual(self.post(f'/admin/artigos/{another.id}/historico/{revision.id}/recuperar',confirm='yes').status_code,404)

    def test_stale_form_does_not_overwrite_and_failed_validation_creates_no_version(self):
        owner=self.member();article=self.article(owner);self.signin(owner.admin)
        old_token=article.updated_at.isoformat()
        self.assertEqual(self.edit(article,'Primeira alteração válida. '*8).status_code,302)
        saved=article.body;count=ArticleRevision.query.filter_by(article_id=article.id).count()
        response=self.edit(article,'Texto de um formulário antigo.',version_token=old_token)
        self.assertEqual(response.status_code,409)
        self.assertIn('formulário antigo',response.text)
        self.assertEqual(article.body,saved)
        self.assertEqual(self.edit(article,'Texto inválido.',title='x').status_code,200)
        self.assertEqual(ArticleRevision.query.filter_by(article_id=article.id).count(),count)

    def test_comparison_escapes_html_and_unchanged_content_does_not_duplicate(self):
        owner=self.member();article=self.article(owner);self.signin(self.primary)
        self.edit(article,'<script>alert(1)</script> Texto de teste. '*4)
        count=ArticleRevision.query.filter_by(article_id=article.id).count()
        self.edit(article,article.body)
        self.assertEqual(ArticleRevision.query.filter_by(article_id=article.id).count(),count)
        response=self.client.get(f'/admin/artigos/{article.id}/historico')
        self.assertNotIn('<script>alert(1)</script>',response.text)
        self.assertIn('&lt;script&gt;',response.text)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
