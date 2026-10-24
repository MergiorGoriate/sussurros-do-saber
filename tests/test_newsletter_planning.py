"""Saved selection, authorisation, local scheduling and recurring outbox safety."""
from contextlib import contextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import importlib.util
import secrets
from pathlib import Path

from werkzeug.datastructures import MultiDict
from app import app
from models import Article, Author, Subscriber, db, utcnow
from submission_models import NewsletterPlan, NewsletterCampaign, EditorialNotification
from newsletter_planning import (plan, save_plan, edition_for, prepare_plan, run_due_plan,
                                  selected_articles, next_run, schedule_time)
from mail_delivery import policy, due_messages
import test_newsletter as existing

NOW = existing.NOW


class NewsletterPlanningTests(unittest.TestCase):
    def setUp(self):
        existing.NewsletterTests.setUp(self)
        NewsletterPlan.query.delete()
        policy().last_started_at=None
        db.session.commit()

    def tearDown(self):
        NewsletterPlan.query.delete()
        db.session.commit()
        existing.NewsletterTests.tearDown(self)

    @contextmanager
    def recipients(self):
        scoped = SimpleNamespace(query=Subscriber.query.filter(Subscriber.id.in_(
            [self.subscriber.id,self.inactive.id])),email=Subscriber.email,id=Subscriber.id)
        with patch('newsletter_service.Subscriber', scoped):
            yield

    def save(self, **overrides):
        values = dict(selection_mode='manual', article_ids=str(self.article.id), max_articles='5',
                      weekday='0', send_time='09:00')
        values.update(overrides)
        return save_plan(MultiDict(values), now=NOW-timedelta(days=1))

    def mails(self):
        return EditorialNotification.query.filter_by(recipient=self.subscriber.email)

    def test_defaults_are_disabled_and_saving_never_sends(self):
        self.assertFalse(plan().automatic_enabled)
        self.save()
        self.assertEqual(plan().article_ids, [self.article.id])
        self.assertEqual(self.mails().count(), 0)
        self.assertIsNone(plan().next_run_at)

    def test_manual_selection_includes_old_articles_in_saved_order(self):
        self.article.published_at=NOW-timedelta(days=80)
        self.private.status='published'
        db.session.commit()
        ids=[self.private.id,self.article.id]
        edition=existing.digest(now=NOW,article_ids=ids)
        self.assertEqual([x.id for x in edition['articles']],ids)
        self.assertEqual(edition['period'],'Selecção editorial')
        with self.recipients():
            self.assertEqual(existing.queue_digest(now=NOW,article_ids=ids),1)
        row=self.mails().one()
        self.assertLess(row.body.index(self.private.title),row.body.index(self.article.title))
        self.assertIsNone(row.sent_at)

    def test_private_missing_future_and_repeated_articles_are_rejected(self):
        for ids in ([self.private.id],[2147483647],[self.article.id,self.article.id]):
            with self.assertRaises(ValueError): selected_articles(ids,NOW)
        self.article.published_at=NOW+timedelta(days=1)
        db.session.commit()
        with self.assertRaises(ValueError):selected_articles([self.article.id],NOW)

    def test_confirmation_is_required_for_recurring_authorisation(self):
        with self.assertRaises(ValueError): self.save(automatic_enabled='on')
        db.session.rollback()
        self.assertFalse(plan().automatic_enabled)
        settings=self.save(automatic_enabled='on',confirm_automation='on')
        self.assertEqual(settings.next_run_at,datetime(2026,10,19,7))
        self.assertEqual(self.mails().count(),0)

    def test_local_scheduling_and_future_validation(self):
        self.assertEqual(schedule_time('2026-10-20T09:30',NOW),datetime(2026,10,20,7,30))
        self.assertEqual(next_run(0,'09:00',datetime(2026,10,19,7)),datetime(2026,10,26,7))
        for value in ('invalid','2026-10-18T09:00','2026-10-20T09:30+02:00'):
            with self.assertRaises(ValueError):schedule_time(value,NOW)

    def test_preparation_keeps_review_and_authorisation_separate(self):
        settings=self.save()
        edition=edition_for(settings,NOW)
        with self.recipients():
            self.assertEqual(prepare_plan(edition['fingerprint'],now=NOW),1)
        campaign=db.session.get(NewsletterCampaign,self.mails().one().campaign_id)
        self.assertEqual(campaign.status,'prepared')
        self.assertIsNone(campaign.approved_at)
        self.assertFalse(due_messages(NOW).filter_by(recipient=self.subscriber.email).count())

    def test_schedule_freezes_content_and_waits_for_due_time(self):
        settings=self.save()
        edition=edition_for(settings,NOW)
        with self.recipients():
            prepare_plan(edition['fingerprint'],'schedule','2026-10-20T09:30',NOW)
        row=self.mails().one()
        campaign=db.session.get(NewsletterCampaign,row.campaign_id)
        self.assertEqual(campaign.scheduled_at,datetime(2026,10,20,7,30))
        self.assertEqual(campaign.status,'scheduled')
        self.assertIsNotNone(campaign.approved_at)
        body=row.body
        self.article.title='Título alterado depois da aprovação'
        db.session.commit()
        self.assertEqual(db.session.get(EditorialNotification,row.id).body,body)
        self.assertEqual(due_messages(NOW).filter_by(id=row.id).count(),0)
        self.assertEqual(due_messages(datetime(2026,10,20,7,30)).filter_by(id=row.id).count(),1)

    def test_stale_preview_cannot_authorise_changed_content(self):
        settings=self.save()
        fingerprint=edition_for(settings,NOW)['fingerprint']
        self.article.title='Artigo actualizado antes da confirmação'
        db.session.commit()
        with self.recipients(),self.assertRaises(ValueError):
            prepare_plan(fingerprint,'now',now=NOW)
        db.session.rollback()
        self.assertEqual(self.mails().count(),0)

    def test_immediate_authorisation_uses_the_queue_without_smtp_in_request(self):
        settings=self.save()
        with self.recipients(),patch('mail_delivery.smtplib.SMTP') as smtp:
            prepare_plan(edition_for(settings,NOW)['fingerprint'],'now',now=NOW)
        smtp.assert_not_called()
        campaign=db.session.get(NewsletterCampaign,self.mails().one().campaign_id)
        self.assertEqual(campaign.scheduled_at,NOW)
        self.assertEqual(campaign.status,'scheduled')

    def test_recurring_job_is_due_only_once_and_skips_inactive_recipients(self):
        self.save(automatic_enabled='on',confirm_automation='on')
        with self.recipients():
            self.assertEqual(run_due_plan(datetime(2026,10,19,6,59)),0)
            self.assertEqual(run_due_plan(NOW),1)
            self.assertEqual(run_due_plan(NOW),0)
        self.assertEqual(self.mails().count(),1)
        self.assertEqual(EditorialNotification.query.filter_by(recipient=self.inactive.email).count(),0)
        self.assertEqual(plan().next_run_at,datetime(2026,10,26,7))
        self.assertEqual(db.session.get(NewsletterCampaign,self.mails().one().campaign_id).status,'scheduled')

    def test_global_pause_and_disabled_smtp_do_not_consume_the_slot(self):
        settings=self.save(automatic_enabled='on',confirm_automation='on')
        expected=settings.next_run_at
        policy().paused=True;db.session.commit()
        with self.recipients():self.assertEqual(run_due_plan(NOW),0)
        self.assertEqual(plan().next_run_at,expected)
        policy().paused=False;db.session.commit()
        with self.recipients(),patch.dict('os.environ',{'NEWSLETTER_ENABLED':'false'}):
            self.assertEqual(run_due_plan(NOW),0)
        self.assertEqual(plan().next_run_at,expected)

    def test_unpublished_selection_suspends_automation_without_sending(self):
        self.save(automatic_enabled='on',confirm_automation='on')
        self.article.status='draft';db.session.commit()
        with self.recipients():self.assertEqual(run_due_plan(NOW),0)
        self.assertFalse(plan().automatic_enabled)
        self.assertEqual(self.mails().count(),0)

    def test_automatic_selection_limit_and_no_empty_mail(self):
        self.save(selection_mode='automatic',max_articles='1',automatic_enabled='on',confirm_automation='on')
        self.private.status='published';db.session.commit()
        self.assertEqual(len(edition_for(plan(),NOW)['articles']),1)
        self.article.status='draft';self.private.status='draft';db.session.commit()
        with self.recipients():self.assertEqual(run_due_plan(NOW),0)
        self.assertEqual(self.mails().count(),0)
        self.assertGreater(plan().next_run_at,NOW)

    def test_conflicting_prepared_content_suspends_only_the_plan(self):
        settings=self.save(automatic_enabled='on',confirm_automation='on')
        with self.recipients():prepare_plan(edition_for(settings,NOW)['fingerprint'],now=NOW)
        self.article.summary='Novo resumo que exige revisão';db.session.commit()
        with self.recipients():self.assertEqual(run_due_plan(NOW),0)
        self.assertFalse(plan().automatic_enabled)
        self.assertEqual(self.mails().count(),1)
        self.assertEqual(db.session.get(NewsletterCampaign,self.mails().one().campaign_id).status,'prepared')

    def test_existing_worker_prepares_and_delivers_due_plan_once(self):
        self.save(automatic_enabled='on',confirm_automation='on')
        with self.recipients(),patch('newsletter_planning.utcnow',return_value=NOW), \
                patch('mail_delivery.utcnow',return_value=NOW), \
                patch('mail_delivery.due_messages',side_effect=lambda now:due_messages(now).filter_by(recipient=self.subscriber.email)), \
                patch('mail_delivery.smtplib.SMTP') as smtp:
            smtp.return_value.send_message.return_value={}
            first=app.test_cli_runner().invoke(args=['enviar-notificacoes'])
            second=app.test_cli_runner().invoke(args=['enviar-notificacoes'])
        self.assertEqual(first.exit_code,0,first.output)
        self.assertEqual(second.exit_code,0,second.output)
        self.assertEqual(smtp.return_value.send_message.call_count,1)
        self.assertEqual(self.mails().one().status,'accepted')

    def test_disabling_plan_prevents_new_preparations(self):
        self.save(automatic_enabled='on',confirm_automation='on')
        self.save()
        with self.recipients():self.assertEqual(run_due_plan(NOW),0)
        self.assertIsNone(plan().next_run_at)
        self.assertEqual(self.mails().count(),0)

    def test_failed_render_does_not_leave_a_partial_authorised_campaign(self):
        settings=self.save(automatic_enabled='on',confirm_automation='on')
        issue=edition_for(settings,NOW)['issue']
        with self.recipients(),patch('newsletter_service.render_digest_html',side_effect=ValueError('Falha de composição')):
            self.assertEqual(run_due_plan(NOW),0)
        self.assertEqual(self.mails().count(),0)
        self.assertIsNone(NewsletterCampaign.query.filter_by(issue=issue).first())
        self.assertFalse(plan().automatic_enabled)


class NewsletterPlanningPermissionTests(existing.NewsletterPermissionsTests):
    def test_configuration_requires_current_permission_and_csrf(self):
        author=self.member('author');self.signin(author.admin)
        self.assertEqual(self.post('/admin/subscritores',action='save_newsletter_plan').status_code,403)
        self.signin(self.primary)
        self.assertEqual(self.client.post('/admin/subscritores',data={'action':'save_newsletter_plan'}).status_code,400)

    def test_administrator_can_choose_preview_and_schedule_through_the_page(self):
        self.signin(self.primary)
        token=secrets.token_hex(6)
        author=Author(name='Autoria do boletim',slug=token)
        article=Article(title='Artigo escolhido '+token,slug=token,summary='Resumo editorial.',
            body='Texto público.',status='published',published_at=utcnow()-timedelta(days=20),
            author_rel=author,category_rel=self.category)
        recipient=Subscriber(email=token+'@example.test')
        db.session.add_all([article,recipient]);db.session.commit()
        NewsletterPlan.query.delete();db.session.commit()
        previous_campaigns={row.id for row in NewsletterCampaign.query.all()}
        try:
            response=self.post('/admin/subscritores',action='save_newsletter_plan',selection_mode='manual',
                article_ids=str(article.id),max_articles='5',weekday='1',send_time='10:30')
            self.assertEqual(response.status_code,303)
            with patch.dict('os.environ',existing.SMTP):
                response=self.client.get('/admin/subscritores?article_search='+token)
            self.assertEqual(response.status_code,200)
            soup=existing.BeautifulSoup(response.data,'html.parser')
            self.assertIsNotNone(soup.select_one(f'input[name="article_ids"][value="{article.id}"][checked]'))
            fingerprint=soup.select_one('input[name="fingerprint"]')['value']
            future=(utcnow()+timedelta(days=2)).replace(second=0,microsecond=0)
            with patch.dict('os.environ',existing.SMTP),patch('mail_delivery.smtplib.SMTP') as smtp:
                response=self.post('/admin/subscritores',action='prepare_newsletter',confirm='on',
                    fingerprint=fingerprint,delivery_mode='schedule',scheduled_at=future.isoformat(timespec='minutes'))
            self.assertEqual(response.status_code,303)
            smtp.assert_not_called()
            mail=EditorialNotification.query.filter_by(recipient=recipient.email).one()
            campaign=db.session.get(NewsletterCampaign,mail.campaign_id)
            self.assertEqual(campaign.scheduled_at,future-timedelta(hours=2))
            self.assertIn(article.title,mail.body)
        finally:
            db.session.rollback()
            added=[row.id for row in NewsletterCampaign.query.all() if row.id not in previous_campaigns]
            EditorialNotification.query.filter(EditorialNotification.campaign_id.in_(added)).delete(synchronize_session=False)
            NewsletterCampaign.query.filter(NewsletterCampaign.id.in_(added)).delete(synchronize_session=False)
            NewsletterPlan.query.delete()
            db.session.delete(article);db.session.delete(recipient)
            db.session.flush();db.session.delete(author);db.session.commit()


class NewsletterPlanMigrationTests(unittest.TestCase):
    def test_migration_is_additive_and_repeatable(self):
        import sqlalchemy as sa
        path=Path(__file__).resolve().parents[1]/'migrations/versions/20261024_14_newsletter_plan.py'
        spec=importlib.util.spec_from_file_location('newsletter_plan_migration',path)
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        engine=sa.create_engine('sqlite://')
        with engine.begin() as connection:
            connection.execute(sa.text('CREATE TABLE preserved (id INTEGER PRIMARY KEY, body TEXT)'))
            connection.execute(sa.text("INSERT INTO preserved VALUES (1, 'histórico')"))
            with patch.object(migration.op,'get_bind',return_value=connection):
                migration.upgrade();migration.upgrade()
            self.assertIn('newsletter_plan',sa.inspect(connection).get_table_names())
            self.assertEqual(connection.execute(sa.text('SELECT body FROM preserved')).scalar(),'histórico')


if __name__=='__main__':unittest.main()
