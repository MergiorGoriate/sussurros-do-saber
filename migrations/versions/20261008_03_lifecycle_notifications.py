"""Preserve archived records and recipient-owned internal notices."""
from alembic import op
import sqlalchemy as sa
revision = '20261008_03'
down_revision = '20261007_02'
branch_labels = None
depends_on = None

def upgrade():
    inspector = sa.inspect(op.get_bind())
    for table, column in [('team_member','removed_at'),('staff_document','removed_at'),('manuscript','removed_at'),('staff_notice','removed_at'),('staff_notice','researcher_id'),('staff_notice','resource_type'),('staff_notice','resource_id')]:
        existing = {c['name'] for c in sa.inspect(op.get_bind()).get_columns(table)}
        if column not in existing:
            kind = sa.DateTime() if column == 'removed_at' else sa.String(40) if column == 'resource_type' else sa.Integer()
            with op.batch_alter_table(table) as batch:
                batch.add_column(sa.Column(column, kind, nullable=True))
                if column == 'researcher_id':
                    batch.create_foreign_key('fk_notice_researcher', 'researcher', ['researcher_id'], ['id'])
                if column in {'removed_at','researcher_id'}:
                    batch.create_index('ix_'+table+'_'+column, [column])
    with op.batch_alter_table('staff_notice') as batch:
        batch.alter_column('admin_id', existing_type=sa.Integer(), nullable=True)
    from governance_models import AuditReport
    AuditReport.__table__.create(op.get_bind(), checkfirst=True)
    existing_indexes={i['name'] for i in sa.inspect(op.get_bind()).get_indexes('staff_notice')}
    for name,recipient in [('ix_notice_inbox_admin','admin_id'),('ix_notice_inbox_researcher','researcher_id')]:
        if name not in existing_indexes:op.create_index(name,'staff_notice',[recipient,'removed_at','created_at','id'])

def downgrade():
    raise RuntimeError('Restore a verified backup: archived history and notifications must be preserved.')
