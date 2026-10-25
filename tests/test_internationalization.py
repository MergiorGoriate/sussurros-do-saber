"""Locale routes, immutable sources, approval gates and bounded translation worker."""
import copy
import os
import secrets
import tempfile
import time
import unittest
from datetime import timedelta
from unittest.mock import patch
import test_platform
from app import app
from models import db, Article, Author, Category, Journal, utcnow
from extensions import limiter
from security_test_support import authenticate_test_session
from translation_models import (ContentTranslation as Translation, TranslationVersion as Version,
    TranslationJob as Job, TranslationEvent as Event, TranslationQuota, TranslationWorker, InterfaceTranslation, InterfaceBatch)
from dissemination_ai import GenerationError
import translation_service as service
from internationalization import preferred


class InternationalizationTests(unittest.TestCase):
    def setUp(self):
        self.ctx=app.app_context();self.ctx.push();self.previous=limiter.enabled;limiter.enabled=False
        self.env=patch.dict(os.environ,dict(OPENAI_API_KEY='fixture',TRANSLATION_TEXT_MODEL='fixture',TRANSLATION_REVIEW_MODEL='fixture',TRANSLATION_DAILY_UNITS='100',I18N_ENABLED='true'))
        self.env.start()
        for model in (Event,Job,Version,Translation,TranslationQuota,TranslationWorker,InterfaceBatch,InterfaceTranslation):model.query.delete()
        token=secrets.token_hex(5)
        self.article=Article(title='Plantas '+token,slug='i18n-'+token,summary='As plantas utilizam luz.',
            body='## Método\nAs plantas utilizam luz. $x=2$ [Fonte](https://example.org/paper).\n\n![Planta](https://example.org/plant.png)',
            references='Autor (2020). Referência original.',keywords='plantas',status='published',
            author_rel=Author.query.first(),category_rel=Category.query.first())
        db.session.add(self.article);db.session.commit()
        self.client=app.test_client()
        with self.client.session_transaction() as s:
            s.update(admin_authenticated=True,admin_superuser=True,admin_last_activity_at=time.time(),csrf_token='i18n-test')
            authenticate_test_session(s)

    def tearDown(self):
        db.session.rollback();self.env.stop();limiter.enabled=self.previous;self.ctx.pop()

    def make(self,publish=False):
        original=service.source('article',self.article.id)
        content=dict(original,title='Plants and sunlight',summary='Plants use light.',keywords='plants',
            body=original['body'].replace('Método','Method').replace('As plantas utilizam luz.','Plants use light.').replace('![Planta]','![Plant]'))
        item=Translation(kind='article',source_id=self.article.id);db.session.add(item);db.session.flush()
        service.add_version(item,original,content,dict(ready=True,faithful=True,issues=[]))
        if publish:
            item.state='published';item.approved_version=1;item.published_version=1;item.reviewed_at=utcnow()
        db.session.commit();return item

    def post(self,item,action,**data):
        return self.client.post(f'/admin/internacionalizacao/{item.id}/accao',data=dict(csrf_token='i18n-test',version=item.version,action=action,**data))

    def test_negotiation_manual_cookie_country_browser_and_untrusted_country(self):
        with patch.dict(os.environ,{'TRUST_CLOUDFLARE_COUNTRY':'true'}):
            self.assertEqual(preferred({'CF-IPCountry':'MZ','Accept-Language':'en'},{}),'pt')
            self.assertEqual(preferred({'CF-IPCountry':'US','Accept-Language':'pt'},{}),'en')
            self.assertEqual(preferred({'CF-IPCountry':'US'},{'sds_language':'pt'}),'pt')
            self.assertEqual(preferred({'CF-IPCountry':'FR','Accept-Language':'en-GB,en;q=0.8'},{}),'en')
        with patch.dict(os.environ,{'TRUST_CLOUDFLARE_COUNTRY':'false'}):
            self.assertEqual(preferred({'CF-IPCountry':'US'},{}),'pt')

    def test_initial_redirect_only_home_and_explicit_paths_are_stable(self):
        response=self.client.get('/',headers={'Accept-Language':'en','User-Agent':'Mozilla/5.0'})
        self.assertEqual(response.status_code,302);self.assertEqual(response.location,'/en/')
        self.assertEqual(self.client.get('/sobre',headers={'Accept-Language':'en'}).status_code,200)
        self.assertEqual(self.client.get('/',headers={'Accept-Language':'en','User-Agent':'Googlebot'}).status_code,200)
        self.assertEqual(self.client.get('/en/').status_code,200)

    def test_switch_preserves_query_and_rejects_open_redirects(self):
        r=self.client.get('/idioma/en',query_string={'next':'/artigos?q=plantas&page=2'})
        self.assertEqual(r.location,'/en/artigos?q=plantas&page=2')
        self.assertIn('sds_language=en',r.headers['Set-Cookie'])
        for target in ['https://evil.test','//evil.test','/\\evil.test']:
            self.assertEqual(self.client.get('/idioma/en',query_string={'next':target}).status_code,400)

    def test_untranslated_article_switch_has_clear_existing_alternative(self):
        r=self.client.get('/idioma/en',query_string={'next':'/artigo/'+self.article.slug})
        self.assertIn('/en/artigos?original=',r.location)
        page=self.client.get('/en/artigo/'+self.article.slug)
        self.assertEqual(page.status_code,404);self.assertIn('Read the Portuguese original',page.text)

    def test_english_article_uses_only_published_version_and_self_canonical(self):
        item=self.make()
        self.assertEqual(self.client.get('/en/artigo/'+self.article.slug).status_code,404)
        self.assertEqual(self.post(item,'publish').status_code,409)
        self.assertEqual(self.post(item,'approve',reviewed='yes').status_code,302)
        self.assertEqual(self.post(item,'publish').status_code,302)
        page=self.client.get('/en/artigo/'+self.article.slug)
        self.assertEqual(page.status_code,200);self.assertIn('Plants and sunlight',page.text)
        self.assertIn('lang="en"',page.text);self.assertIn('/en/artigo/'+self.article.slug,page.text)
        self.assertEqual(page.headers['Content-Language'],'en');self.assertIn('no-store',page.headers['Cache-Control'])
        self.assertEqual(self.article.title.split()[0],'Plantas')
        self.assertIn('## Método',self.article.body)

    def test_update_preserves_published_translation_and_blocks_stale_approval(self):
        item=self.make(publish=True)
        self.article.body+='\nNovo resultado.';db.session.commit()
        self.assertEqual(service.state(item),'outdated')
        self.assertEqual(item.published_version,1)
        page=self.client.get('/en/artigo/'+self.article.slug)
        self.assertEqual(page.status_code,200);self.assertIn('awaiting an editorial update',page.text)
        self.assertEqual(self.post(item,'approve',reviewed='yes').status_code,409)

    def test_manual_edit_invalidates_approval_and_queues_review(self):
        item=self.make(publish=True)
        content=dict(service.version(item).content,title='Plants and light')
        self.assertEqual(self.post(item,'edit',**content).status_code,302)
        self.assertEqual(item.published_version,1);self.assertIsNone(item.approved_version)
        self.assertEqual(Job.query.one().mode,'review')
        self.assertEqual(self.post(item,'publish').status_code,409)

    def test_source_references_formula_links_and_heading_integrity_are_checked(self):
        item=self.make();row=service.version(item)
        for field,replacement in [('references','Invented reference'),('body',row.content['body'].replace('$x=2$','$x=7$')),
                                  ('body',row.content['body'].replace('https://example.org/paper','https://evil.test')),
                                  ('body',row.content['body'].replace('## Method','# Method'))]:
            content=dict(row.content);content[field]=replacement
            with self.assertRaises(GenerationError):service.validate(row.source,content)

    def test_masked_translation_restores_exact_formula_and_code(self):
        source='## Teste\n$x=2$ e `x = 2` [Fonte](https://example.org) (Autor, 2020).'
        protected,tokens=service.protect(source)
        self.assertNotIn('$x=2$',protected)
        self.assertEqual(service.restore(protected,tokens),source)
        with self.assertRaises(GenerationError):service.restore(protected+next(iter(tokens)),tokens)

    def test_batch_is_async_prioritized_and_can_pause_cancel_pending(self):
        with patch('translation_service.translate') as translator:
            r=self.client.post('/admin/internacionalizacao/lote',data=dict(csrf_token='i18n-test',kind='article',source_ids=[self.article.id],priority='3'))
        self.assertEqual(r.status_code,302);translator.assert_not_called()
        job=Job.query.one();self.assertEqual(job.priority,3)
        self.assertEqual(self.client.post(f'/admin/internacionalizacao/tarefas/{job.id}',data=dict(csrf_token='i18n-test',action='pause')).status_code,302)
        self.assertEqual(job.state,'paused')
        self.assertFalse(service.process_one())
        self.client.post(f'/admin/internacionalizacao/tarefas/{job.id}',data=dict(csrf_token='i18n-test',action='cancel'))
        self.assertEqual(job.state,'cancelled')

    def test_worker_reviews_without_publishing_and_releases_global_slot(self):
        with app.test_request_context('/'):
            item=service.queue('article',self.article.id);db.session.commit()
        original=service.source('article',self.article.id)
        with patch('translation_service.translate',return_value=(original,dict(ready=True,faithful=True,issues=[]))):
            self.assertTrue(service.process_one())
        self.assertEqual(item.state,'review');self.assertIsNone(item.published_version)
        self.assertIsNone(db.session.get(TranslationWorker,1).lease)
        self.assertFalse(service.process_one())

    def test_worker_failure_is_terminal_and_does_not_expose_secrets(self):
        with app.test_request_context('/'):
            item=service.queue('article',self.article.id);db.session.commit()
        with patch('translation_service.translate',side_effect=RuntimeError('secret-key')):service.process_one()
        self.assertEqual(item.state,'error');self.assertNotIn('secret-key',item.error)
        self.assertFalse(service.process_one())

    def test_scientific_journal_translation_excludes_manuscript_pdf_and_doi(self):
        token=secrets.token_hex(5)
        journal=Journal(title='Revista '+token,article_title='Plantas',slug='i18n-journal-'+token,field='Biologia',
            description='Descrição',summary='Resumo',keywords='plantas',content_markdown='MANUSCRITO IMUTÁVEL',published=True,doi='10.9999/'+token)
        db.session.add(journal);db.session.commit()
        source=service.source('journal',journal.id)
        self.assertNotIn('content_markdown',source);self.assertNotIn('doi',source)
        self.assertNotIn('MANUSCRITO IMUTÁVEL',str(source))
        self.assertEqual(journal.content_markdown,'MANUSCRITO IMUTÁVEL')

    def test_interface_catalogue_is_escaped_and_incomplete_pages_are_noindex(self):
        row=InterfaceTranslation(key='a'*64,source='Pesquisar',english='<script>alert(1)</script>',published=True)
        db.session.add(row);db.session.commit()
        page=self.client.get('/en/artigos')
        self.assertIn('&lt;script&gt;',page.text);self.assertNotIn('<script>alert(1)</script>',page.text)
        self.assertIn('noindex',page.headers.get('X-Robots-Tag',''))

    def test_article_listing_translates_headings_categories_and_search_labels(self):
        from bs4 import BeautifulSoup
        page=self.client.get('/en/artigos')
        soup=BeautifulSoup(page.text,'html.parser')
        self.assertEqual(soup.select_one('h1').get_text(strip=True),'All articles')
        self.assertEqual(soup.select_one('.section-rule span').get_text(strip=True),'Explore content')
        self.assertEqual([a.get_text(strip=True) for a in soup.select('.filter-row a')],
                         ['All','Biology','Health','Environment','Education','Technology','Space'])
        links=soup.select('.filter-row a')
        self.assertTrue(all('/en/artigos' in a['href'] for a in links))
        page=self.client.get('/en/artigos',query_string={'q':'<science>'})
        self.assertIn('Results for',page.text)
        self.assertIn('&lt;science&gt;',page.text)
        original=self.client.get('/artigos')
        self.assertIn('Todos os artigos',original.text)
        self.assertIn('Explorar conteúdos',original.text)

    def test_missing_translation_notice_links_to_portuguese_original(self):
        from bs4 import BeautifulSoup
        page=self.client.get('/en/artigos',query_string={'original':self.article.slug})
        soup=BeautifulSoup(page.text,'html.parser')
        link=soup.select_one('.translation-notice a')
        self.assertIsNotNone(link)
        self.assertEqual(link['href'],'/artigo/'+self.article.slug)
        self.assertIn('not yet published',soup.select_one('.translation-notice').get_text())

    def test_english_query_matches_published_translated_content(self):
        self.make(publish=True)
        page=self.client.get('/en/artigos?q=sunlight')
        self.assertEqual(page.status_code,200);self.assertIn('Plants and sunlight',page.text)

    def test_editorial_routes_require_authentication_and_csrf(self):
        self.assertEqual(app.test_client().get('/admin/internacionalizacao/').status_code,302)
        self.assertEqual(self.client.post('/admin/internacionalizacao/lote',data=dict(source_ids=[self.article.id])).status_code,400)
        self.assertEqual(self.client.get('/admin/internacionalizacao/').status_code,200)
        self.assertEqual(self.client.get('/admin/internacionalizacao/interface').status_code,200)

    def test_disable_switch_keeps_portuguese_and_hides_language_selector(self):
        with patch.dict(os.environ,{'I18N_ENABLED':'false'}):
            self.assertEqual(self.client.get('/en/').status_code,404)
            page=self.client.get('/')
            self.assertEqual(page.status_code,200);self.assertNotIn('class="language-selector"',page.text)

    def test_ai_translation_keeps_protected_parts_and_translates_alt_text(self):
        original=service.source('article',self.article.id)
        def provider(model,instruction,data):
            if 'original' in data:
                return {'faithful':True,'issues':[]}
            return {key:text.replace('Método','Method').replace('Planta','Plant').replace('plantas','plants').replace('As plants utilizam luz.','Plants use light.') for key,text in data.items()}
        with patch('translation_service.call',side_effect=provider):
            translated,report=service.translate(original)
        self.assertTrue(report['ready']);self.assertIn('![Plant]',translated['body'])
        self.assertIn('$x=2$',translated['body']);self.assertEqual(translated['references'],original['references'])

    def test_single_worker_lease_prevents_parallel_provider_calls(self):
        with app.test_request_context('/'):
            service.queue('article',self.article.id);db.session.commit()
        db.session.add(TranslationWorker(id=1,lease='occupied',expires_at=utcnow()+timedelta(minutes=10)));db.session.commit()
        with patch('translation_service.translate') as provider:
            self.assertFalse(service.process_one())
        provider.assert_not_called();self.assertEqual(Job.query.one().state,'queued')

    def test_interface_batch_requires_review_and_publication_to_change_ui(self):
        row=InterfaceTranslation(key='b'*64,source='Pesquisar',english='',published=False)
        batch=InterfaceBatch(keys=[row.key]);db.session.add_all([row,batch]);db.session.flush()
        item=Translation(kind='interface',source_id=batch.id);db.session.add(item);db.session.flush()
        service.add_version(item,{row.key:row.source},{row.key:'Search reviewed'},dict(ready=True,faithful=True,issues=[]));db.session.commit()
        self.assertFalse(row.published)
        self.assertEqual(self.post(item,'publish').status_code,409)
        self.assertEqual(self.post(item,'approve',reviewed='yes').status_code,302)
        self.assertEqual(self.post(item,'publish').status_code,302)
        self.assertTrue(row.published);self.assertEqual(row.english,'Search reviewed')

    def test_source_update_records_outdated_event_without_deleting_published_version(self):
        item=self.make(publish=True)
        self.article.summary+=' Actualização.';db.session.commit()
        self.assertEqual(item.state,'outdated');self.assertEqual(item.published_version,1)
        self.assertTrue(Event.query.filter_by(translation_id=item.id,action='source_updated').first())

    def test_english_dissemination_uses_reviewed_current_translation(self):
        from dissemination_service import snapshot
        self.make(publish=True)
        source=snapshot('portal_en',self.article.id)
        self.assertEqual(source['language'],'en');self.assertEqual(source['title'],'Plants and sunlight')
        self.article.body+=' Mudança.';db.session.commit()
        with self.assertRaises(GenerationError):snapshot('portal_en',self.article.id)

    def test_public_premium_translation_changes_only_presentation(self):
        from premium_models import PremiumPlan
        import hashlib
        name='Plano público '+secrets.token_hex(4)
        plan=PremiumPlan(name=name,interval='monthly',price_minor=12345,currency='MZN',description='Descrição pública.',benefits=['Benefício público'],active=True)
        row=InterfaceTranslation(key=hashlib.sha256(name.encode()).hexdigest(),source=name,english='Reviewed monthly plan',published=True)
        db.session.add_all([plan,row]);db.session.commit()
        page=self.client.get('/en/premium')
        self.assertEqual(page.status_code,200);self.assertIn('Reviewed monthly plan',page.text)
        self.assertEqual(plan.name,name);self.assertEqual(plan.price_minor,12345);self.assertEqual(plan.benefits,['Benefício público'])

    def test_new_draft_can_be_translated_and_approved_but_not_published_before_original(self):
        self.article.status='draft';db.session.commit()
        item=self.make()
        self.assertEqual(self.post(item,'approve',reviewed='yes').status_code,302)
        self.assertEqual(self.post(item,'publish').status_code,409)
        self.assertEqual(self.client.get('/en/artigo/'+self.article.slug).status_code,404)
        self.article.status='published';db.session.commit()
        self.assertEqual(item.state,'approved')
        self.assertEqual(self.post(item,'publish').status_code,302)
        self.assertEqual(self.client.get('/en/artigo/'+self.article.slug).status_code,200)


if __name__=='__main__':unittest.main()
