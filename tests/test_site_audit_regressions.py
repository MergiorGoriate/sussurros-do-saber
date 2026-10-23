"""Confirmed editorial form, scheduling and identifier regressions."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import test_staff_governance as fixtures
from models import db, Author, Category, Article, utcnow
from governance_models import ArticleWorkflow, PortalReview


class SiteAuditRegressions(unittest.TestCase):
    def setUp(self):
        fixtures.StaffGovernanceTests.setUp(self)
        from extensions import limiter
        p=patch.object(limiter,'enabled',False);p.start();self.addCleanup(p.stop)
        self.signin(self.primary)

    tearDown=fixtures.StaffGovernanceTests.tearDown
    member=fixtures.StaffGovernanceTests.member
    article=fixtures.StaffGovernanceTests.article
    signin=fixtures.StaffGovernanceTests.signin
    post=fixtures.StaffGovernanceTests.post

    def fields(self, article, **extra):
        data={k:getattr(article,k) or '' for k in ('title','summary','body','references','keywords','doi','image','cover_video','slug')}
        data.update(author_id=article.author_id,category_id=article.category_id,status='draft')
        data.update(extra)
        return data

    def test_oversized_form_identifiers_never_reach_database_driver(self):
        huge='9'*100
        for path,data in [('/admin/autores',dict(author_id=huge,name='Nome')),
                          ('/admin/categorias',dict(category_id=huge,name='Nome'))]:
            with self.subTest(path=path):
                response=self.post(path,**data)
                self.assertIn(response.status_code,[302,400])
        article=self.article(self.member())
        for key in ['author_id','category_id']:
            with self.subTest(key=key):
                response=self.post(f'/admin/artigos/{article.id}/editar',**self.fields(article,**{key:huge}))
                self.assertIn(response.status_code,[200,400])

    def test_categories_cannot_share_a_normalized_url_or_have_an_empty_url(self):
        name='Área Única '+self.token
        self.assertEqual(self.post('/admin/categorias',name=name).status_code,200)
        existing=Category.query.filter_by(name=name).one()
        for alternate in ['Area Unica '+self.token,'!!!']:
            self.post('/admin/categorias',name=alternate)
            self.assertIsNone(Category.query.filter_by(name=alternate).first())
        self.assertEqual(Category.query.filter_by(slug=existing.slug).count(),1)

    def test_author_fields_fit_postgresql_limits_and_invalid_orcid_is_rejected(self):
        for index,extra in enumerate([dict(name='N'*121),dict(slug=self.token+'s'*161),dict(email='x'*170+'@example.org'),dict(orcid='0000-0000-0000-XX00')]):
            with self.subTest(extra=extra):
                data=dict(name='Nome '+self.token,slug='author-'+self.token+'-'+str(index))
                data.update(extra)
                self.post('/admin/autores',**data)
                self.assertIsNone(Author.query.filter_by(slug=data['slug']).first())

    def test_duplicate_maximum_article_slug_keeps_room_for_suffix(self):
        owner=self.member();first=self.article(owner);second=self.article(owner)
        long_slug=(self.token+'a'*260)[:260]
        first.slug=long_slug;db.session.commit()
        self.assertEqual(self.post(f'/admin/artigos/{second.id}/editar',**self.fields(second,slug=long_slug)).status_code,302)
        self.assertLessEqual(len(second.slug),260)
        self.assertNotEqual(first.slug,second.slug)

    def test_oversized_article_image_is_rejected_before_upload_or_save(self):
        article=self.article(self.member())
        with patch('admin.upload_article_image') as upload:
            response=self.post(f'/admin/artigos/{article.id}/editar',**self.fields(article,image='https://example.org/'+'a'*600))
            self.assertEqual(response.status_code,200)
            upload.assert_not_called()
        self.assertEqual(article.image,'')

    def test_editor_form_normalizes_schedule_timezone_to_utc(self):
        article=self.article(self.member());flow=db.session.get(ArticleWorkflow,article.id)
        article.status=flow.stage='approved';flow.approved_at=utcnow();db.session.commit()
        desired=(utcnow()+timedelta(days=2)).replace(microsecond=0)
        local=desired.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=2)))
        response=self.post(f'/admin/artigos/{article.id}/editar',**self.fields(article,status='scheduled',scheduled_at=local.isoformat()))
        self.assertEqual(response.status_code,302)
        db.session.refresh(article)
        self.assertEqual(article.scheduled_at,desired)

    def test_past_schedule_is_rejected_before_upload(self):
        article=self.article(self.member());flow=db.session.get(ArticleWorkflow,article.id)
        article.status=flow.stage='approved';flow.approved_at=utcnow();db.session.commit()
        with patch('admin.upload_article_video') as upload:
            response=self.post(f'/admin/artigos/{article.id}/editar',**self.fields(article,status='scheduled',scheduled_at='2000-01-01T12:00'))
            self.assertEqual(response.status_code,200)
            upload.assert_not_called()
        self.assertEqual(article.status,'approved')

    def test_direct_update_does_not_apply_previous_review_to_changed_content(self):
        owner=self.member();reviewer=self.member('portal_reviewer');article=self.article(owner)
        flow=db.session.get(ArticleWorkflow,article.id)
        flow.reviewer=reviewer;flow.reviewed_at=flow.approved_at=utcnow();flow.stage=article.status='published'
        report=PortalReview(article_id=article.id,reviewer_id=reviewer.id,action='reviewed',report='Parecer da versão anterior.')
        db.session.add(report);db.session.commit()
        self.assertEqual(self.post(f'/admin/artigos/{article.id}/editar',**self.fields(article,status='published',body=article.body+' Conteúdo novo.')).status_code,302)
        self.assertIsNone(flow.reviewed_at)
        self.assertEqual(db.session.get(PortalReview,report.id).report,'Parecer da versão anterior.')
