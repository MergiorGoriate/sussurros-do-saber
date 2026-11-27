"""Synthetic automation tests; no public network or production data."""
from datetime import timedelta
import json
import subprocess
from unittest.mock import patch
import unittest

import test_staff_governance as fixtures
from app import app
from automation.config import validate_settings
from automation.engine import claim, complete, enqueue, execute_claimed, queue_due, recover_expired, retention, seed_operators
from automation.http import FetchError, fetch, portal_url
from automation.models import AutomationAlert, AutomationDiscovery, AutomationOperator, AutomationRun
from automation.operators import editorial, finding, infrastructure, report, research, seo, workflow
from governance_models import StaffNotice, StaffTask
from models import db, utcnow


class AutomationTests(unittest.TestCase):
    setUp = fixtures.StaffGovernanceTests.setUp
    member = fixtures.StaffGovernanceTests.member
    signin = fixtures.StaffGovernanceTests.signin
    post = fixtures.StaffGovernanceTests.post
    article = fixtures.StaffGovernanceTests.article

    def tearDown(self):
        db.session.rollback()
        StaffNotice.query.filter_by(resource_type='automation_run').delete()
        AutomationAlert.query.delete()
        AutomationRun.query.delete()
        AutomationDiscovery.query.delete()
        AutomationOperator.query.delete()
        db.session.commit()
        seed_operators()
        fixtures.StaffGovernanceTests.tearDown(self)

    def enable(self, code):
        operator = db.session.get(AutomationOperator, code)
        operator.enabled = True
        db.session.commit()
        return operator

    def test_admin_permission_configuration_queue_and_reports(self):
        self.assertEqual(self.client.get('/admin/automacao').status_code, 302)
        member = self.member('portal_editor')
        self.signin(member.admin)
        self.assertEqual(self.client.get('/admin/automacao').status_code, 403)
        self.assertEqual(self.post('/admin/automacao/operadores/editorial/executar').status_code, 403)
        self.signin(self.primary)
        self.assertEqual(self.client.get('/admin/automacao').status_code, 200)
        self.assertEqual(self.client.post('/admin/automacao/operadores/editorial/executar').status_code, 400)
        self.assertEqual(self.post('/admin/automacao/operadores/seo', interval=15, retention=90, timeout=3,
                                   paths=['https://example.invalid/not-authorized']).status_code, 400)
        self.assertEqual(self.post('/admin/automacao/operadores/editorial', interval=15, retention=90,
                                   batch=2, enabled='yes', notify='yes').status_code, 302)
        self.assertEqual(self.post('/admin/automacao/operadores/editorial/executar').status_code, 303)
        self.assertEqual(self.post('/admin/automacao/operadores/editorial/executar').status_code, 303)
        run = AutomationRun.query.one()
        self.assertEqual(run.status, 'queued')
        self.assertEqual(claim(utcnow()), run.id)
        self.assertTrue(execute_claimed(run.id))
        self.assertIn(run.status, ('success', 'warning'))
        self.assertIn('findings', run.result)
        self.assertEqual(self.client.get('/admin/automacao/execucoes/' + str(run.id)).status_code, 200)
        self.assertEqual(self.client.get('/admin/automacao/alertas').status_code, 200)
        if AutomationAlert.query.first():
            ident = AutomationAlert.query.first().id
            self.assertEqual(self.post(f'/admin/automacao/alertas/{ident}/resolver').status_code, 303)
            self.assertIsNotNone(db.session.get(AutomationAlert, ident).resolved_at)

    def test_admin_report_and_alert_layout_with_synthetic_results(self):
        self.signin(self.primary)
        run = AutomationRun(operator_code='research', trigger='manual', version='1.0',
                            status='warning', queued_at=utcnow(), result={
            'pending': {'artigos': 2}, 'topics_checked': ['astronomia'], 'duplicates': 0,
            'findings': [{'severity': 'HIGH', 'subject': 'Ensaio', 'description': 'Observação de teste',
                          'recommendation': 'Revisão humana de teste'}],
            'records': [{'title': 'Publicação de teste', 'url': 'https://example.org/fixture',
                         'authors': ['Autor de teste'], 'doi': '10.1234/fixture', 'source': 'Crossref',
                         'topic': 'astronomia', 'published': '2026-11-26'}],
        })
        alert = AutomationAlert(operator_code='research', fingerprint='fixture-layout',
                                severity='HIGH', description='Alerta de teste',
                                subject='Ensaio', recommendation='Rever o registo')
        db.session.add_all([run, alert])
        db.session.commit()
        ident = alert.id
        response = self.client.get(f'/admin/automacao/execucoes/{run.id}')
        self.assertEqual(response.status_code, 200)
        for label in ['Cronologia da execução', 'artigos', 'Observação de teste',
                      'Publicação de teste', 'https://example.org/fixture']:
            self.assertIn(label, response.get_data(as_text=True))
        response = self.client.get('/admin/automacao/alertas')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Alerta de teste', response.get_data(as_text=True))
        self.assertIn('Marcar resolvido', response.get_data(as_text=True))
        self.assertEqual(self.post(f'/admin/automacao/alertas/{ident}/resolver').status_code, 303)
        self.assertNotIn('Alerta de teste', self.client.get('/admin/automacao/alertas').get_data(as_text=True))
        self.assertIn('Alerta de teste', self.client.get('/admin/automacao/alertas?estado=resolvidos').get_data(as_text=True))

    def test_one_active_run_schedule_timeout_and_retention(self):
        operator = self.enable('workflow')
        operator.next_run_at = utcnow() - timedelta(minutes=1)
        db.session.commit()
        queue_due(utcnow()); queue_due(utcnow())
        self.assertEqual(AutomationRun.query.count(), 1)
        self.assertIsNone(enqueue('workflow', 'manual'))
        ident = claim(utcnow())
        self.assertIsNotNone(ident)
        self.assertIsNone(claim(utcnow()))
        run = db.session.get(AutomationRun, ident)
        run.deadline_at = utcnow() - timedelta(minutes=1)
        db.session.commit()
        recover_expired(utcnow())
        self.assertEqual(run.status, 'failed')
        self.assertFalse(complete(ident, report()))
        run.finished_at = utcnow() - timedelta(days=100)
        db.session.commit()
        retention(utcnow())
        self.assertIsNone(db.session.get(AutomationRun, ident))

    def test_editorial_and_workflow_are_read_only(self):
        member = self.member()
        article = self.article(member)
        article.body = '## Primeiro\n\n#### Salto\n\n![ ](https://example.org/a.jpg)\n\n[Ausente](/artigo/nao-publicado-ensaio)'
        article.status = 'published'
        db.session.add(StaffTask(title='Ensaio em atraso', assignee_id=member.id,
                                 due_on=utcnow().date()-timedelta(days=1),status='pending'))
        db.session.commit()
        original = article.body
        output = editorial({'batch': 40}, {'artigo': article.id - 1})
        codes = {x['code'] for x in output['findings'] if x['subject'] == f'artigo:{article.id}'}
        self.assertTrue({'heading-order', 'image-alt', 'missing-internal'} <= codes)
        self.assertEqual(article.body, original)
        result = workflow({'age_days': 7}, {})
        self.assertGreaterEqual(result['pending']['tarefas'], 1)
        self.assertEqual(article.status, 'published')

    def test_seo_and_health_keep_network_destinations_fixed(self):
        for path in ('https://example.invalid/other', '/admin', '/api/', '/arbitrary'):
            with self.assertRaises(ValueError):
                portal_url(path)
        with patch('automation.http.requests.Session') as session:
            with self.assertRaises(ValueError):
                fetch('https://example.invalid/other', 3)
            session.assert_not_called()
        html = b'<title>Fixture</title><meta name="robots" content="noindex">'
        with patch('automation.operators.fetch', side_effect=[
            (200, {}, html), (200, {}, b'User-agent: *'), (200, {}, b'<invalid/>'), (503, {}, b'')
        ]) as mock_fetch:
            result = seo({'paths':['/'], 'timeout':3}, {})
        self.assertEqual(mock_fetch.call_count, 4)
        self.assertTrue({'noindex','canonical','missing-description','robots-sitemap','sitemap-invalid','http'}
                        <= {x['code'] for x in result['findings']})
        with patch('automation.operators.fetch', side_effect=FetchError('Resposta indisponível.')), patch.dict('os.environ', {'AUTOMATION_BACKUP_REPORT_PATH':''}):
            result = infrastructure({'timeout':3, 'backup_age_days':7}, {})
        self.assertEqual(result['database'], 'ok')
        self.assertIn('unavailable', {x['code'] for x in result['findings']})

    def test_research_records_real_response_metadata_and_skips_duplicates(self):
        item = {'DOI':'10.1234/fixture', 'title':['Metadados de ensaio'], 'author':[{'family':'Fixture'}],
                'published':{'date-parts':[[2026,11,26]]}}
        data = json.dumps({'message':{'items':[item, item, {'title':['Sem DOI']}]}}).encode()
        self.enable('research')
        run = enqueue('research', 'manual'); db.session.commit()
        ident = claim(utcnow())
        with patch('automation.operators.fetch', return_value=(200, {}, data)):
            self.assertTrue(execute_claimed(ident))
        self.assertEqual(len(run.result['records']), 1)
        self.assertEqual(run.result['records'][0]['doi'], '10.1234/fixture')
        self.assertEqual(run.result['records'][0]['published'], '2026-11-26')
        with patch('automation.operators.fetch', return_value=(200, {}, data)):
            output = research({'topics':['astronomia'], 'days':14, 'timeout':3}, {})
        self.assertEqual(output['records'], [])
        self.assertEqual(output['duplicates'], 2)

    def test_alerts_deduplicate_and_errors_do_not_retain_exception_details(self):
        operator = self.enable('workflow')
        operator.notify = True
        db.session.commit()
        for _ in range(2):
            run = enqueue('workflow','manual'); db.session.commit()
            claim(utcnow())
            output = report()
            finding(output, 'HIGH', 'fixture', 'workflow', 'Observação de ensaio.')
            complete(run.id, output)
        self.assertEqual(AutomationAlert.query.filter_by(subject='workflow').one().occurrences, 2)
        self.assertEqual(StaffNotice.query.filter_by(resource_type='automation_run', admin_id=self.primary.id).count(), 1)
        run = enqueue('workflow','manual'); db.session.commit()
        claim(utcnow())
        with patch.dict('automation.engine.OPERATORS', {'workflow': lambda *_: (_ for _ in ()).throw(RuntimeError('private fixture'))}):
            self.assertTrue(execute_claimed(run.id))
        self.assertEqual(run.status, 'failed')
        self.assertNotIn('private fixture', json.dumps(run.result) + run.error)
        with self.assertRaises(ValueError):
            validate_settings('research', {'topics':['arbitrary text']})
        with self.assertRaises(ValueError):
            validate_settings('editorial', {'batch':10000})

    def test_worker_process_timeout_persists_failure_and_reports_nonzero(self):
        self.enable('workflow')
        run = enqueue('workflow', 'manual')
        db.session.commit()
        ident = run.id
        with patch.dict('os.environ', {'SUSSURROS_AUTOMATION_WORKER':'true'}), patch(
            'automation.engine.subprocess.run', side_effect=subprocess.TimeoutExpired(['worker'], 110)
        ):
            result = app.test_cli_runner().invoke(args=['automation-tick'])
        self.assertNotEqual(result.exit_code, 0)
        row = db.session.get(AutomationRun, ident)
        self.assertEqual(row.status, 'failed')
        self.assertIn('prazo', row.error)
