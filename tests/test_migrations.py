import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from models import db


class MigrationTests(unittest.TestCase):
    def test_html_email_upgrade_preserves_existing_sent_and_pending_notifications(self):
        with tempfile.TemporaryDirectory() as directory:
            url='sqlite:///'+str(Path(directory)/'mail.db')
            engine=create_engine(url)
            with engine.begin() as connection:
                connection.execute(text('CREATE TABLE editorial_notification (id INTEGER PRIMARY KEY, recipient VARCHAR(254), subject VARCHAR(300), body TEXT, sent_at DATETIME, attempts INTEGER)'))
                connection.execute(text("INSERT INTO editorial_notification VALUES (1,'test@example.test','Pendente','Texto original',NULL,0),(2,'test@example.test','Enviada','Texto enviado','2026-10-19 08:00:00',1)"))
                connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)'))
                connection.execute(text("INSERT INTO alembic_version VALUES ('20261018_04')"))
            self.run_migration(url);self.run_migration(url)
            with engine.connect() as connection:
                column=next(c for c in inspect(connection).get_columns('editorial_notification') if c['name']=='html_body')
                self.assertTrue(column['nullable'])
                rows=connection.execute(text('SELECT body,sent_at,html_body FROM editorial_notification ORDER BY id')).all()
                self.assertEqual(rows[0],('Texto original',None,None))
                self.assertEqual(rows[1],('Texto enviado','2026-10-19 08:00:00',None))
            engine.dispose()

    def run_migration(self, url):
        with patch.dict(os.environ, {"DATABASE_URL": url}):
            command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")

    def test_empty_database_is_created_and_upgrade_is_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            url = "sqlite:///" + str(Path(directory) / "new.db")
            self.run_migration(url)
            self.run_migration(url)
            engine = create_engine(url)
            with engine.connect() as connection:
                self.assertTrue({"admin_user", "author", "category", "journal", "article", "comment", "subscriber", "contact_message"}.issubset(inspect(connection).get_table_names()))
                self.assertEqual(connection.execute(text("SELECT version_num FROM alembic_version")).scalar(), "20261020_05")
            engine.dispose()

    def test_existing_schema_and_content_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            url = "sqlite:///" + str(Path(directory) / "existing.db")
            engine = create_engine(url)
            db.metadata.create_all(engine)
            with engine.begin() as connection:
                connection.execute(text("INSERT INTO category (id, name, slug) VALUES (7, 'Biologia', 'biologia')"))
            self.run_migration(url)
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text("SELECT name FROM category WHERE id=7")).scalar(), "Biologia")
            engine.dispose()

    def test_partial_schema_is_rejected_without_removing_content(self):
        with tempfile.TemporaryDirectory() as directory:
            url = "sqlite:///" + str(Path(directory) / "partial.db")
            engine = create_engine(url)
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE category (id integer PRIMARY KEY, name text)"))
                connection.execute(text("INSERT INTO category VALUES (9, 'Preservar')"))
            with self.assertRaisesRegex(RuntimeError, "Baseline refused"):
                self.run_migration(url)
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text("SELECT name FROM category WHERE id=9")).scalar(), "Preservar")
            engine.dispose()


    def test_upgrade_real_previous_shape_preserves_notices_document_payload_and_acceptance(self):
        import sqlalchemy as sa
        import governance_models
        import submission_models
        with tempfile.TemporaryDirectory() as directory:
            url='sqlite:///'+str(Path(directory)/'previous.db')
            engine=create_engine(url)
            metadata=sa.MetaData()
            for table in db.metadata.sorted_tables:
                if table.name=='audit_report':continue
                table.to_metadata(metadata)
            removable={'team_member':['removed_at'],'staff_document':['removed_at'],'manuscript':['removed_at'],'staff_notice':['removed_at','researcher_id','resource_type','resource_id']}
            for name,columns in removable.items():
                table=metadata.tables[name]
                for column_name in columns:
                    column=table.c[column_name]
                    for constraint in list(table.constraints):
                        if isinstance(constraint,sa.ForeignKeyConstraint) and column_name in constraint.columns:
                            table.constraints.remove(constraint)
                    for index in list(table.indexes):
                        if column_name in index.columns:table.indexes.remove(index)
                    table._columns.remove(column)
            metadata.tables['staff_notice'].c.admin_id.nullable=False
            metadata.create_all(engine)
            with engine.begin() as conn:
                conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
                conn.execute(sa.text("INSERT INTO alembic_version VALUES ('20261007_02')"))
                conn.execute(metadata.tables['admin_user'].insert().values(id=1,username='fixture-admin',display_name='Fixture',password_hash='unused',active=True,is_superadmin=False,two_factor_enabled=False,security_version=1,governance_managed=True))
                conn.execute(metadata.tables['team_member'].insert().values(id=1,admin_id=1,name='Fixture',email='fixture@example.org',status='active'))
                from datetime import datetime
                accepted=datetime(2026,1,2,3,4,5)
                conn.execute(metadata.tables['staff_document'].insert().values(id=1,member_id=1,title='Termo preservado',body='Versão original',payload=b'original',accepted_at=accepted,accepted_by=1))
                conn.execute(metadata.tables['staff_notice'].insert().values(id=1,admin_id=1,source_key='legacy-source',subject='Aviso original',body='Preservar'))
            self.run_migration(url);self.run_migration(url)
            with engine.connect() as conn:
                self.assertEqual(conn.execute(sa.text('SELECT subject FROM staff_notice WHERE id=1')).scalar(),'Aviso original')
                self.assertEqual(conn.execute(sa.text('SELECT payload FROM staff_document WHERE id=1')).scalar(),b'original')
                self.assertTrue(str(conn.execute(sa.text('SELECT accepted_at FROM staff_document WHERE id=1')).scalar()).startswith('2026-01-02 03:04:05'))
                self.assertIn('audit_report',sa.inspect(conn).get_table_names())
                self.assertTrue(sa.inspect(conn).get_columns('staff_notice')[1] is not None)
                self.assertTrue(next(c['nullable'] for c in sa.inspect(conn).get_columns('staff_notice') if c['name']=='admin_id'))
            engine.dispose()


