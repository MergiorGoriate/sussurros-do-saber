"""Real PostgreSQL concurrency and foreign keys, isolated CI database only."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class ScientificMetricsPostgresTests(unittest.TestCase):
    @unittest.skipUnless(os.getenv('SCIENTIFIC_METRICS_TEST_DATABASE_URL'), 'Requires isolated PostgreSQL fixture')
    def test_concurrent_receipts_and_editorial_delete(self):
        url=os.environ['SCIENTIFIC_METRICS_TEST_DATABASE_URL']
        self.assertTrue(url.startswith(('postgresql://','postgresql+psycopg://')))
        script='''
from concurrent.futures import ThreadPoolExecutor
import secrets
from app import app
from models import db, Journal
from extensions import limiter
from scientific_metrics_collection import record
from scientific_metrics_models import ScientificMetricDay,ScientificMetricSource
from flask import Response
limiter.enabled=False
with app.app_context():
    j=Journal(title='Synthetic metrics concurrency',slug='metrics-pg-'+secrets.token_hex(8),field='Test',description='CI only',content_markdown='Scientific text',published=True)
    db.session.add(j);db.session.commit();ident=j.id

def collect(kind):
    with app.app_context(),app.test_request_context('/fixture',headers={'User-Agent':'Mozilla/5.0 metrics-reader'},environ_overrides={'REMOTE_ADDR':'192.0.2.44'}):
        j=db.session.get(Journal,ident)
        record(j,kind,Response('fixture',mimetype='application/pdf' if kind=='download' else 'text/html'))

try:
    with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(collect,['view']*16+['download']*16))
    with app.app_context():
        row=ScientificMetricDay.query.filter_by(journal_id=ident).one()
        assert (row.views,row.downloads)==(1,1),(row.views,row.downloads)
        db.session.add(ScientificMetricSource(journal_id=ident,source='crossref',doi='10.9999/fixture',state='unavailable'));db.session.commit()
        db.session.delete(db.session.get(Journal,ident));db.session.commit()
        assert ScientificMetricDay.query.filter_by(journal_id=ident).count()==0
        assert ScientificMetricSource.query.filter_by(journal_id=ident).count()==0
finally:
    with app.app_context():
        db.session.rollback()
        if db.session.get(Journal,ident):db.session.delete(db.session.get(Journal,ident));db.session.commit()
'''
        env=dict(os.environ,DATABASE_URL=url)
        result=subprocess.run([sys.executable,'-c',script],cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+'\n'+result.stderr)
