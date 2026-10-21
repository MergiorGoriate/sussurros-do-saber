"""Real upgrade of the old outbox without deleting history or resending legacy work."""
import tempfile
import unittest
from pathlib import Path
import sqlalchemy as sa
from models import db
from mail_schema import upgrade_mail_schema


class MailMigrationTests(unittest.TestCase):
    def test_legacy_duplicates_and_uncertain_attempts_are_preserved_without_requeue(self):
        with tempfile.TemporaryDirectory() as directory:
            engine=sa.create_engine('sqlite:///'+str(Path(directory)/'old.db'))
            with engine.begin() as conn:
                conn.execute(sa.text('CREATE TABLE subscriber (id INTEGER PRIMARY KEY, email VARCHAR(180))'))
                conn.execute(sa.text("INSERT INTO subscriber VALUES (1,'a@example.test'),(2,'b@example.test')"))
                conn.execute(sa.text('CREATE TABLE editorial_notification (id INTEGER PRIMARY KEY, recipient VARCHAR(254), subject VARCHAR(300), body TEXT, sent_at DATETIME, attempts INTEGER, last_error VARCHAR(120))'))
                sql=sa.text('INSERT INTO editorial_notification VALUES (:id,:email,:subject,:body,:sent,:attempts,\'\')')
                subject='Sussurros do Saber — Boletim 2026-W42'
                for ident,email,sent,attempts in [(1,'a@example.test','2026-10-21 10:00:00',1),(2,'a@example.test',None,0),(3,'b@example.test',None,1)]:
                    conn.execute(sql,dict(id=ident,email=email,subject=subject,body='Texto original '+str(ident),sent=sent,attempts=attempts))
                upgrade_mail_schema(conn);upgrade_mail_schema(conn)
                rows=conn.execute(sa.text('SELECT id,body,sent_at,status,campaign_id,subscriber_id FROM editorial_notification ORDER BY id')).all()
                self.assertEqual(len(rows),3)
                self.assertEqual(rows[0][1:4],('Texto original 1','2026-10-21 10:00:00','accepted'))
                self.assertEqual(rows[1][3],'cancelled');self.assertIsNone(rows[1][4])
                self.assertEqual(rows[2][3],'uncertain');self.assertEqual(rows[2][5],2)
                self.assertEqual(conn.execute(sa.text('SELECT status FROM newsletter_campaign')).scalar(),'prepared')
                self.assertEqual(conn.execute(sa.text('SELECT count(*) FROM mail_delivery_attempt')).scalar(),1)
                self.assertEqual(conn.execute(sa.text('SELECT hourly_limit FROM mail_delivery_policy')).scalar(),100)
            engine.dispose()
