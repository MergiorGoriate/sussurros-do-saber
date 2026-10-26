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
                connection.execute(text('CREATE TABLE article (id INTEGER PRIMARY KEY)'))
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

    def test_article_background_upgrade_preserves_old_content_and_preferences(self):
        import sqlalchemy as sa
        import governance_models, submission_models
        with tempfile.TemporaryDirectory() as directory:
            url='sqlite:///'+str(Path(directory)/'background.db')
            engine=create_engine(url)
            metadata=sa.MetaData()
            for table in db.metadata.sorted_tables:table.to_metadata(metadata)
            metadata.tables['article']._columns.remove(metadata.tables['article'].c.background)
            metadata.create_all(engine)
            with engine.begin() as connection:
                connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)'))
                connection.execute(text("INSERT INTO alembic_version VALUES ('20261020_05')"))
                from datetime import datetime
                connection.execute(metadata.tables['author'].insert().values(id=1,name='Autor',slug='autor'))
                connection.execute(metadata.tables['category'].insert().values(id=1,name='Biologia',slug='biologia'))
                connection.execute(metadata.tables['article'].insert().values(id=1,title='Conteúdo anterior',slug='anterior',summary='Resumo preservado',body='Texto preservado',author_id=1,category_id=1,status='published',created_at=datetime(2026,1,1),updated_at=datetime(2026,1,1)))
            self.run_migration(url)
            with engine.begin() as connection:
                self.assertEqual(connection.execute(text('SELECT title,body,background FROM article')).one(),('Conteúdo anterior','Texto preservado','default'))
                self.assertFalse(next(c for c in inspect(connection).get_columns('article') if c['name']=='background')['nullable'])
                connection.execute(text("UPDATE article SET background='aged_paper'"))
            self.run_migration(url)
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text('SELECT background FROM article')).scalar(),'aged_paper')
            engine.dispose()

    def test_cover_mode_upgrade_preserves_images_and_existing_videos(self):
        from models import Article
        with tempfile.TemporaryDirectory() as directory:
            url='sqlite:///'+str(Path(directory)/'covers.db')
            engine=create_engine(url)
            with engine.begin() as connection:
                connection.execute(text('CREATE TABLE article (id INTEGER PRIMARY KEY, image VARCHAR(600), cover_video VARCHAR(1000), body TEXT)'))
                connection.execute(text("INSERT INTO article VALUES (1,'https://example.org/static.jpg','','Imagem anterior'),(2,'https://example.org/poster.jpg','https://example.org/legacy.mp4','Vídeo anterior')"))
                connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)'))
                connection.execute(text("INSERT INTO alembic_version VALUES ('20261021_06')"))
            self.run_migration(url)
            with engine.begin() as connection:
                rows=connection.execute(text('SELECT image,cover_video,body,cover_mode FROM article ORDER BY id')).all()
                self.assertEqual(rows[0],('https://example.org/static.jpg','','Imagem anterior','auto'))
                self.assertEqual(rows[1],('https://example.org/poster.jpg','https://example.org/legacy.mp4','Vídeo anterior','auto'))
                self.assertEqual([Article(cover_mode=r[3],cover_video=r[1]).cover_format for r in rows],['image','video_controls'])
                connection.execute(text("UPDATE article SET cover_mode='video_animated' WHERE id=2"))
            self.run_migration(url)
            with engine.connect() as connection:
                self.assertEqual(connection.execute(text('SELECT cover_mode FROM article WHERE id=2')).scalar(),'video_animated')
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
                self.assertTrue({"admin_user", "author", "category", "journal", "article", "comment", "subscriber", "contact_message", "newsletter_plan", "translation_limit_setting", "translation_limit_change"}.issubset(inspect(connection).get_table_names()))
                self.assertEqual(connection.execute(text("SELECT version_num FROM alembic_version")).scalar(), "20261026_19")
                columns={column['name']:column for column in inspect(connection).get_columns('article_workflow')}
                self.assertTrue(columns['owner_id']['nullable'])
                self.assertFalse(columns['primary_owned']['nullable'])
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
