"""Idempotent workflow upgrade shared by startup and Alembic."""
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def upgrade_workflow_schema(connection):
    if connection.dialect.name == 'postgresql':
        connection.execute(sa.text('SELECT pg_advisory_xact_lock(1936028275)'))
    inspector = sa.inspect(connection)
    if 'article_workflow' not in inspector.get_table_names():
        return
    columns = {c['name']: c for c in inspector.get_columns('article_workflow')}
    if 'primary_owned' not in columns or not columns['owner_id']['nullable']:
        op = Operations(MigrationContext.configure(connection))
        with op.batch_alter_table('article_workflow') as batch:
            if 'primary_owned' not in columns:
                batch.add_column(sa.Column('primary_owned', sa.Boolean(), nullable=False, server_default=sa.false()))
            if not columns['owner_id']['nullable']:
                batch.alter_column('owner_id', existing_type=sa.Integer(), nullable=True)
