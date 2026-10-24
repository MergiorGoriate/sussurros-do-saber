"""Digest queue, cancellation, delivery, and current management permissions."""
import secrets
import smtplib
import ssl
import unittest
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from app import app
from models import db, Article, Author, Category, Subscriber
from newsletter_service import CANCELLED, digest, queue_digest, unsubscribe_token, newsletter_image_url, unsubscribe_url
from submission_models import EditorialNotification, NewsletterCampaign, MailDeliveryAttempt
from mail_delivery import policy, due_messages
import test_staff_governance as staff

SMTP = {'SMTP_HOST':'smtp.example.test', 'SMTP_FROM':'boletim@example.test',
        'SMTP_TLS':'true', 'SMTP_SSL':'false', 'SMTP_USERNAME':'', 'NEWSLETTER_ENABLED':'true'}
NOW = datetime(2026, 10, 19, 9)


class NewsletterTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, RATELIMIT_ENABLED=False)
        self.context=app.app_context();self.context.push()
        self.environment=patch.dict('os.environ', SMTP);self.environment.start()
        token=secrets.token_hex(8)
        self.author=Author(name='Autor '+token,slug=token)
        self.category=Category(name='Tema '+token,slug=token)
        self.subscriber=Subscriber(email=token+'@example.test')
        self.inactive=Subscriber(email='inactive-'+token+'@example.test',active=False)
        self.article=Article(title='Ciência publicada '+token,slug=token,
            summary='Resumo com fontes verificadas.',body='Conteúdo de divulgação.',
            author_rel=self.author,category_rel=self.category,status='published',
            published_at=NOW-timedelta(days=4))
        self.private=Article(title='Manuscrito privado '+token,slug='private-'+token,
            summary='Resumo privado.',body='Conteúdo reservado.',
            author_rel=self.author,category_rel=self.category,status='draft',
            published_at=self.article.published_at)
        db.session.add_all([self.article,self.private,self.subscriber,self.inactive]);db.session.commit()
        scoped_articles=SimpleNamespace(
            public_card_query=lambda:Article.public_card_query().filter(Article.id.in_([self.article.id,self.private.id])),
            published_at=Article.published_at,id=Article.id)
        self.article_scope=patch('newsletter_service.Article',scoped_articles)
        self.article_scope.start()
        self.client=app.test_client()
        settings=policy();settings.interval_seconds=0;settings.hourly_limit=100000;settings.daily_limit=1000000;settings.paused=False;settings.suspended_until=None;db.session.commit()

    def tearDown(self):
        self.article_scope.stop()
        db.session.rollback()
        campaign_ids=[r.campaign_id for r in EditorialNotification.query.filter_by(recipient=self.subscriber.email).all() if r.campaign_id]
        ids=[r.id for r in EditorialNotification.query.filter(EditorialNotification.recipient.in_([self.subscriber.email,self.inactive.email])).all()]
        MailDeliveryAttempt.query.filter(MailDeliveryAttempt.notification_id.in_(ids)).delete(synchronize_session=False)
        EditorialNotification.query.filter(EditorialNotification.id.in_(ids)).delete(synchronize_session=False)
        NewsletterCampaign.query.filter(NewsletterCampaign.id.in_(campaign_ids)).delete(synchronize_session=False)
        for row in [self.article,self.private,self.subscriber,self.inactive]:db.session.delete(row)
        db.session.flush()
        db.session.delete(self.author);db.session.delete(self.category);db.session.commit()
        db.session.remove();self.context.pop();self.environment.stop()

    def queue(self, **kwargs):
        # Scope recipients to this test while retaining real SQL and persistence.
        scoped=SimpleNamespace(query=Subscriber.query.filter(Subscriber.id.in_(
            [self.subscriber.id,self.inactive.id])),email=Subscriber.email,id=Subscriber.id)
        with patch('newsletter_service.Subscriber',scoped):
            return queue_digest(now=NOW,**kwargs)

    def deliver(self, failure=False, send_results=None, quit_failure=False):
        for row in EditorialNotification.query.filter_by(recipient=self.subscriber.email).all():
            if row.campaign_id:
                c=db.session.get(NewsletterCampaign,row.campaign_id)
                c.status='scheduled';c.approved_at=NOW;c.scheduled_at=NOW
            if row.status=='temporary':row.next_attempt_at=None
        db.session.commit()
        query=due_messages
        with patch('mail_delivery.due_messages',side_effect=lambda now:query(now).filter_by(recipient=self.subscriber.email)), patch('mail_delivery.smtplib.SMTP') as smtp:
            smtp.return_value.send_message.return_value={}
            if quit_failure:smtp.return_value.quit.side_effect=smtplib.SMTPServerDisconnected('disconnect at QUIT')
            if send_results is not None:smtp.return_value.send_message.side_effect=send_results
            if failure:smtp.return_value.send_message.side_effect=smtplib.SMTPDataError(451,b'test refusal')
            result=app.test_cli_runner().invoke(args=['enviar-notificacoes'])
            self.assertEqual(result.exit_code,0,result.output)
            return smtp.return_value

    def test_queue_is_private_active_only_and_idempotent(self):
        self.assertEqual(self.queue(),1)
        self.assertEqual(self.queue(),0)
        row=EditorialNotification.query.filter_by(recipient=self.subscriber.email).one()
        self.assertIn(self.article.title,row.body)
        self.assertNotIn(self.private.title,row.body)
        self.assertIn('/boletim/cancelar/',row.body)
        self.assertIsNone(row.sent_at)
        self.assertEqual(EditorialNotification.query.filter_by(recipient=self.inactive.email).count(),0)

    def test_html_snapshot_contains_covers_and_is_sent_as_multipart_alternative(self):
        self.article.image='https://res.cloudinary.com/demo/image/upload/v1/cover.png'
        self.article.title='Ciência <em>com rigor</em>'
        self.article.summary='Resumo <script>não executar</script> & fontes.'
        db.session.commit()
        self.assertEqual(self.queue(),1)
        row=EditorialNotification.query.filter_by(recipient=self.subscriber.email).one()
        soup=BeautifulSoup(row.html_body,'html.parser')
        image=soup.find('img')
        self.assertIn('/upload/f_jpg,',image['src'])
        self.assertIn('w_640',image['src'])
        self.assertIn(self.article.title,image['alt'])
        self.assertIsNone(soup.find('script'))
        self.assertIsNone(soup.find('em'))
        self.assertIn(self.article.title,soup.get_text())
        self.assertNotIn(self.private.title,row.html_body)
        self.assertIn(unsubscribe_url(self.subscriber),[a['href'] for a in soup.find_all('a')])
        self.assertTrue(all(a['href'].startswith('https://') for a in soup.find_all('a')))
        snapshot=row.html_body
        self.article.image='https://example.test/changed-cover.jpg';self.article.summary='Resumo alterado depois de preparar.'
        db.session.commit()
        smtp=self.deliver();message=smtp.send_message.call_args.args[0]
        self.assertEqual(message.get_content_type(),'multipart/alternative')
        self.assertEqual([part.get_content_type() for part in message.iter_parts()],['text/plain','text/html'])
        self.assertEqual(message.get_body(preferencelist=('html',)).get_content().rstrip('\n'),snapshot.rstrip('\n'))
        self.assertIn(self.article.title,message.get_body(preferencelist=('plain',)).get_content())
        self.assertNotIn('changed-cover.jpg',message.as_string())
        self.assertIn(unsubscribe_url(self.subscriber),message['List-Unsubscribe'])

    def test_cover_urls_are_public_absolute_and_invalid_sources_are_omitted(self):
        for value in [None,'','javascript:alert(1)','data:image/png;base64,test','https://name:secret@example.test/photo.jpg']:
            self.assertEqual(newsletter_image_url(value),'')
        self.assertEqual(newsletter_image_url('//example.test/cover.jpg'),'https://example.test/cover.jpg')
        self.assertTrue(newsletter_image_url('/static/img/e-coli-niaid-960.jpg').startswith('https://www.sussurrosdosaber.com/static/'))
        image=newsletter_image_url('https://commons.wikimedia.org/wiki/Special:FilePath/E._coli_Bacteria_(7316101966).jpg')
        self.assertTrue(image.startswith('https://www.sussurrosdosaber.com/static/img/e-coli-niaid-960.jpg'))

    def test_image_change_invalidates_the_reviewed_digest_fingerprint(self):
        before=digest(NOW)['fingerprint']
        self.article.image='https://example.test/new-cover.jpg';db.session.commit()
        self.assertNotEqual(before,digest(NOW)['fingerprint'])
        with self.assertRaises(ValueError):self.queue(expected_hash=before)

    def test_article_without_cover_has_no_broken_image_and_keeps_reading_links(self):
        self.article.image='';db.session.commit();self.queue()
        row=EditorialNotification.query.filter_by(recipient=self.subscriber.email).one()
        soup=BeautifulSoup(row.html_body,'html.parser')
        self.assertIsNone(soup.find('img'))
        self.assertIn(self.article.title,soup.get_text())
        self.assertIn('Ler o artigo',soup.get_text())

    def test_legacy_queued_newsletter_still_sends_its_original_plain_text(self):
        self.queue();row=EditorialNotification.query.filter_by(recipient=self.subscriber.email).one()
        row.html_body=None;db.session.commit()
        smtp=self.deliver();message=smtp.send_message.call_args.args[0]
        self.assertFalse(message.is_multipart())
        self.assertIn(row.body,message.get_content())

    def test_preview_must_be_current_and_empty_editions_are_not_queued(self):
        with self.assertRaises(ValueError):self.queue(expected_hash='0'*64)
        db.session.rollback()
        with patch('newsletter_service.digest',return_value={'articles':[], 'fingerprint':'x'}):
            self.assertEqual(self.queue(),0)

    def test_week_boundary_and_private_articles(self):
        edition=digest(NOW)
        self.assertEqual(edition['start'],datetime(2026,10,12))
        self.assertEqual(edition['end'],datetime(2026,10,19))
        self.assertIn(self.article,edition['articles'])
        self.assertNotIn(self.private,edition['articles'])
        self.article.published_at=edition['end'];db.session.commit()
        self.assertNotIn(self.article,digest(NOW)['articles'])

    def test_unsubscribe_requires_valid_token_and_get_does_not_mutate(self):
        path='/boletim/cancelar/'+unsubscribe_token(self.subscriber)
        self.assertEqual(self.client.get(path).status_code,200)
        db.session.refresh(self.subscriber);self.assertTrue(self.subscriber.active)
        self.assertEqual(self.client.post(path+'tampered').status_code,400)
        self.assertEqual(self.client.post(path,data={'List-Unsubscribe':'One-Click'}).status_code,200)
        db.session.refresh(self.subscriber);self.assertFalse(self.subscriber.active)
        self.assertEqual(self.client.post(path).status_code,200)
        self.assertIn('no-store',self.client.get(path).headers['Cache-Control'])

    def test_cancelled_subscriber_is_skipped_before_delivery(self):
        self.queue();self.subscriber.active=False;db.session.commit()
        smtp=self.deliver()
        smtp.send_message.assert_not_called()
        row=EditorialNotification.query.filter_by(recipient=self.subscriber.email).one()
        self.assertEqual(row.last_error,CANCELLED);self.assertIsNone(row.sent_at)
        self.assertEqual(row.attempts,0)

    def test_smtp_validates_server_certificates_for_starttls_and_ssl(self):
        self.queue()
        smtp = self.deliver()
        context = smtp.starttls.call_args.kwargs['context']
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        db.session.add(EditorialNotification(recipient=self.subscriber.email,subject='Mensagem SSL',body='Teste de validação TLS'));db.session.commit()
        with patch.dict('os.environ', {'SMTP_SSL':'true', 'SMTP_TLS':'false'}), patch('mail_delivery.smtplib.SMTP_SSL') as factory:
            factory.return_value.send_message.return_value={}
            self.deliver()
            context = factory.call_args.kwargs['context']
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
            factory.return_value.starttls.assert_not_called()

    def test_smtp_disconnect_at_quit_does_not_requeue_accepted_message(self):
        self.queue()
        self.deliver(quit_failure=True)
        row=EditorialNotification.query.filter_by(recipient=self.subscriber.email).one()
        self.assertIsNotNone(row.sent_at);self.assertEqual(row.last_error,'')
        self.deliver().send_message.assert_not_called()

    def test_network_error_mid_batch_keeps_accepted_messages_sent(self):
        self.queue()
        second=EditorialNotification(recipient=self.subscriber.email,subject='Mensagem transaccional de teste',body='Segundo envio')
        db.session.add(second);db.session.commit()
        self.deliver(send_results=[{},smtplib.SMTPDataError(451,b'transient refusal')])
        rows=EditorialNotification.query.filter_by(recipient=self.subscriber.email).order_by(EditorialNotification.id).all()
        self.assertIsNotNone(rows[0].sent_at)
        self.assertIsNone(rows[1].sent_at)
        self.assertEqual(rows[1].attempts,1)
        self.assertTrue(rows[1].last_error)
        smtp=self.deliver()
        self.assertEqual(smtp.send_message.call_count,1)
        self.assertEqual(smtp.send_message.call_args.args[0]['Subject'],second.subject)

    def test_delivery_headers_and_retry_preserve_truthful_sent_state(self):
        self.queue()
        self.deliver(failure=True)
        row=EditorialNotification.query.filter_by(recipient=self.subscriber.email).one()
        self.assertIsNone(row.sent_at);self.assertEqual(row.attempts,1)
        smtp=self.deliver()
        message=smtp.send_message.call_args.args[0]
        self.assertIn('/boletim/cancelar/',message['List-Unsubscribe'])
        self.assertEqual(message['List-Unsubscribe-Post'],'List-Unsubscribe=One-Click')
        self.assertIsNotNone(row.sent_at);self.assertEqual(row.attempts,2)

    def test_disabled_newsletter_does_not_block_transactional_mail(self):
        self.queue()
        transactional=EditorialNotification(recipient=self.subscriber.email,subject='Confirme a conta',body='Mensagem transaccional',html_body='<p>Not a newsletter</p>')
        db.session.add(transactional);db.session.commit()
        with patch.dict('os.environ',{'NEWSLETTER_ENABLED':'false'}):
            with self.assertRaises(ValueError):self.queue()
            smtp=self.deliver()
        self.assertEqual(smtp.send_message.call_count,1)
        self.assertEqual(smtp.send_message.call_args.args[0]['Subject'],'Confirme a conta')
        self.assertFalse(smtp.send_message.call_args.args[0].is_multipart())
        self.assertIsNotNone(transactional.sent_at)

    def test_signup_preserves_deduplication_and_cancelled_accounts_can_resubscribe(self):
        response=self.client.post('/api/newsletter',json={'email':self.subscriber.email.upper()})
        self.assertEqual(response.status_code,200)
        self.assertEqual(Subscriber.query.filter_by(email=self.subscriber.email).count(),1)
        self.subscriber.active=False;db.session.commit()
        self.assertTrue(self.client.post('/api/newsletter',json={'email':self.subscriber.email}).json['ok'])
        db.session.refresh(self.subscriber);self.assertTrue(self.subscriber.active)
        self.assertEqual(self.client.post('/api/newsletter',json={'email':'a'*170+'@example.test'}).status_code,400)


class NewsletterPermissionsTests(unittest.TestCase):
    setUp=staff.StaffGovernanceTests.setUp
    tearDown=staff.StaffGovernanceTests.tearDown
    member=staff.StaffGovernanceTests.member
    signin=staff.StaffGovernanceTests.signin
    post=staff.StaffGovernanceTests.post

    def test_management_reuses_subscribers_permission_and_requires_csrf(self):
        author=self.member('author');self.signin(author.admin)
        self.assertEqual(self.client.get('/admin/subscritores').status_code,403)
        self.assertEqual(self.post('/admin/subscritores',action='prepare_newsletter',confirm='on',fingerprint='0'*64).status_code,403)
        director=self.member('direction');self.signin(director.admin)
        response=self.client.get('/admin/subscritores')
        self.assertEqual(response.status_code,200)
        self.assertIn('Boletim científico',response.get_data(as_text=True))
        self.assertEqual(self.client.post('/admin/subscritores',data={'action':'prepare_newsletter'}).status_code,400)

    def test_confirmation_uses_preview_hash_before_queueing(self):
        self.signin(self.primary)
        edition=digest()
        with patch('newsletter_planning.prepare_plan',return_value=3) as queue:
            response=self.post('/admin/subscritores',action='prepare_newsletter',confirm='on',fingerprint=edition['fingerprint'])
            self.assertEqual(response.status_code,303)
            queue.assert_called_once_with(edition['fingerprint'],'review','')

    def test_every_delivery_action_requires_current_permission_and_csrf(self):
        author=self.member('author');self.signin(author.admin)
        for action in ['update_limits','pause_all','resume_all','approve','schedule','start','pause','cancel','retry','confirmed_accepted','confirmed_not_accepted']:
            self.assertEqual(self.post('/admin/subscritores',action=action).status_code,403,action)
        director=self.member('direction');self.signin(director.admin)
        self.assertEqual(self.client.post('/admin/subscritores',data={'action':'pause_all'}).status_code,400)
        self.assertEqual(self.post('/admin/subscritores',action='pause_all').status_code,303)
        self.assertTrue(policy().paused)
        self.assertEqual(self.post('/admin/subscritores',action='resume_all').status_code,303)
        self.assertFalse(policy().paused)
        self.assertIn('Limites e entrega',self.client.get('/admin/subscritores').get_data(as_text=True))


