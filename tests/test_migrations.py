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
                self.assertEqual(connection.execute(text("SELECT version_num FROM alembic_version")).scalar(), "20260930_01")
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
