"""Isolated scientific measurement, supplier contracts and editorial scope."""
import csv
import io
import json
import os
import secrets
import time
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch
import requests
from flask import Response
import test_platform
from app import app
from models import db, Journal, Article, AdminUser, utcnow
from extensions import limiter
from governance_models import TeamMember, TeamRole, TeamAppointment
from scientific_metrics_models import ScientificMetricDay, ScientificMetricReceipt, ScientificMetricStart, ScientificMetricSource, ScientificMetricProvider
from scientific_metrics import report, selected
from scientific_metrics_collection import record
from scientific_metrics_sources import lookup, normalize_doi, bibliographic_candidates
from security_test_support import authenticate_test_session


class ScientificMetricsTests(unittest.TestCase):
    def setUp(self):
        self.ctx=app.app_context();self.ctx.push();self.previous=limiter.enabled;limiter.enabled=False
        self.token=secrets.token_hex(6)
        self.j=Journal(title='Revista '+self.token,article_title='Artigo '+self.token,slug='science-'+self.token,
            field='Biologia',description='Resumo público',content_markdown='## Métodos\nCiência aberta.',published=True,
            current_issue='Edição A '+self.token,doi='10.1234/'+self.token,publication_date=date(2026,1,1),
            authors_data=json.dumps([{'name':'Maria Cientista','orcid':'','description':''}]))
        self.other=Journal(title=self.j.title,article_title='Outro '+self.token,slug='other-science-'+self.token,
            field='Biologia',description='Resumo',content_markdown='## Métodos\nTexto',published=True,current_issue='Edição B '+self.token,publication_date=date(2025,1,1))
        self.draft=Journal(title='Rascunho '+self.token,slug='draft-science-'+self.token,field='Biologia',description='Reservado',content_markdown='Reservado',published=False)
        self.venue=Journal(title='Apresentação '+self.token,slug='venue-science-'+self.token,field='Biologia',description='Revista',content_markdown='',published=True)
        db.session.add_all([self.j,self.other,self.draft,self.venue]);db.session.flush()
        for item in (self.j,self.other):db.session.add(ScientificMetricStart(journal_id=item.id,started_at=utcnow()-timedelta(days=20)))
        ScientificMetricProvider.query.delete();db.session.commit()
        self.client=app.test_client();self.headers={'User-Agent':'Mozilla/5.0 scientific-reader'}
        self.options=dict(start=utcnow().date()-timedelta(days=29),end=utcnow().date(),source='crossref',period='30',year='',issue='',article='',author='',journal='')

    def tearDown(self):
        db.session.rollback();limiter.enabled=self.previous;self.ctx.pop()

    def path(self,journal=None):return '/revistas/'+(journal or self.j).slug

    def total(self,kind='views'):
        return sum(getattr(row,kind) for row in ScientificMetricDay.query.filter_by(journal_id=self.j.id))

    def primary(self):
        with self.client.session_transaction() as session:
            session['admin_authenticated']=True;session['admin_superuser']=True;session['admin_last_activity_at']=time.time();authenticate_test_session(session)

    def source(self,provider='crossref',**kwargs):
        row=ScientificMetricSource(journal_id=self.j.id,source=provider,doi=normalize_doi(self.j.doi),state='ok',
            citations=3 if provider!='altmetric' else None,measured_at=utcnow(),checked_at=utcnow(),**kwargs)
        db.session.add(row);db.session.commit();return row

    def test_metrics_do_not_block_existing_article_deletion(self):
        self.client.get(self.path(),headers=self.headers)
        self.source()
        # Enforce foreign keys explicitly: SQLite normally hides PostgreSQL conflicts.
        ident=self.j.id
        db.session.remove()
        with db.engine.begin() as connection:
            if db.engine.dialect.name=='sqlite':connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            connection.execute(Journal.__table__.delete().where(Journal.id==ident))
            for model in (ScientificMetricDay,ScientificMetricStart,ScientificMetricSource):
                self.assertIsNone(connection.execute(model.__table__.select().where(model.journal_id==ident)).first())
            if db.engine.dialect.name=='sqlite':connection.exec_driver_sql('PRAGMA foreign_keys=OFF')

    def test_successful_public_get_counted_once_per_network_day(self):
        for _ in range(3):self.assertEqual(self.client.get(self.path(),headers=self.headers).status_code,200)
        self.assertEqual(self.total(),1)
        self.client.get(self.path(),headers={'User-Agent':'Mozilla/5.0 a different reader'})
        self.assertEqual(self.total(),1)
        self.client.get(self.path(),headers=self.headers,environ_overrides={'REMOTE_ADDR':'192.0.2.45'})
        self.assertEqual(self.total(),2)
        self.assertNotIn('192.0.2.45',str([r.digest for r in ScientificMetricReceipt.query.all()]))

    def test_embedded_resources_do_not_inflate_reading(self):
        self.client.get(self.path(),headers={**self.headers,'Sec-Fetch-Dest':'image'})
        self.assertEqual(self.total(),0)

    def test_reporting_failure_preserves_article_and_returns_503_on_metrics_page(self):
        from sqlalchemy.exc import OperationalError
        with patch('scientific_metrics.report',side_effect=OperationalError('metrics',{},Exception())):
            response=self.client.get(self.path())
            self.assertEqual(response.status_code,200)
            self.assertIn('Ciência aberta.',response.text)
            self.assertIn('Métricas temporariamente indisponíveis',response.text)
            self.assertEqual(self.client.get(self.path()+'/metricas').status_code,503)

    def test_period_preset_overrides_stale_custom_date_inputs(self):
        from scientific_metrics import filters
        with app.test_request_context('/metricas-cientificas?period=7&from=2020-01-01&to=2020-01-05'):
            options=filters()
        self.assertEqual((options['end']-options['start']).days,6)
        self.assertEqual(options['end'],utcnow().date())

    def test_spoofed_forwarded_ip_and_country_are_ignored(self):
        for ip in ['192.0.2.1','192.0.2.2']:
            self.client.get(self.path(),headers={**self.headers,'X-Forwarded-For':ip,'CF-IPCountry':'MZ'})
        self.assertEqual(self.total(),1)
        self.assertEqual(ScientificMetricDay.query.filter_by(journal_id=self.j.id).one().country,'ZZ')

    def test_explicit_proxy_trust_uses_configured_forwarded_identity(self):
        with patch.dict(os.environ,{'SCIENTIFIC_METRICS_TRUSTED_PROXIES':'127.0.0.1/32'}):
            for ip in ['192.0.2.1','192.0.2.2']:
                self.client.get(self.path(),headers={**self.headers,'X-Forwarded-For':ip})
        self.assertEqual(self.total(),2)

    def test_head_bots_prefetch_and_privacy_signals_excluded(self):
        for extra in [{'User-Agent':'Googlebot'},{'User-Agent':'python-requests'},{'DNT':'1'},{'Sec-GPC':'1'},{'Purpose':'prefetch'},{'Sec-Purpose':'prefetch'}]:
            self.assertEqual(self.client.get(self.path(),headers={**self.headers,**extra}).status_code,200)
        self.client.head(self.path(),headers=self.headers)
        self.assertEqual(self.total(),0)

    def test_pdf_distinct_from_views_and_only_success_counted(self):
        path=self.path()+'/baixar.pdf'
        with patch('app.render_journal_pdf',return_value=Response(b'%PDF fixture',mimetype='application/pdf')):
            self.client.get(path,headers=self.headers);self.client.get(path,headers=self.headers)
        self.assertEqual(self.total('downloads'),1);self.assertEqual(self.total(),0)
        for status in [206,304,413,503]:
            with patch('app.render_journal_pdf',return_value=Response(b'fixture',status=status,mimetype='application/pdf')):
                self.client.get(path,headers=self.headers,environ_overrides={'REMOTE_ADDR':'192.0.2.'+str(status%250)})
        self.assertEqual(self.total('downloads'),1)

    def test_portal_drafts_venue_and_previews_do_not_generate_events(self):
        portal=Article.public_query().first()
        if portal:self.assertEqual(self.client.get('/artigo/'+portal.slug,headers=self.headers).status_code,200)
        self.assertEqual(self.client.get(self.path(self.draft),headers=self.headers).status_code,404)
        self.assertEqual(self.client.get(self.path(self.venue),headers=self.headers).status_code,200)
        self.primary();self.client.get(f'/admin/revistas/{self.j.id}/previsualizar',headers=self.headers)
        self.assertEqual(self.total(),0)
        self.assertNotIn('Ver métricas',self.client.get(self.path(self.venue)).text)

    def test_day_boundary_receipt_rotation(self):
        now=utcnow()
        with patch('scientific_metrics_collection.utcnow',return_value=now):self.client.get(self.path(),headers=self.headers)
        with patch('scientific_metrics_collection.utcnow',return_value=now+timedelta(days=1)):self.client.get(self.path(),headers=self.headers)
        self.assertEqual(self.total(),2)

    def test_write_failure_does_not_block_open_reading(self):
        from sqlalchemy.exc import OperationalError
        with patch('scientific_metrics_collection.db.engine.begin',side_effect=OperationalError('metrics',{},Exception())):
            response=self.client.get(self.path(),headers=self.headers)
        self.assertEqual(response.status_code,200);self.assertIn('Ciência aberta.',response.text)

    def test_public_metrics_are_free_read_only_and_never_fetch_suppliers(self):
        with patch('scientific_metrics_sources.requests.get',side_effect=AssertionError('No external calls on a page')):
            for path in [self.path(),self.path()+'/metricas','/metricas-cientificas','/revistas']:
                response=self.client.get(path)
                self.assertEqual(response.status_code,200)
        self.assertIn('Ver métricas',self.client.get(self.path()).text)
        self.assertEqual(self.client.get(self.path(self.draft)+'/metricas').status_code,404)
        self.assertEqual(self.client.get(self.path(self.venue)+'/metricas').status_code,404)

    def test_geography_suppresses_small_groups_and_unknown_locations(self):
        row=ScientificMetricDay(journal_id=self.j.id,day=utcnow().date(),country='MZ',views=4,downloads=0)
        db.session.add(row);db.session.commit()
        self.assertEqual(report([self.j],self.options)['geography'],[])
        row.views=5;db.session.commit()
        self.assertEqual(report([self.j],self.options)['geography'],[{'country':'MZ','views':5}])

    def test_periods_before_collection_and_absent_sources_are_not_fake_zero(self):
        data=report([self.j],self.options)
        self.assertEqual(data['views'],0);self.assertIsNone(data['citations']);self.assertIsNone(data['mentions'])
        old={**self.options,'start':utcnow().date()-timedelta(days=60),'end':utcnow().date()-timedelta(days=40)}
        self.assertIsNone(report([self.j],old)['views'])

    def test_filters_by_edition_year_article_author_and_journal(self):
        for change in [{'issue':self.j.current_issue},{'year':'2026'},{'article':str(self.j.id)},{'author':'maria'},{'journal':self.j.title,'year':'2026'}]:
            self.assertEqual([j.id for j in selected([self.j,self.other],{**self.options,**change})],[self.j.id])

    def test_no_cross_source_or_duplicate_doi_sum(self):
        self.source('crossref');self.source('openalex')
        self.other.doi=self.j.doi;db.session.add(ScientificMetricSource(journal_id=self.other.id,doi=self.j.doi,source='crossref',state='ok',citations=3,measured_at=utcnow()));db.session.commit()
        data=report([self.j,self.other],self.options)
        self.assertEqual(data['citations'],3);self.assertEqual(data['citation_coverage'],1)

    def test_changed_doi_stale_and_unavailable_counts_excluded(self):
        source=self.source();source.state='unavailable';db.session.commit()
        self.assertIsNone(report([self.j],self.options)['citations'])
        source.state='ok';source.measured_at=utcnow()-timedelta(days=8);db.session.commit()
        self.assertIsNone(report([self.j],self.options)['citations'])
        source.measured_at=utcnow();self.j.doi='10.1234/changed';db.session.commit()
        self.assertIsNone(report([self.j],self.options)['citations'])

    def test_altmetric_requires_explicit_display_and_export_approval(self):
        self.source('altmetric',mentions=7,attention_score=.25)
        with patch.dict(os.environ,{'ALTMETRIC_LICENSE_APPROVED':'true','ALTMETRIC_PUBLIC_DISPLAY_APPROVED':'false'}):
            self.assertIsNone(report([self.j],self.options,True)['mentions'])
            self.assertEqual(report([self.j],self.options,False)['mentions'],7)
        with patch.dict(os.environ,{'ALTMETRIC_LICENSE_APPROVED':'true','ALTMETRIC_PUBLIC_DISPLAY_APPROVED':'true'}):
            self.assertEqual(report([self.j],self.options,True)['mentions'],7)

    def test_admin_requires_existing_journal_permissions(self):
        self.assertEqual(self.client.get('/admin/revistas/metricas').status_code,302)
        account=AdminUser(username='metrics-'+self.token,password_hash='unused',display_name='Gestor',is_superadmin=False,
            two_factor_enabled=True,totp_secret='JBSWY3DPEHPK3PXP',governance_managed=True)
        role=TeamRole(code='metrics-'+self.token,name='Gestor de revista',permissions=['journal.manage'])
        member=TeamMember(name='Gestor',email=self.token+'@example.test',status='active',accepted_at=utcnow(),admin=account)
        grant=TeamAppointment(member=member,role=role,journal_id=self.j.id,starts_on=date.today())
        db.session.add_all([account,role,member,grant]);db.session.commit()
        with self.client.session_transaction() as session:
            session['admin_authenticated']=True;session['admin_id']=account.id;session['admin_2fa_verified']=True;session['admin_last_activity_at']=time.time();authenticate_test_session(session)
        response=self.client.get('/admin/revistas/metricas')
        self.assertEqual(response.status_code,200);self.assertIn(self.j.article_title,response.text);self.assertNotIn(self.other.article_title,response.text)
        grant.active=False;db.session.commit()
        self.assertEqual(self.client.get('/admin/revistas/metricas').status_code,403)

    def test_csv_formula_safety_and_filter_scope(self):
        self.primary();self.j.article_title='=1+1';db.session.commit()
        response=self.client.get('/admin/revistas/metricas/exportar.csv',query_string={'article':str(self.j.id)})
        self.assertEqual(response.status_code,200)
        rows=list(csv.reader(io.StringIO(response.text.lstrip('\ufeff'))))
        self.assertEqual(len(rows),2);self.assertTrue(rows[1][1].startswith("'="))
        self.assertNotIn(self.other.slug,response.text)
        self.assertIn('no-store',response.headers['Cache-Control'])

    def test_invalid_filters_rejected_and_unrecognised_args_do_not_break_links(self):
        self.primary()
        for values in [{'period':'bad'},{'period':'custom','from':'no-date'},{'period':'custom','from':'2020-01-01','to':'2026-01-01'},{'source':'altmetric'},{'article':'-1'},{'year':'180x'}]:
            self.assertEqual(self.client.get('/admin/revistas/metricas',query_string=values).status_code,400)
        self.assertEqual(self.client.get('/admin/revistas/metricas?endpoint=bad').status_code,200)

    def test_refresher_leases_and_retains_old_result_on_failure(self):
        with patch('scientific_metrics.published_query',return_value=Journal.query.filter_by(id=self.j.id)),patch('scientific_metrics.lookup',return_value={'state':'ok','citations':2,'mentions':None,'attention_score':None}) as api,patch('scientific_metrics.time.sleep'):
            first=app.test_cli_runner().invoke(args=['metricas-cientificas-actualizar','--source','crossref'])
            second=app.test_cli_runner().invoke(args=['metricas-cientificas-actualizar','--source','crossref'])
        self.assertEqual(first.exit_code,0,first.output);self.assertEqual(second.exit_code,0,second.output);self.assertEqual(api.call_count,1)
        row=ScientificMetricSource.query.filter_by(journal_id=self.j.id,source='crossref').one();row.next_attempt=utcnow()-timedelta(days=1)
        db.session.get(ScientificMetricProvider,'crossref').next_attempt=utcnow()-timedelta(days=1);db.session.commit()
        with patch('scientific_metrics.published_query',return_value=Journal.query.filter_by(id=self.j.id)),patch('scientific_metrics.lookup',return_value={'state':'unavailable'}),patch('scientific_metrics.time.sleep'):
            result=app.test_cli_runner().invoke(args=['metricas-cientificas-actualizar','--source','crossref'])
        self.assertEqual(result.exit_code,0,result.output);self.assertEqual(row.citations,2);self.assertEqual(row.state,'unavailable')

    def test_supplier_contracts_confirm_zero_and_doi_identity(self):
        bodies={'crossref':{'message':{'DOI':self.j.doi,'is-referenced-by-count':0}},'openalex':{'doi':'https://doi.org/'+self.j.doi,'cited_by_count':0},'opencitations':[{'count':'0'}],
                'altmetric':{'doi':self.j.doi,'cited_by_posts_count':0,'score':.25}}
        for name,body in bodies.items():
            response=MagicMock(status_code=200);response.iter_content.return_value=[json.dumps(body).encode()]
            with patch.dict(os.environ,{'ALTMETRIC_API_KEY':'fixture','ALTMETRIC_LICENSE_APPROVED':'true'}),patch('scientific_metrics_sources.requests.get',return_value=response) as api:
                result=lookup(name,self.j.doi)
            self.assertEqual(result['state'],'ok',name)
            self.assertEqual(result['mentions'] if name=='altmetric' else result['citations'],0)
            self.assertFalse(api.call_args.kwargs['allow_redirects'])
        response=MagicMock(status_code=200);response.iter_content.return_value=[json.dumps({'message':{'DOI':'10.1234/other','is-referenced-by-count':99}}).encode()]
        with patch('scientific_metrics_sources.requests.get',return_value=response):self.assertEqual(lookup('crossref',self.j.doi)['state'],'mismatch')

    def test_supplier_errors_missing_values_limits_and_license(self):
        for code,state in [(404,'not_found'),(429,'rate_limited'),(503,'unavailable'),(302,'unavailable')]:
            response=MagicMock(status_code=code,headers={'Retry-After':'3600'})
            with patch('scientific_metrics_sources.requests.get',return_value=response):self.assertEqual(lookup('crossref',self.j.doi)['state'],state)
        for value in [None,True,-1,1.5,'bad']:
            response=MagicMock(status_code=200);response.iter_content.return_value=[json.dumps({'message':{'DOI':self.j.doi,'is-referenced-by-count':value}}).encode()]
            with patch('scientific_metrics_sources.requests.get',return_value=response):self.assertEqual(lookup('crossref',self.j.doi)['state'],'unavailable')
        with patch('scientific_metrics_sources.requests.get',side_effect=requests.Timeout()):self.assertEqual(lookup('crossref',self.j.doi)['state'],'unavailable')
        with patch.dict(os.environ,{'ALTMETRIC_LICENSE_APPROVED':'false'}),patch('scientific_metrics_sources.requests.get') as api:
            self.assertEqual(lookup('altmetric',self.j.doi)['state'],'requires_license');api.assert_not_called()
        self.assertEqual(lookup('crossref','invalid')['state'],'no_doi')

    def test_bibliographic_candidates_do_not_modify_editorial_metadata(self):
        response=MagicMock(status_code=200);response.__enter__.return_value=response
        response.iter_content.return_value=[json.dumps({'message':{'items':[{'DOI':'10.1234/proposal','title':['Proposta'],'published':{'date-parts':[[2026]]},'author':[{'given':'Maria','family':'Cientista'}]}]}}).encode()]
        before=self.j.doi
        with patch('scientific_metrics_sources.requests.get',return_value=response):candidates=bibliographic_candidates(self.j)
        self.assertEqual(candidates[0]['doi'],'10.1234/proposal');self.assertEqual(self.j.doi,before)

    def test_rate_limit_applies_to_whole_provider(self):
        with patch('scientific_metrics.published_query',return_value=Journal.query.filter(Journal.id.in_([self.j.id,self.other.id]))),patch('scientific_metrics.lookup',return_value={'state':'rate_limited','retry_seconds':3600}) as api:
            result=app.test_cli_runner().invoke(args=['metricas-cientificas-actualizar','--source','crossref'])
        self.assertEqual(result.exit_code,0,result.output);self.assertEqual(api.call_count,1)
        self.assertGreater(db.session.get(ScientificMetricProvider,'crossref').next_attempt,utcnow()+timedelta(minutes=59))
