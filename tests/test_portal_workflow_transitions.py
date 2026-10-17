"""Portal submission delivery, independent review and immutable completed reports."""
from datetime import datetime
import unittest
from models import db, utcnow
from governance_models import ArticleWorkflow, PortalReview, GovernanceAudit
import test_lifecycle_notifications as fixtures


class PortalWorkflowTransitions(unittest.TestCase):
    def setUp(self):
        fixtures.LifecycleNotificationTests.setUp(self)
        from extensions import limiter
        previous=limiter.enabled
        limiter.enabled=False
        self.addCleanup(setattr,limiter,'enabled',previous)

    tearDown=fixtures.LifecycleNotificationTests.tearDown
    member=fixtures.LifecycleNotificationTests.member
    article=fixtures.LifecycleNotificationTests.article
    signin=fixtures.LifecycleNotificationTests.signin
    post=fixtures.LifecycleNotificationTests.post
    notices=fixtures.LifecycleNotificationTests.notices

    def setup_article(self):
        owner=self.member()
        editor=self.member('portal_editor')
        reviewer=self.member('portal_reviewer')
        article=self.article(owner)
        flow=db.session.get(ArticleWorkflow,article.id)
        return owner,editor,reviewer,article,flow,f'/admin/fluxo-artigos/{article.id}'

    def edit(self,article,status):
        return self.post(f'/admin/artigos/{article.id}/editar',title=article.title,summary=article.summary,
                         body=article.body,status=status,author_id=article.author_id,category_id=article.category_id)

    def relink_author(self,owner,reviewer):
        author=owner.author
        owner.author=None
        db.session.flush()
        reviewer.author=author
        db.session.commit()

    def test_submit_notifies_editors_who_can_open_and_assign(self):
        owner,editor,reviewer,article,flow,path=self.setup_article()
        self.signin(owner.admin)
        self.assertEqual(self.post(path,action='submit').status_code,302)
        alerts=self.notices(editor,'article',article.id)
        self.assertEqual(len(alerts),1)
        self.signin(editor.admin)
        opened=self.client.get(f'/admin/notificacoes/{alerts[0].id}/abrir')
        self.assertEqual(opened.status_code,302)
        self.assertTrue(opened.location.endswith(path))
        self.assertEqual(self.post(path,action='assign',reviewer_id=reviewer.id).status_code,302)
        self.assertEqual(len(self.notices(reviewer,'article',article.id)),1)
        self.signin(reviewer.admin)
        self.assertIn(article.title.encode(),self.client.get('/admin/trabalho').data)

    def test_form_resubmission_notifies_editor_and_clears_previous_approver(self):
        owner,editor,reviewer,article,flow,path=self.setup_article()
        flow.stage=article.status='changes'
        flow.editor=editor
        db.session.commit()
        self.signin(owner.admin)
        self.assertEqual(self.edit(article,'review').status_code,302)
        db.session.refresh(flow)
        self.assertEqual(flow.stage,'submitted')
        self.assertIsNone(flow.editor_id)
        self.assertTrue(self.notices(editor,'article',article.id))

    def test_assignment_replaces_cached_recipient_and_clears_old_approval(self):
        owner,editor,old,article,flow,path=self.setup_article()
        replacement=self.member('portal_reviewer')
        flow.reviewer=old
        flow.editor=editor
        flow.stage=article.status='review'
        flow.reviewed_at=utcnow()
        db.session.commit()
        self.assertEqual(flow.reviewer.id,old.id)  # Load the relationship before replacing it.
        self.signin(editor.admin)
        self.assertEqual(self.post(path,action='assign',reviewer_id=replacement.id).status_code,302)
        db.session.refresh(flow)
        self.assertEqual(flow.reviewer_id,replacement.id)
        self.assertIsNone(flow.editor_id)
        self.assertIsNone(flow.reviewed_at)
        self.assertIsNone(flow.approved_at)
        self.assertEqual(len(self.notices(replacement,'article',article.id)),1)
        self.assertEqual(len(self.notices(old,'article',article.id)),0)
        count=GovernanceAudit.query.filter_by(action='article.assign',entity_id=article.id).count()
        self.assertEqual(self.post(path,action='assign',reviewer_id=replacement.id).status_code,302)
        self.assertEqual(len(self.notices(replacement,'article',article.id)),1)
        self.assertEqual(GovernanceAudit.query.filter_by(action='article.assign',entity_id=article.id).count(),count)
        self.signin(old.admin)
        self.assertEqual(self.client.get(path).status_code,404)

    def test_completed_review_cannot_be_changed_into_corrections(self):
        owner,editor,reviewer,article,flow,path=self.setup_article()
        self.signin(editor.admin)
        self.post(path,action='assign',reviewer_id=reviewer.id)
        self.signin(reviewer.admin)
        report='Parecer completo e independente, com as fontes verificadas.'
        self.assertEqual(self.post(path,action='reviewed',note=report).status_code,302)
        timestamp=flow.reviewed_at
        self.assertNotIn(b'value="changes"',self.client.get(path).data)
        self.assertEqual(self.post(path,action='changes',note='Pedido posterior ao parecer concluído.').status_code,409)
        db.session.refresh(flow)
        self.assertEqual(flow.stage,'review')
        self.assertEqual(flow.reviewed_at,timestamp)
        self.assertEqual(PortalReview.query.filter_by(article_id=article.id).count(),1)
        self.assertEqual(self.post(path,action='reviewed',note=report).status_code,302)
        self.assertEqual(PortalReview.query.filter_by(article_id=article.id).count(),1)

    def test_author_relink_cannot_enable_self_assignment_or_self_review(self):
        owner,editor,reviewer,article,flow,path=self.setup_article()
        self.signin(editor.admin)
        self.post(path,action='assign',reviewer_id=reviewer.id)
        self.relink_author(owner,reviewer)
        self.signin(editor.admin)
        self.assertNotIn(f'value="{reviewer.id}"'.encode(),self.client.get(path).data)
        self.assertEqual(self.post(path,action='assign',reviewer_id=reviewer.id).status_code,400)
        self.signin(reviewer.admin)
        self.assertNotIn(b'value="reviewed"',self.client.get(path).data)
        self.assertEqual(self.post(path,action='reviewed',note='Tentativa de rever o próprio texto.').status_code,403)
        self.assertIsNone(flow.reviewed_at)
        self.signin(self.primary)
        self.assertEqual(self.post(f'/admin/equipa/{owner.id}/responsabilidades',kind='portal_reviewer',resource_id=article.id,target_id=reviewer.id).status_code,400)

    def test_author_relink_after_review_requires_new_independent_review(self):
        owner,editor,reviewer,article,flow,path=self.setup_article()
        self.signin(editor.admin)
        self.post(path,action='assign',reviewer_id=reviewer.id)
        self.signin(reviewer.admin)
        self.post(path,action='reviewed',note='Parecer independente concluído antes da alteração de autoria.')
        self.relink_author(owner,reviewer)
        self.signin(editor.admin)
        self.assertNotIn(b'value="approve"',self.client.get(path).data)
        self.assertEqual(self.post(path,action='approve').status_code,409)
        self.assertIsNone(flow.approved_at)
        self.assertEqual(PortalReview.query.filter_by(article_id=article.id).count(),1)

    def test_schedule_displays_scheduled_time_instead_of_old_publication_time(self):
        owner,editor,reviewer,article,flow,path=self.setup_article()
        article.status=flow.stage='scheduled'
        article.scheduled_at=datetime(2030,3,14,9,30)
        article.published_at=datetime(2020,1,1,12,0)
        flow.approved_at=utcnow()
        db.session.commit()
        self.signin(editor.admin)
        body=self.client.get(path).data
        self.assertIn(b'14/03/2030 09:30',body)
        self.assertNotIn(b'01/01/2020 12:00',body)

    def test_corrections_resubmission_and_new_review_preserve_all_reports(self):
        owner,editor,reviewer,article,flow,path=self.setup_article()
        self.signin(editor.admin)
        self.assertEqual(self.post(path,action='assign',reviewer_id=reviewer.id).status_code,302)
        self.signin(reviewer.admin)
        self.assertEqual(self.post(path,action='changes',note='Corrigir as referências antes de aprovar o texto.').status_code,302)
        self.assertEqual(flow.stage,'changes')
        self.signin(owner.admin)
        article.body+=' Fontes e referências corrigidas.'
        self.assertEqual(self.edit(article,'review').status_code,302)
        self.assertEqual(flow.stage,'submitted')
        self.signin(editor.admin)
        self.assertEqual(self.post(path,action='assign',reviewer_id=reviewer.id).status_code,302)
        self.signin(reviewer.admin)
        self.assertIn(b'value="reviewed"',self.client.get(path).data)
        self.assertEqual(self.post(path,action='reviewed',note='Referências corrigidas e verificadas na nova revisão.').status_code,302)
        self.signin(editor.admin)
        self.assertEqual(self.post(path,action='approve').status_code,302)
        self.assertEqual(flow.stage,'approved')
        reports=PortalReview.query.filter_by(article_id=article.id).order_by(PortalReview.id).all()
        self.assertEqual([r.action for r in reports],['changes','reviewed'])

    def test_no_reviewer_guidance_respects_team_management_permission(self):
        owner=self.member()
        editor=self.member('portal_editor')
        article=self.article(owner)
        path=f'/admin/fluxo-artigos/{article.id}'
        # Other tests may have valid reviewers: make this case independent of them.
        from unittest.mock import patch
        with patch('governance.eligible',return_value=[]):
            self.signin(editor.admin)
            body=self.client.get(path).data
            self.assertNotIn(b'Gerir colaboradores e mandatos',body)
            self.assertIn('Peça ao responsável pela equipa'.encode(),body)
            self.signin(self.primary)
            self.assertIn(b'Gerir colaboradores e mandatos',self.client.get(path).data)
