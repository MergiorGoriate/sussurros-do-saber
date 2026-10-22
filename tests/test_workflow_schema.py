import unittest
import sqlalchemy as sa
from workflow_schema import upgrade_workflow_schema


class WorkflowSchemaTests(unittest.TestCase):
    def test_upgrade_preserves_history_and_is_idempotent(self):
        engine = sa.create_engine('sqlite://')
        with engine.begin() as connection:
            connection.exec_driver_sql('CREATE TABLE team_member (id INTEGER PRIMARY KEY)')
            connection.exec_driver_sql('CREATE TABLE article (id INTEGER PRIMARY KEY)')
            connection.exec_driver_sql('CREATE TABLE article_workflow (article_id INTEGER PRIMARY KEY REFERENCES article(id), owner_id INTEGER NOT NULL REFERENCES team_member(id), stage TEXT NOT NULL, reviewed_at TEXT)')
            connection.exec_driver_sql('INSERT INTO team_member VALUES (1)')
            connection.exec_driver_sql('INSERT INTO article VALUES (1), (2)')
            connection.exec_driver_sql("INSERT INTO article_workflow VALUES (1, 1, 'review', '2026-10-22')")
            upgrade_workflow_schema(connection)
            upgrade_workflow_schema(connection)
            row = connection.exec_driver_sql('SELECT owner_id,stage,reviewed_at,primary_owned FROM article_workflow WHERE article_id=1').one()
            self.assertEqual(tuple(row), (1, 'review', '2026-10-22', 0))
            connection.exec_driver_sql("INSERT INTO article_workflow (article_id,owner_id,stage,primary_owned) VALUES (2,NULL,'draft',1)")
            self.assertTrue(next(c for c in sa.inspect(connection).get_columns('article_workflow') if c['name']=='owner_id')['nullable'])
            self.assertEqual(len(sa.inspect(connection).get_foreign_keys('article_workflow')), 2)
