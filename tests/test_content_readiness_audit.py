import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from sqlalchemy import create_engine, text
from content_audit import DEMO_ARTICLE_BODY, assess_article
from scripts.audit_published_content import inspect_database


class ContentReadinessTests(unittest.TestCase):
    def test_demo_and_unresolved_notes_are_separate_from_reference_detection(self):
        row = {'slug': 'demo', 'title': 'Example', 'body': DEMO_ARTICLE_BODY, 'references': '', 'image': 'https://example.org/cover.jpg'}
        result = assess_article(row)
        self.assertIn('demo_body_published', result['flags'])
        self.assertIn('references_not_identified', result['flags'])
        row.update(body='Conteúdo revisto.', references='Referência. Nota bibliográfica: confirmar os autores completos no registo editorial antes da publicação formal.')
        result = assess_article(row)
        self.assertNotIn('references_not_identified', result['flags'])
        self.assertIn('unresolved_editorial_note', result['flags'])
        self.assertFalse(result['image_rights_verified'])

    def test_inspection_excludes_drafts_and_preserves_database(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'fixture.db'
            engine = create_engine('sqlite:///' + str(path))
            with engine.begin() as conn:
                conn.execute(text('CREATE TABLE article (slug TEXT, title TEXT, body TEXT, "references" TEXT, image TEXT, status TEXT)'))
                conn.execute(text('INSERT INTO article VALUES (:slug,:title,:body,:refs,:image,:status)'), [
                    dict(slug='public', title='Public', body=DEMO_ARTICLE_BODY, refs='', image='', status='published'),
                    dict(slug='private', title='Private', body='Secret draft', refs='', image='', status='draft')])
            before = path.read_bytes()
            report = inspect_database('sqlite:///' + str(path))
            self.assertEqual(report['published_articles'], 1)
            self.assertNotIn('Secret draft', json.dumps(report))
            self.assertIn('demo_body_published', report['articles'][0]['flags'])
            self.assertEqual(path.read_bytes(), before)
            engine.dispose()

    def test_production_bootstrap_keeps_demo_content_private(self):
        with tempfile.TemporaryDirectory() as folder:
            env = dict(os.environ, FLASK_ENV='production', RENDER='false',
                       DATABASE_URL='sqlite:///' + str(Path(folder) / 'production-fixture.db'),
                       SECRET_KEY='isolated-content-audit-test-secret', RATELIMIT_STORAGE_URI='memory://',
                       ADMIN_TOTP_SECRET='JBSWY3DPEHPK3PXP', AUTO_SCHEMA_UPGRADE='true')
            code = """
from app import app, seed_database
from models import Article, Journal, db
with app.app_context():
    assert Article.query.count() > 0
    assert Article.public_query().count() == 0
    assert Journal.query.filter_by(published=True).count() == 0
    article = Article.query.first()
    article.status = 'published'
    article.body = 'Texto revisto pelo editor, que não pode ser sobrescrito.'
    db.session.commit()
    seed_database()
    assert Article.public_query().count() == 1
    assert Article.public_query().first().body == 'Texto revisto pelo editor, que não pode ser sobrescrito.'
"""
            result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr[-1000:])
