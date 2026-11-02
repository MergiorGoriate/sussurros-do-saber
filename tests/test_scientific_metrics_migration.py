"""Upgrade actual pre-metrics table shapes without altering published content."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


class ScientificMetricsMigrationTests(unittest.TestCase):
    def test_upgrade_preserves_content_and_does_not_fabricate_events(self):
        config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
        with tempfile.TemporaryDirectory() as folder:
            url='sqlite:///'+str(Path(folder)/'metrics.db')
            with patch.dict(os.environ,{'DATABASE_URL':url}):
                command.upgrade(config,'20261023_12')
                engine=create_engine(url)
                with engine.begin() as connection:
                    for table in ['scientific_metric_source','scientific_metric_day','scientific_metric_receipt','scientific_metric_start','scientific_metric_provider']:
                        if inspect(connection).has_table(table):connection.exec_driver_sql('DROP TABLE '+table)
                    connection.execute(text("INSERT INTO journal (id,title,slug,field,description,published,created_at,updated_at,content_markdown) VALUES (731,'Preservado','artigo-preservado','Ciência','Resumo',1,'2026-10-23','2026-10-23','## Texto preservado')"))
                command.upgrade(config,'head');command.upgrade(config,'head')
                with engine.begin() as connection:
                    self.assertEqual(connection.scalar(text('SELECT content_markdown FROM journal WHERE id=731')),'## Texto preservado')
                    self.assertEqual(connection.scalar(text('SELECT count(*) FROM scientific_metric_day')),0)
                    self.assertEqual(connection.scalar(text('SELECT count(*) FROM scientific_metric_source')),0)
                    self.assertEqual(connection.scalar(text('SELECT count(*) FROM scientific_metric_start WHERE journal_id=731')),1)
                    self.assertEqual(connection.scalar(text('SELECT version_num FROM alembic_version')),'20261102_20')
                engine.dispose()

