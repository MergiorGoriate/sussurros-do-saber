"""Add staff governance and collaboration without replacing existing records."""
from alembic import op
from models import db
import submission_models
import governance_models
import sqlalchemy as sa
revision='20261007_02'
down_revision='20260930_01'
branch_labels=None
depends_on=None


def upgrade():
    connection=op.get_bind()
    # Create dependencies on installations predating the submission module.
    core={'admin_user','author','category','journal','article','comment','subscriber','contact_message'}
    # The baseline predates current scientific fields. Add missing scalar columns
    # with bounded empty defaults, preserving every existing row.
    inspector=sa.inspect(connection)
    for name in core:
        columns={c['name'] for c in inspector.get_columns(name)}
        for column in db.metadata.tables[name].columns:
            if column.name in columns:
                continue
            default=None
            if not column.nullable:
                if isinstance(column.type,sa.Boolean): default=sa.false()
                elif isinstance(column.type,sa.Integer): default=sa.text('1')
                elif isinstance(column.type,(sa.String,sa.Text)): default=sa.text("''")
                else: raise RuntimeError('Reconcile required column '+name+'.'+column.name)
            op.add_column(name,sa.Column(column.name,column.type,nullable=column.nullable,server_default=default))
    for table in db.metadata.sorted_tables:
        if table.name not in core:
            table.create(connection,checkfirst=True)
    roles=governance_models.TeamRole.__table__
    from governance import DEFAULT_ROLES
    for code,name,purpose,permissions in DEFAULT_ROLES:
        exists=connection.execute(roles.select().where(roles.c.code==code)).first()
        if not exists:
            connection.execute(roles.insert().values(code=code,name=name,purpose=purpose,duties=purpose,
                         limits='Acesso limitado às permissões e ao âmbito do mandato.',permissions=permissions))


def downgrade():
    raise RuntimeError('Rollback refused: preserve staff documents, decisions and audit history. Restore a verified backup instead.')
