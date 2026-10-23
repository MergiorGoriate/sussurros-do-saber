"""Idempotent additive catalogue upgrade for existing Premium installations."""
from sqlalchemy import inspect


def upgrade_catalogue_schema(connection):
    for table, column, definition in (
        ('premium_plan', 'benefits', "JSON NOT NULL DEFAULT '[]'"),
        ('premium_content', 'category', "VARCHAR(80) NOT NULL DEFAULT ''"),
    ):
        inspector = inspect(connection)
        if inspector.has_table(table) and column not in {c['name'] for c in inspector.get_columns(table)}:
            connection.exec_driver_sql(f'ALTER TABLE {table} ADD COLUMN {column} {definition}')
