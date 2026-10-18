"""Regressions reproduced during the portal audit; synthetic fixture data only."""
import unittest
from datetime import timedelta
import test_staff_governance as fixtures
from app import app
from models import db, Article, utcnow
from governance_models import ArticleWorkflow, PortalReview, StaffNotice, GovernanceAudit

class FunctionalityAuditTests(unittest.TestCase):
    setUp=fixtures.StaffGovernanceTests.setUp
    tearDown=fixtures.StaffGovernanceTests.tearDown
    member=fixtures.StaffGovernanceTests.member
    signin=fixtures.StaffGovernanceTests.signin
    post=fixtures.StaffGovernanceTests.post
    article=fixtures.StaffGovernanceTests.article

    def test_reassigning_reviewer_invalidates_old_review_approval_and_schedule(self):
        owner=self.member();old=self.member('portal_reviewer');new=self.member('portal_reviewer')
        editor=self.member('portal_editor');publisher=self.member('publisher')
        for stage in ['review','approved','scheduled']:
            with self.subTest(stage=stage):
                article=self.article(owner);flow=db.session.get(ArticleWorkflow,article.id)
                flow.reviewer_id=old.id;flow.editor_id=editor.id;flow.reviewed_at=utcnow();flow.approved_at=utcnow();flow.stage=stage
                article.status=stage;article.scheduled_at=utcnow()+timedelta(days=1)
                report=PortalReview(article_id=article.id,reviewer_id=old.id,action='reviewed',report='Parecer original preservado')
                db.session.add(report);db.session.commit();self.signin(self.primary)
                response=self.post(f'/admin/equipa/{old.id}/responsabilidades',kind='portal_reviewer',resource_id=article.id,target_id=new.id)
                if stage == 'approved':
                    # Valid existing approvals now publish before the request.
                    # Published decisions require an explicit reopening first.
                    self.assertEqual(response.status_code,404)
                    self.assertEqual(article.status,'published')
                    self.assertEqual(self.post(f'/admin/fluxo-artigos/{article.id}',action='reopen').status_code,302)
                    response=self.post(f'/admin/equipa/{old.id}/responsabilidades',kind='portal_reviewer',resource_id=article.id,target_id=new.id)
                self.assertEqual(response.status_code,303)
                db.session.refresh(flow);db.session.refresh(article)
                self.assertEqual(flow.reviewer_id,new.id);self.assertEqual(flow.stage,'review');self.assertEqual(article.status,'review')
                self.assertIsNone(flow.reviewed_at);self.assertIsNone(flow.approved_at);self.assertIsNone(article.scheduled_at)
                self.assertEqual(db.session.get(PortalReview,report.id).report,'Parecer original preservado')
                self.signin(editor.admin);self.assertEqual(self.post(f'/admin/fluxo-artigos/{article.id}',action='approve').status_code,409)
                self.signin(publisher.admin);self.assertEqual(self.post(f'/admin/fluxo-artigos/{article.id}',action='publish').status_code,409)
                self.signin(new.admin);self.assertEqual(self.client.get(f'/admin/fluxo-artigos/{article.id}').status_code,200)
                self.assertEqual(self.post(f'/admin/fluxo-artigos/{article.id}',action='reviewed',note='Nova revisão independente completa.').status_code,302)
                self.signin(editor.admin);self.assertEqual(self.post(f'/admin/fluxo-artigos/{article.id}',action='approve').status_code,302)
                self.signin(publisher.admin);self.assertEqual(self.post(f'/admin/fluxo-artigos/{article.id}',action='publish').status_code,302)

    def test_repeated_review_is_idempotent_and_changed_report_requires_reopening(self):
        owner=self.member();reviewer=self.member('portal_reviewer');article=self.article(owner)
        flow=db.session.get(ArticleWorkflow,article.id);flow.reviewer_id=reviewer.id;flow.stage='review';article.status='review';db.session.commit()
        self.signin(reviewer.admin);path=f'/admin/fluxo-artigos/{article.id}'
        self.assertEqual(self.post(path,action='reviewed',note='Revisão científica concluída.').status_code,302)
        count=StaffNotice.query.filter_by(resource_type='article',resource_id=article.id).count()
        stamp=flow.reviewed_at
        self.assertEqual(self.post(path,action='reviewed',note='Revisão científica concluída.').status_code,302)
        self.assertEqual(PortalReview.query.filter_by(article_id=article.id).count(),1)
        self.assertEqual(StaffNotice.query.filter_by(resource_type='article',resource_id=article.id).count(),count)
        self.assertEqual(flow.reviewed_at,stamp)
        self.assertEqual(self.post(path,action='reviewed',note='Outro parecer após a conclusão.').status_code,409)

    def test_scheduled_publication_records_event_and_notifies_once(self):
        owner=self.member();reviewer=self.member('portal_reviewer');article=self.article(owner)
        flow=db.session.get(ArticleWorkflow,article.id);flow.reviewer_id=reviewer.id;flow.reviewed_at=flow.approved_at=utcnow();flow.stage='scheduled'
        article.status='scheduled';article.scheduled_at=utcnow()-timedelta(minutes=1);db.session.commit()
        with app.test_request_context('/'):
            self.assertGreaterEqual(Article.publish_due_scheduled(),1)
            self.assertEqual(Article.publish_due_scheduled(),0)
        db.session.refresh(article);db.session.refresh(flow)
        self.assertEqual(article.status,'published');self.assertEqual(flow.stage,'published')
        self.assertEqual(GovernanceAudit.query.filter_by(action='article.publish',entity_id=article.id).count(),1)
        for member in [owner,reviewer]:
            notices=StaffNotice.query.filter_by(admin_id=member.admin_id,resource_type='article',resource_id=article.id).all()
            self.assertEqual(len(notices),1);self.assertIn('Artigo publicado',notices[0].body)

    def test_scheduler_does_not_publish_managed_article_without_approval(self):
        owner=self.member();article=self.article(owner);flow=db.session.get(ArticleWorkflow,article.id)
        flow.stage='scheduled';article.status='scheduled';article.scheduled_at=utcnow()-timedelta(days=1);db.session.commit()
        with app.test_request_context('/'):Article.publish_due_scheduled()
        db.session.refresh(article);self.assertEqual(article.status,'scheduled')
        self.assertEqual(GovernanceAudit.query.filter_by(action='article.publish',entity_id=article.id).count(),0)

    def test_bell_announces_unread_count_to_assistive_technology(self):
        owner=self.member();db.session.add(StaffNotice(admin_id=owner.admin_id,subject='Aviso isolado'));db.session.commit();self.signin(owner.admin)
        response=self.client.get('/admin/trabalho')
        self.assertEqual(response.status_code,200)
        self.assertIn('aria-label="Notificações internas · 1 por ler"'.encode(),response.data)

    def test_unlinked_managed_account_cannot_open_global_dashboard(self):
        member=self.member('coordination');self.signin(member.admin);member.admin_id=None;db.session.commit()
        response=self.client.get('/admin')
        self.assertEqual(response.status_code,302);self.assertTrue(response.location.endswith('/admin/trabalho'))
        self.assertEqual(self.client.get('/admin/trabalho').status_code,200)
        self.assertEqual(self.client.get('/admin/artigos').status_code,403)
        self.signin(self.primary);self.assertEqual(self.client.get('/admin').status_code,200)

    def test_deleting_article_cleans_saved_preferences_without_touching_other_articles(self):
        from reader_accounts import ReaderArticle
        from submission_models import Researcher
        import secrets
        owner=self.member();article=self.article(owner);other=self.article(owner)
        reader=Researcher(name='Leitor isolado',email=secrets.token_hex(8)+'@example.org',verified=True,token_nonce='test',password_hash='unused')
        db.session.add(reader);db.session.flush()
        db.session.add_all([ReaderArticle(owner_id=reader.id,article_id=article.id),ReaderArticle(owner_id=reader.id,article_id=other.id)])
        db.session.commit();self.signin(self.primary)
        self.assertEqual(self.post(f'/admin/artigos/{article.id}/eliminar').status_code,302)
        self.assertEqual(ReaderArticle.query.filter_by(article_id=article.id).count(),0)
        self.assertEqual(ReaderArticle.query.filter_by(article_id=other.id).count(),1)
        self.assertIsNotNone(db.session.get(Article,other.id))

    def test_deleting_journal_cleans_preferences_but_preserves_mandate_history(self):
        from reader_accounts import ReaderJournal
        from submission_models import Researcher
        import secrets
        reader=Researcher(name='Leitor isolado',email=secrets.token_hex(8)+'@example.org',verified=True,token_nonce='test',password_hash='unused')
        db.session.add(reader);db.session.flush()
        db.session.add_all([ReaderJournal(owner_id=reader.id,journal_id=self.journal.id,saved=True),ReaderJournal(owner_id=reader.id,journal_id=self.other_journal.id,following=True)])
        db.session.commit();self.signin(self.primary)
        self.assertEqual(self.post(f'/admin/revistas/{self.journal.id}/eliminar').status_code,302)
        self.assertEqual(ReaderJournal.query.filter_by(journal_id=self.journal.id).count(),0)
        self.assertEqual(ReaderJournal.query.filter_by(journal_id=self.other_journal.id).count(),1)
        member=self.member('reviewer',self.other_journal.id);member.appointments[0].active=False;db.session.commit()
        self.assertEqual(self.post(f'/admin/revistas/{self.other_journal.id}/eliminar').status_code,409)
        self.assertEqual(member.appointments[0].journal_id,self.other_journal.id)

