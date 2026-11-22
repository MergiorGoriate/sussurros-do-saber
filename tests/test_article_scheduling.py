"""Schedule via the existing editor and run the existing publication lifecycle."""
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
import test_platform
from app import app
from models import db, Article, Author, utcnow
from governance_models import ArticleWorkflow, GovernanceAudit
from article_scheduling import parse_schedule, schedule_local
import test_site_audit_regressions as fixtures


class ArticleSchedulingTests(unittest.TestCase):
    setUp=fixtures.SiteAuditRegressions.setUp
    tearDown=fixtures.SiteAuditRegressions.tearDown
    member=fixtures.SiteAuditRegressions.member
    article=fixtures.SiteAuditRegressions.article
    signin=fixtures.SiteAuditRegressions.signin
    post=fixtures.SiteAuditRegressions.post
    fields=fixtures.SiteAuditRegressions.fields

    def schedule(self,article,**extra):
        values=dict(status='scheduled',scheduled_at=(utcnow()+timedelta(days=3)).strftime('%Y-%m-%dT%H:%M'),schedule_timezone='Africa/Maputo')
        values.update(extra)
        return self.post(f'/admin/artigos/{article.id}/editar',**self.fields(article,**values))

    def test_primary_editor_can_schedule_draft_without_publishing_early(self):
        article=self.article(self.member());path=f'/admin/artigos/{article.id}/editar'
        self.assertIn('value="scheduled"',self.client.get(path).text)
        self.assertEqual(self.schedule(article,scheduled_at='2099-01-02T12:30').status_code,302)
        self.assertEqual(article.scheduled_at,datetime(2099,1,2,10,30))
        self.assertEqual(article.status,'scheduled')
        flow=db.session.get(ArticleWorkflow,article.id)
        self.assertEqual(flow.stage,'scheduled');self.assertIsNotNone(flow.approved_at)
        self.assertIsNone(flow.reviewed_at)
        self.assertEqual(app.test_client().get('/artigo/'+article.slug).status_code,404)
        self.assertEqual(GovernanceAudit.query.filter_by(action='article.schedule',entity_id=article.id).count(),1)
        self.assertEqual(GovernanceAudit.query.filter_by(action='article.publish',entity_id=article.id).count(),0)

    def test_new_article_with_unlinked_author_can_be_scheduled(self):
        author=Author(name='Autor sem vínculo '+self.token,slug='schedule-'+self.token)
        db.session.add(author);db.session.commit()
        response=self.post('/admin/artigos/novo',title='Novo artigo programado '+self.token,
            slug='scheduled-new-'+self.token,summary='Resumo completo do artigo programado.',body='Conteúdo completo e fundamentado. '*10,
            author_id=author.id,category_id=self.category.id,status='scheduled',scheduled_at='2099-01-01T12:00',schedule_timezone='Africa/Maputo')
        self.assertEqual(response.status_code,302)
        article=Article.query.filter_by(slug='scheduled-new-'+self.token).one()
        flow=db.session.get(ArticleWorkflow,article.id)
        self.assertTrue(flow.primary_owned);self.assertEqual(flow.stage,'scheduled')
        self.assertEqual(article.scheduled_at,datetime(2099,1,1,10))
        self.assertEqual(app.test_client().get('/artigo/'+article.slug).status_code,404)

    def test_due_schedule_publishes_once_without_http_request(self):
        article=self.article(self.member());self.assertEqual(self.schedule(article).status_code,302)
        article.scheduled_at=utcnow()-timedelta(minutes=1);db.session.commit()
        path = '/artigo/' + article.slug
        with patch.dict(app.config, {'PUBLISH_SCHEDULED_ON_REQUEST': False}):
            self.assertEqual(app.test_client().get(path).status_code, 404)
            result=app.test_cli_runner().invoke(args=['admin','publicar-programados'])
            self.assertEqual(app.test_client().get(path).status_code, 200)
        self.assertEqual(result.exit_code,0,result.output+str(result.exception))
        db.session.refresh(article);self.assertEqual(article.status,'published')
        self.assertEqual(article.published_at,article.scheduled_at)
        result=app.test_cli_runner().invoke(args=['admin','publicar-programados'])
        self.assertEqual(result.exit_code,0);self.assertIn('0 artigo(s)',result.output)
        self.assertEqual(GovernanceAudit.query.filter_by(action='article.publish',entity_id=article.id).count(),1)

    def test_reschedule_and_cancel_via_draft_clear_pending_date(self):
        article=self.article(self.member());self.assertEqual(self.schedule(article).status_code,302)
        self.assertEqual(self.schedule(article,scheduled_at='2099-01-03T14:00').status_code,302)
        self.assertEqual(article.scheduled_at,datetime(2099,1,3,12))
        response=self.post(f'/admin/artigos/{article.id}/editar',**self.fields(article,status='draft',scheduled_at='2099-01-03T14:00'))
        self.assertEqual(response.status_code,302);self.assertIsNone(article.scheduled_at)
        self.assertIsNone(db.session.get(ArticleWorkflow,article.id).approved_at)
        self.assertEqual(Article.publish_due_scheduled(),0)

    def test_invalid_missing_past_date_and_unknown_timezone_are_not_saved(self):
        article=self.article(self.member())
        for fields in [dict(scheduled_at=''),dict(scheduled_at='invalid'),dict(scheduled_at='2000-01-01T12:00'),dict(schedule_timezone='Unknown/Zone')]:
            with self.subTest(fields=fields):
                self.assertEqual(self.schedule(article,**fields).status_code,200)
                db.session.refresh(article);self.assertEqual(article.status,'draft')

    def test_secondary_author_cannot_bypass_editorial_approval(self):
        owner=self.member();article=self.article(owner);self.signin(owner.admin)
        self.assertNotIn('value="scheduled"',self.client.get(f'/admin/artigos/{article.id}/editar').text)
        self.assertIn(self.schedule(article).status_code,[403,409])
        db.session.refresh(article);self.assertEqual(article.status,'draft')

    def test_edit_displays_local_time_and_preserves_invalid_input(self):
        article=self.article(self.member());self.schedule(article,scheduled_at='2099-01-02T12:30')
        response=self.client.get(f'/admin/artigos/{article.id}/editar')
        self.assertIn('value="2099-01-02T12:30"',response.text)
        self.assertIn('value="2000-01-01T12:00"',self.schedule(article,scheduled_at='2000-01-01T12:00').text)

    def test_timezone_roundtrip_and_legacy_utc_contract(self):
        self.assertEqual(parse_schedule('2099-01-01T00:30','Africa/Maputo'),datetime(2098,12,31,22,30))
        self.assertEqual(parse_schedule('2099-01-01T12:00'),datetime(2099,1,1,12))
        self.assertEqual(parse_schedule('2099-01-01T12:00+02:00'),datetime(2099,1,1,10))
        self.assertEqual(schedule_local(datetime(2099,1,1,10)),'2099-01-01T12:00')
