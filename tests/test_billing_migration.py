"""Upgrade an actual previous shape and verify immutable financial history."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine,text,inspect


class BillingMigrationTests(unittest.TestCase):
    def test_previous_head_upgrade_preserves_content_and_adds_immutability(self):
        config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
        with tempfile.TemporaryDirectory() as folder:
            url='sqlite:///'+str(Path(folder)/'billing.db')
            with patch.dict(os.environ,{'DATABASE_URL':url}):
                command.upgrade(config,'20261023_10')
                engine=create_engine(url)
                with engine.begin() as connection:
                    if 'open_access_required' in {c['name'] for c in inspect(connection).get_columns('premium_content')}:
                        connection.exec_driver_sql('ALTER TABLE premium_content DROP COLUMN open_access_required')
                    connection.execute(text("INSERT INTO premium_content (id,title,kind,summary,body,published,updated_at,version) VALUES (7,'Preservado','course','Resumo','Corpo preservado',0,'2026-10-23',1)"))
                command.upgrade(config,'head');command.upgrade(config,'head')
                with engine.begin() as connection:
                    self.assertEqual(connection.scalar(text('SELECT body FROM premium_content WHERE id=7')),'Corpo preservado')
                    self.assertEqual(connection.scalar(text('SELECT open_access_required FROM premium_content WHERE id=7')),0)
                    self.assertEqual(connection.scalar(text('SELECT version_num FROM alembic_version')),'20261024_16')
                    connection.execute(text("INSERT INTO billing_event (event_key,kind,object_ref,digest,created_at) VALUES ('fixture','test','ref','hash','2026-10-23')"))
                with engine.begin() as connection:
                    with self.assertRaises(Exception):connection.execute(text("DELETE FROM billing_event WHERE event_key='fixture'"))
                engine.dispose()

