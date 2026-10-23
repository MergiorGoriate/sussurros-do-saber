"""Only the authenticated principal may publish without an independent review."""
import os
import time
import unittest
from unittest.mock import patch
from app import app
from admin import admin_security_stamp
from models import db, Article, Author, utcnow
from governance_models import ArticleWorkflow, GovernanceAudit, PortalReview
import test_staff_governance as fixtures


class PrimaryDirectPublicationTests(unittest.TestCase):
    def setUp(self):
        fixtures.StaffGovernanceTests.setUp(self)
        from extensions import limiter
        patcher=patch.object(limiter,'enabled',False)
        patcher.start();self.addCleanup(patcher.stop)

    tearDown=fixtures.StaffGovernanceTests.tearDown
    signin=fixtures.StaffGovernanceTests.signin
    member=fixtures.StaffGovernanceTests.member
    article=fixtures.StaffGovernanceTests.article
    post=fixtures.StaffGovernanceTests.post

    def test_principal_can_publish_every_workflow_stage_without_review(self):
        owner=self.member()
        for stage in ['draft','submitted','review','changes','approved','scheduled']:
            with self.subTest(stage=stage):
                article=self.article(owner)
                flow=db.session.get(ArticleWorkflow,article.id)
                article.status=flow.stage=stage
                db.session.commit();self.signin(self.primary)
                path=f'/admin/fluxo-artigos/{article.id}'
                self.assertIn('Publicar directamente',self.client.get(path).text)
                self.assertEqual(self.post(path,action='publish').status_code,302)
                self.assertEqual((article.status,flow.stage),('published','published'))
                self.assertIsNotNone(flow.approved_at)
                self.assertIsNone(flow.reviewed_at)
                self.assertIsNone(article.scheduled_at)
                self.assertEqual(PortalReview.query.filter_by(article_id=article.id).count(),0)
                event=GovernanceAudit.query.filter_by(action='article.publish',entity_id=article.id).one()
                self.assertEqual(event.actor_id,self.primary.id)
                self.assertIn('revisão dispensada',event.detail)
                published=article.published_at;approved=flow.approved_at
                self.assertEqual(self.post(path,action='approve').status_code,302)
                self.assertEqual((article.published_at,flow.approved_at),(published,approved))
                self.assertEqual(GovernanceAudit.query.filter_by(action='article.publish',entity_id=article.id).count(),1)
                self.assertEqual(app.test_client().get('/artigo/'+article.slug).status_code,200)

    def test_principal_can_approve_own_unlinked_article_without_staff_record(self):
        author=Author(name='Autoria principal',slug='direct-'+self.token)
        article=Article(title='Artigo do administrador principal',slug='direct-'+self.token,
                        summary='Resumo completo.',body='Texto fundamentado. '*10,author_rel=author,
                        category_id=self.category.id,status='draft')
        db.session.add(article);db.session.commit();self.signin(self.primary)
        self.assertEqual(self.post(f'/admin/fluxo-artigos/{article.id}',action='approve').status_code,302)
        flow=db.session.get(ArticleWorkflow,article.id)
        self.assertTrue(flow.primary_owned)
        self.assertIsNone(flow.owner_id)
        self.assertEqual(article.status,'published')
        self.assertIsNone(flow.reviewed_at)

    def test_principal_can_publish_article_of_removed_member_without_reactivating_account(self):
        owner=self.member();article=self.article(owner)
        owner.removed_at=utcnow();owner.status='ended';owner.admin.active=False
        db.session.delete(db.session.get(ArticleWorkflow,article.id));db.session.commit()
        self.signin(self.primary)
        self.assertEqual(self.post(f'/admin/fluxo-artigos/{article.id}',action='publish').status_code,302)
        self.assertEqual(article.status,'published')
        self.assertIsNotNone(owner.removed_at)
        self.assertFalse(owner.admin.active)

    def test_secondary_editor_and_publisher_cannot_publish_unreviewed_or_forge_primary_flag(self):
        owner=self.member();article=self.article(owner)
        path=f'/admin/fluxo-artigos/{article.id}'
        for role in ['portal_editor','publisher']:
            member=self.member(role);self.signin(member.admin)
            with self.client.session_transaction() as state:state['admin_superuser']=True
            self.assertNotIn('Publicar directamente',self.client.get(path).text)
            self.assertIn(self.post(path,action='publish').status_code,[403,409])
            self.assertEqual(article.status,'draft')
            self.assertIn(self.post(f'/admin/artigos/{article.id}/editar',title=article.title,
                                   summary=article.summary,body=article.body,status='published',
                                   author_id=article.author_id,category_id=article.category_id).status_code,[403,409])

    def test_direct_publication_requires_csrf_and_complete_content(self):
        article=self.article(self.member());self.signin(self.primary)
        path=f'/admin/fluxo-artigos/{article.id}'
        self.assertEqual(self.client.post(path,data={'action':'publish'}).status_code,400)
        article.body='Curto';db.session.commit()
        self.assertEqual(self.post(path,action='approve').status_code,400)
        self.assertEqual(article.status,'draft')
        self.assertIsNone(db.session.get(ArticleWorkflow,article.id).approved_at)

    def test_primary_form_can_publish_updated_content_and_change_authorship(self):
        owner=self.member();article=self.article(owner)
        flow=db.session.get(ArticleWorkflow,article.id)
        flow.reviewed_at=flow.approved_at=utcnow();flow.stage=article.status='approved'
        author=Author(name='Nova autoria directa',slug='new-direct-'+self.token)
        db.session.add(author);db.session.commit();self.signin(self.primary)
        response=self.post(f'/admin/artigos/{article.id}/editar',title=article.title,
                           summary=article.summary,body=article.body+' Texto actualizado.',status='published',
                           author_id=author.id,category_id=article.category_id)
        self.assertEqual(response.status_code,302)
        self.assertEqual(article.author_id,author.id)
        self.assertIsNone(flow.owner_id)
        self.assertIsNone(flow.reviewed_at)
        self.assertEqual((flow.stage,article.status),('published','published'))

    def test_environment_primary_can_publish_without_database_account(self):
        article=self.article(self.member())
        with patch.dict(os.environ,{'ADMIN_USERNAME':'direct-env','ADMIN_TOTP_SECRET':'JBSWY3DPEHPK3PXP'}):
            with app.test_request_context():stamp=admin_security_stamp()
            with self.client.session_transaction() as state:
                state.clear();state.update(admin_authenticated=True,admin_id=None,admin_username='direct-env',
                    admin_2fa_verified=True,admin_superuser=True,admin_security_stamp=stamp,
                    admin_last_activity_at=time.time(),csrf_token='test')
            self.assertEqual(self.post(f'/admin/fluxo-artigos/{article.id}',action='publish').status_code,302)
            self.assertEqual(article.status,'published')

    def test_changing_between_two_unlinked_authors_clears_old_review(self):
        first=Author(name='Primeiro autor',slug='first-'+self.token)
        second=Author(name='Segundo autor',slug='second-'+self.token)
        article=Article(title='Mudança de autoria sem membro',slug='change-'+self.token,
                        summary='Resumo completo.',body='Texto fundamentado. '*10,
                        author_rel=first,category_id=self.category.id,status='review')
        db.session.add_all([article,second]);db.session.flush()
        flow=ArticleWorkflow(article_id=article.id,primary_owned=True,stage='review',reviewed_at=utcnow())
        db.session.add(flow);db.session.commit();self.signin(self.primary)
        self.assertEqual(self.post(f'/admin/artigos/{article.id}/editar',title=article.title,
            summary=article.summary,body=article.body,status='published',author_id=second.id,
            category_id=article.category_id).status_code,302)
        self.assertIsNone(flow.reviewed_at)
        self.assertEqual(article.status,'published')
        self.assertEqual(article.author_id,second.id)

    def test_existing_reviews_are_preserved_when_principal_publishes(self):
        owner=self.member();reviewer=self.member('portal_reviewer');article=self.article(owner)
        report=PortalReview(article_id=article.id,reviewer_id=reviewer.id,action='changes',report='Correcções anteriores.')
        db.session.add(report);db.session.commit();self.signin(self.primary)
        self.assertEqual(self.post(f'/admin/fluxo-artigos/{article.id}',action='publish').status_code,302)
        self.assertEqual(db.session.get(PortalReview,report.id).report,'Correcções anteriores.')
