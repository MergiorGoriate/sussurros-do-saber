"""Approval publishes atomically and public lists show the committed version."""
import unittest
from datetime import timedelta
import test_staff_governance as fixtures
from app import app
from models import Article, db, utcnow
from governance_models import ArticleWorkflow, GovernanceAudit

class ApprovalPublicationTests(unittest.TestCase):
    def setUp(self):
        fixtures.StaffGovernanceTests.setUp(self)
        from unittest.mock import patch
        from extensions import limiter
        patcher = patch.object(limiter, 'enabled', False)
        patcher.start()
        self.addCleanup(patcher.stop)
    tearDown=fixtures.StaffGovernanceTests.tearDown
    member=fixtures.StaffGovernanceTests.member
    article=fixtures.StaffGovernanceTests.article
    signin=fixtures.StaffGovernanceTests.signin
    post=fixtures.StaffGovernanceTests.post

    def reviewed(self):
        owner=self.member(); reviewer=self.member('portal_reviewer'); editor=self.member('portal_editor')
        article=self.article(owner)
        path=f'/admin/fluxo-artigos/{article.id}'
        self.signin(editor.admin)
        self.assertEqual(self.post(path,action='assign',reviewer_id=reviewer.id).status_code,302)
        self.signin(reviewer.admin)
        self.assertEqual(self.post(path,action='reviewed',note='Revisão independente com fontes conferidas.').status_code,302)
        self.signin(editor.admin)
        return article, path, editor

    def test_approval_publishes_and_surfaces_immediately_with_many_old_featured_articles(self):
        article,path,editor=self.reviewed()
        for number in range(11):
            old=Article(title=f'Destaque antigo {number}',slug=f'old-{number}-{self.token}',summary='Resumo',body='Texto',author_id=article.author_id,category_id=article.category_id,status='published',featured=True,published_at=utcnow()-timedelta(days=2))
            db.session.add(old)
        db.session.commit()
        public=app.test_client()
        self.assertEqual(public.get('/artigo/'+article.slug).status_code,404)
        self.assertNotIn(article.slug,public.get('/').text)
        page=self.client.get(path).text
        self.assertIn('Aprovar e publicar artigo',page)
        self.assertEqual(self.post(path,action='approve').status_code,302)
        flow=db.session.get(ArticleWorkflow,article.id)
        self.assertEqual((article.status,flow.stage),('published','published'))
        self.assertIsNotNone(flow.approved_at);self.assertIsNotNone(article.published_at)
        self.assertEqual(flow.editor_id,editor.id)
        self.assertEqual(public.get('/artigo/'+article.slug).status_code,200)
        for url in ['/', '/artigos', '/feed.xml', '/sitemap.xml', '/autor/'+flow.owner.author.slug]:
            response=public.get(url)
            self.assertIn(article.slug,response.text,url)
            self.assertIn('must-revalidate',response.headers['Cache-Control'],url)
        self.assertIn(article.id,[a['id'] for a in public.get('/api/artigos').json])
        self.assertIn('Ver artigo publicado',self.client.get(path).text)
        published_at=article.published_at
        self.assertEqual(self.post(path,action='approve').status_code,302)
        self.assertEqual(article.published_at,published_at)
        self.assertEqual(GovernanceAudit.query.filter_by(action='article.approve',entity_id=article.id).count(),1)
        self.assertEqual(GovernanceAudit.query.filter_by(action='article.publish',entity_id=article.id).count(),1)

    def test_existing_valid_approval_publishes_once_but_future_schedule_stays_private(self):
        article,path,editor=self.reviewed()
        flow=db.session.get(ArticleWorkflow,article.id)
        flow.stage=article.status='approved';flow.approved_at=utcnow();flow.editor=editor
        scheduled=self.article(flow.owner)
        sf=db.session.get(ArticleWorkflow,scheduled.id)
        sf.stage=scheduled.status='scheduled';sf.approved_at=utcnow();scheduled.scheduled_at=utcnow()+timedelta(days=1)
        db.session.commit()
        public=app.test_client()
        self.assertIn(article.slug,public.get('/artigos').text)
        self.assertEqual(article.status,'published')
        self.assertEqual(public.get('/artigo/'+scheduled.slug).status_code,404)
        public.get('/artigos')
        self.assertEqual(GovernanceAudit.query.filter_by(action='article.publish',entity_id=article.id).count(),1)

    def test_unreviewed_or_conflicting_approval_cannot_become_public(self):
        owner=self.member(); article=self.article(owner)
        flow=db.session.get(ArticleWorkflow,article.id)
        flow.stage=article.status='approved';flow.approved_at=utcnow()
        db.session.commit()
        self.assertEqual(app.test_client().get('/artigo/'+article.slug).status_code,404)
        flow.reviewer=owner;flow.reviewed_at=utcnow();db.session.commit()
        self.assertEqual(app.test_client().get('/artigo/'+article.slug).status_code,404)
