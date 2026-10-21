"""Durable outbox behaviour with a simulated SMTP server, on SQLite and PostgreSQL.

Set MAIL_TEST_DATABASE_URL to an isolated PostgreSQL database for real locks/FKs.
Each test creates its own schema there. No SMTP network operation is performed.
"""
import os
from pathlib import Path
import secrets
import smtplib
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from flask import Flask
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError

from models import db, Subscriber
from submission_models import EditorialNotification as Mail, NewsletterCampaign as Campaign, MailDeliveryAttempt as Attempt
import governance_models
from mail_delivery import (policy, deliver_batch, worker_slot, reserve, campaign_action,
                           reconcile, update_policy, retry, dashboard)

NOW=datetime(2026,10,21,10,0)
SMTP={'SMTP_HOST':'smtp.example.test','SMTP_FROM':'boletim@example.test','SMTP_TLS':'true',
      'SMTP_SSL':'false','SMTP_USERNAME':'','NEWSLETTER_ENABLED':'true'}


class FakeSMTP:
    def __init__(self):self.messages=[];self.error=None;self.before=None;self.quit_error=False
    def factory(self,*args,**kwargs):return self
    def starttls(self,**kwargs):
        if self.before:self.before()
    def login(self,*args):pass
    def send_message(self,message):
        self.messages.append(message)
        if self.error:raise self.error
        return {}
    def quit(self):
        if self.quit_error:raise smtplib.SMTPServerDisconnected('quit')
    def close(self):pass


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.schema=None;self.admin_engine=None
        url=os.getenv('MAIL_TEST_DATABASE_URL','sqlite:///'+self.directory.name+'/mail.db')
        self.app=Flask('mail-tests',template_folder=str(Path(__file__).resolve().parents[1]/'templates'))
        self.app.config.update(TESTING=True,SECRET_KEY='isolated-test-secret',SQLALCHEMY_DATABASE_URI=url)
        if url.startswith('postgresql'):
            self.schema='mail_test_'+secrets.token_hex(6);self.admin_engine=create_engine(url)
            with self.admin_engine.begin() as conn:conn.execute(text('CREATE SCHEMA '+self.schema))
            self.app.config['SQLALCHEMY_ENGINE_OPTIONS']={'connect_args':{'options':'-csearch_path='+self.schema}}
        db.init_app(self.app);self.ctx=self.app.app_context();self.ctx.push();db.create_all()
        p=policy();p.interval_seconds=0;db.session.commit()
        self.env=patch.dict(os.environ,SMTP);self.env.start()
        self.clock=patch('mail_delivery.utcnow',return_value=NOW);self.clock.start()
        self.smtp=FakeSMTP()

    def tearDown(self):
        db.session.remove();db.engine.dispose();self.ctx.pop();self.env.stop();self.clock.stop()
        if self.admin_engine:
            with self.admin_engine.begin() as conn:conn.execute(text('DROP SCHEMA '+self.schema+' CASCADE'))
            self.admin_engine.dispose()
        self.directory.cleanup()

    def mail(self,campaign=None,subscriber=None):
        row=Mail(recipient=subscriber.email if subscriber else secrets.token_hex(5)+'@example.test',
            subject=campaign.subject if campaign else 'Confirmação de conta',body='Texto de teste',
            campaign_id=campaign.id if campaign else None,subscriber_id=subscriber.id if subscriber else None)
        db.session.add(row);db.session.commit();return row

    def campaign(self,status='scheduled',issue='2026-W42'):
        c=Campaign(issue=issue,subject='Sussurros do Saber — Boletim '+issue,fingerprint='a'*64,
            status=status,approved_at=NOW if status!='prepared' else None,scheduled_at=NOW if status=='scheduled' else None)
        subscriber=Subscriber(email=secrets.token_hex(6)+'@example.test');db.session.add_all([c,subscriber]);db.session.commit()
        return c,subscriber

    def send(self):return deliver_batch(50,smtp_factory=self.smtp.factory)

    def test_initial_limits_and_unverified_provider(self):
        p=policy();self.assertEqual((p.hourly_limit,p.daily_limit,p.edition_limit,p.max_retries),(100,500,2500,3))
        self.assertIsNone(p.provider_hourly);self.assertIsNone(p.provider_verified_on)

    def test_shared_hour_and_day_windows_keep_excess_pending(self):
        p=policy();p.hourly_limit=1;p.daily_limit=2;db.session.commit()
        rows=[self.mail() for _ in range(3)]
        self.assertEqual(self.send(),1);self.assertEqual(self.send(),0)
        self.assertEqual(rows[1].status,'pending')
        with patch('mail_delivery.utcnow',return_value=NOW+timedelta(hours=1)):
            self.assertEqual(self.send(),1)
        with patch('mail_delivery.utcnow',return_value=NOW+timedelta(hours=2)):
            self.assertEqual(self.send(),0)
        with patch('mail_delivery.utcnow',return_value=NOW+timedelta(days=1)):
            self.assertEqual(self.send(),1)
        self.assertEqual(Attempt.query.count(),3)

    def test_provider_stricter_limit_and_all_campaigns_share_budget(self):
        p=policy();p.provider_hourly=1;db.session.commit()
        c,s=self.campaign();c2,s2=self.campaign(issue='2026-W41')
        self.mail(c,s);self.mail(c2,s2);self.mail()
        self.assertEqual(self.send(),1);self.assertEqual(len(self.smtp.messages),1)
        self.assertEqual(Mail.query.filter_by(status='pending').count(),2)

    def test_prepared_then_approved_is_not_yet_authorized(self):
        c,s=self.campaign('prepared');self.mail(c,s)
        self.assertEqual(self.send(),0)
        with self.assertRaises(ValueError):campaign_action(c.id,'start',{})
        with self.assertRaises(ValueError):campaign_action(c.id,'approve',{})
        campaign_action(c.id,'approve',{'reviewed_campaign':'on','campaign_fingerprint':c.fingerprint})
        self.assertEqual(self.send(),0)
        campaign_action(c.id,'schedule',{'scheduled_at':(NOW+timedelta(hours=1)).isoformat()})
        self.assertEqual(self.send(),0)
        with patch('mail_delivery.utcnow',return_value=NOW+timedelta(hours=1)):
            self.assertEqual(self.send(),1)

    def test_restart_does_not_repeat_committed_acceptance(self):
        row=self.mail();self.assertEqual(self.send(),1);ident=row.id
        db.session.remove()
        self.assertEqual(self.send(),0);self.assertEqual(db.session.get(Mail,ident).status,'accepted')
        self.assertEqual(len(self.smtp.messages),1)

    def test_abandoned_processing_is_uncertain_not_retried(self):
        row=self.mail()
        with worker_slot() as token:self.assertIsNotNone(reserve(token,NOW))
        ident=row.id
        db.session.remove()
        self.assertEqual(self.send(),0)
        row=db.session.get(Mail,ident);self.assertEqual(row.status,'uncertain')
        self.assertEqual(Attempt.query.one().outcome,'uncertain')

    def test_two_instances_cannot_send_the_same_message_or_bypass_quota(self):
        self.mail();self.mail();p=policy();p.hourly_limit=1;db.session.commit()
        entered=threading.Event();release=threading.Event();results=[];errors=[]
        def factory(*a,**k):
            entered.set()
            if not release.wait(10):raise RuntimeError('test barrier timed out')
            return self.smtp
        def first():
            try:
                with self.app.app_context():results.append(deliver_batch(50,smtp_factory=factory))
            except BaseException as e:errors.append(e)
        thread=threading.Thread(target=first);thread.start()
        self.assertTrue(entered.wait(10))
        try:
            with self.app.app_context():results.append(deliver_batch(50,smtp_factory=self.smtp.factory))
        finally:release.set();thread.join(10)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertEqual(sorted(results),[0,1]);self.assertEqual(len(self.smtp.messages),1)
        self.assertEqual(Attempt.query.count(),1)

    def test_cancelled_or_changed_subscriber_is_not_sent(self):
        c,s=self.campaign();row=self.mail(c,s);s.active=False;db.session.commit()
        self.assertEqual(self.send(),0);self.assertEqual(row.status,'cancelled');self.assertEqual(row.attempts,0)

    def test_cancellation_during_connection_is_rechecked(self):
        c,s=self.campaign();row=self.mail(c,s)
        def cancel():s.active=False;db.session.commit()
        self.smtp.before=cancel
        self.assertEqual(self.send(),0);self.assertEqual(row.status,'cancelled');self.assertFalse(self.smtp.messages)

    def test_pause_then_resume_preserves_pending(self):
        row=self.mail();p=policy();p.paused=True;db.session.commit()
        self.assertEqual(self.send(),0);self.assertEqual(row.attempts,0)
        p.paused=False;db.session.commit();self.assertEqual(self.send(),1)

    def test_pause_during_attempt_allows_it_to_finish_but_stops_next(self):
        self.mail();second=self.mail()
        def pause():policy().paused=True;db.session.commit()
        self.smtp.before=pause
        self.assertEqual(self.send(),1);self.assertEqual(second.status,'pending')

    def test_temporary_errors_have_backoff_and_three_additional_attempts(self):
        row=self.mail();self.smtp.error=smtplib.SMTPDataError(451,b'try later')
        for n in range(1,5):
            when=NOW+timedelta(days=n)
            with patch('mail_delivery.utcnow',return_value=when),patch('mail_delivery.random.randint',return_value=0):
                self.assertEqual(self.send(),0)
                self.assertEqual(row.attempts,n)
                if n<4:
                    self.assertEqual(row.next_attempt_at,when+timedelta(seconds=300*2**(n-1)))
                    self.send();self.assertEqual(row.attempts,n)
        self.assertEqual(row.status,'permanent');self.assertEqual(Attempt.query.count(),4)
        self.send();self.assertEqual(len(self.smtp.messages),4)

    def test_permanent_refusal_is_not_retried(self):
        row=self.mail();self.smtp.error=smtplib.SMTPRecipientsRefused({row.recipient:(550,b'5.1.1 invalid')})
        self.send();self.send();self.assertEqual(row.status,'permanent');self.assertEqual(row.smtp_code,550)
        self.assertEqual(row.attempts,1)

    def test_uncertain_network_result_needs_evidence_and_never_blind_retry(self):
        row=self.mail();self.smtp.error=OSError('reset with SECRET-TO-NOT-LOG')
        self.send();self.smtp.error=None;self.send()
        self.assertEqual(row.status,'uncertain');self.assertEqual(row.attempts,1)
        with self.assertRaises(ValueError):retry(row.id)
        with self.assertRaises(ValueError):reconcile(row.id,'confirmed_not_accepted','')
        reconcile(row.id,'confirmed_not_accepted','Ticket do fornecedor numero 123')
        self.assertEqual(self.send(),1);self.assertEqual(row.attempts,2)
        self.assertNotIn('SECRET-TO-NOT-LOG',str([(a.reason) for a in Attempt.query.all()]))

    def test_reconciled_acceptance_never_reenters_pending_queue(self):
        row=self.mail();row.status='uncertain';row.attempts=1;db.session.commit()
        reconcile(row.id,'confirmed_accepted','Relatorio do fornecedor numero 456')
        self.assertEqual(self.send(),0);self.assertIsNotNone(row.sent_at)

    def test_connection_failure_before_send_is_safely_retryable(self):
        row=self.mail()
        def broken(*a,**k):raise OSError('not connected')
        self.assertEqual(deliver_batch(smtp_factory=broken),0)
        self.assertEqual(row.status,'temporary');self.assertEqual(row.attempts,1)

    def test_provider_rate_limit_cools_down_all_mail(self):
        row=self.mail();second=self.mail();self.smtp.error=smtplib.SMTPDataError(452,b'quota')
        self.send();self.assertEqual(row.status,'temporary');self.assertEqual(second.status,'pending')
        self.assertEqual(policy().suspended_until,NOW+timedelta(minutes=15))

    def test_auth_failure_pauses_global_queue_and_does_not_log_secret(self):
        row=self.mail()
        def auth(*a,**k):raise smtplib.SMTPAuthenticationError(535,b'password=DO-NOT-STORE')
        deliver_batch(smtp_factory=auth)
        self.assertTrue(policy().paused);self.assertEqual(row.status,'suspended')
        self.assertNotIn('DO-NOT-STORE',row.last_error)

    def test_acceptance_commit_survives_quit_failure_and_single_recipient_headers(self):
        row=self.mail();self.smtp.quit_error=True;self.assertEqual(self.send(),1)
        self.assertEqual(self.send(),0);message=self.smtp.messages[0]
        self.assertEqual(message['To'],row.recipient);self.assertIsNone(message['Cc']);self.assertIsNone(message['Bcc'])
        self.assertEqual(row.status,'accepted');self.assertEqual(row.smtp_code,250)

    def test_uniqueness_by_campaign_email_and_subscriber(self):
        c,s=self.campaign();self.mail(c,s)
        with self.assertRaises(IntegrityError):self.mail(c,s)
        db.session.rollback()
        duplicate=Mail(recipient='another@example.test',subject=c.subject,body='x',campaign_id=c.id,subscriber_id=s.id)
        db.session.add(duplicate)
        with self.assertRaises(IntegrityError):db.session.commit()
        db.session.rollback()

    def test_settings_validate_manual_provider_evidence(self):
        form=dict(hourly_limit='90',daily_limit='400',edition_limit='2000',max_retries='3',interval_seconds='40',provider_hourly='80')
        with self.assertRaises(ValueError):update_policy(form)
        db.session.rollback();form.update(provider_source='Painel oficial verificado',provider_verified_on='2026-10-20')
        update_policy(form);self.assertEqual(dashboard()['hour_limit'],80)
        form['hourly_limit']='-1'
        with self.assertRaises(ValueError):update_policy(form)

    def test_preparation_only_and_cap_is_per_edition_across_multiple_batches(self):
        from newsletter_service import queue_digest
        p=policy();p.edition_limit=2;db.session.add_all([Subscriber(email=f'cap{i}@example.test') for i in range(4)]);db.session.commit()
        edition=dict(issue='2026-W42',subject='Sussurros do Saber — Boletim 2026-W42',fingerprint='b'*64,
            articles=[object()],cards=[],content='Artigo publicado',period='Semana',start=NOW-timedelta(days=7),end=NOW)
        with patch('newsletter_service.digest',return_value=edition),patch('mail_delivery.smtplib.SMTP') as smtp:
            self.assertEqual(queue_digest(limit=1),1);self.assertEqual(queue_digest(limit=1),1)
            self.assertEqual(queue_digest(limit=1),0);smtp.assert_not_called()
        self.assertEqual(Mail.query.count(),2);self.assertEqual(Campaign.query.one().status,'prepared')
        self.assertEqual(self.send(),0)

    def test_schedule_and_processing_need_no_http_request(self):
        c,s=self.campaign();self.mail(c,s)
        self.assertEqual(self.send(),1)
        self.assertEqual(c.status,'completed')

    def test_interval_is_shared_and_failed_attempts_consume_capacity(self):
        p=policy();p.interval_seconds=36;p.hourly_limit=1;db.session.commit()
        row=self.mail();second=self.mail();self.smtp.error=smtplib.SMTPDataError(451,b'retry')
        self.send();self.assertEqual(Attempt.query.count(),1);self.assertEqual(second.attempts,0)
        self.assertEqual(dashboard()['hour_count'],1)

    def test_more_than_two_thousand_subscribers_respect_edition_cap(self):
        from newsletter_service import queue_digest
        db.session.add_all([Subscriber(email=f'large{i}@example.test') for i in range(2501)]);db.session.commit()
        edition=dict(issue='2026-W42',subject='Sussurros do Saber — Boletim 2026-W42',fingerprint='c'*64,
            articles=[object()],cards=[],content='Conteúdo semanal',period='Semana',start=NOW-timedelta(days=7),end=NOW)
        with patch('newsletter_service.digest',return_value=edition):
            self.assertEqual(queue_digest(),2500);self.assertEqual(queue_digest(),0)
            c=Campaign.query.one();c.status='scheduled';c.approved_at=NOW;c.scheduled_at=NOW;db.session.commit()
            self.assertEqual(queue_digest(),0)
        p=policy();p.hourly_limit=100000;p.daily_limit=500;db.session.commit()
        with patch('mail_delivery.ssl.create_default_context'):
            self.assertEqual(deliver_batch(1000,smtp_factory=self.smtp.factory),500)
        self.assertEqual(Mail.query.filter_by(status='pending').count(),2000)
        self.assertEqual(Attempt.query.count(),500)

    def test_cancelled_messages_do_not_revive_on_resubscription(self):
        from mail_delivery import cancel_subscriber
        c,s=self.campaign();row=self.mail(c,s)
        s.active=False;cancel_subscriber(s.id);db.session.commit()
        s.active=True;db.session.commit();self.assertEqual(self.send(),0)
        self.assertEqual(row.status,'cancelled')

    def test_lowering_edition_capacity_pauses_prepared_work_without_sending(self):
        c,s=self.campaign();self.mail(c,s)
        other=Subscriber(email='another-cap@example.test');db.session.add(other);db.session.commit();self.mail(c,other)
        form=dict(hourly_limit='100',daily_limit='500',edition_limit='1',max_retries='3',interval_seconds='0')
        update_policy(form)
        self.assertEqual(c.status,'paused');self.assertTrue(c.suspension_reason)
        with self.assertRaises(ValueError):campaign_action(c.id,'start',{})
        self.assertEqual(self.send(),0)

    def test_unapproved_campaign_cannot_block_later_transactional_messages(self):
        c,s=self.campaign('prepared')
        db.session.add_all([Mail(recipient=f'not-due{i}@example.test',subject=c.subject,body='x',campaign_id=c.id) for i in range(150)])
        db.session.commit();row=self.mail()
        self.assertEqual(self.send(),1);self.assertEqual(row.status,'accepted')
        self.assertEqual(Mail.query.filter_by(campaign_id=c.id,status='pending').count(),150)

    def test_failure_to_store_smtp_result_does_not_cause_automatic_replay(self):
        row=self.mail()
        with patch('mail_delivery.finish',side_effect=RuntimeError('crash after DATA')):
            with self.assertRaises(RuntimeError):self.send()
        self.assertEqual(len(self.smtp.messages),1)
        self.assertEqual(self.send(),0);self.assertEqual(row.status,'uncertain')
        self.assertEqual(len(self.smtp.messages),1)

    def test_new_application_instance_uses_same_durable_queue_and_counters(self):
        row=self.mail();ident=row.id;p=policy();p.hourly_limit=1;db.session.commit();self.send()
        self.mail()
        other=Flask('second-process-fixture');other.config.update(self.app.config)
        db.init_app(other)
        with other.app_context():
            self.assertEqual(deliver_batch(smtp_factory=self.smtp.factory),0)
            self.assertEqual(db.session.get(Mail,ident).status,'accepted')
            self.assertEqual(dashboard()['hour_count'],1)
            db.session.remove();db.engine.dispose()


if __name__=='__main__':unittest.main()
