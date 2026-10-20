"""Store an optional HTML snapshot alongside existing plain-text notifications."""
from alembic import op
import sqlalchemy as sa

revision = '20261020_05'
down_revision = '20261018_04'
branch_labels = None
depends_on = None


def upgrade():
    columns = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('editorial_notification')}
    if 'html_body' not in columns:
        op.add_column('editorial_notification', sa.Column('html_body', sa.Text(), nullable=True))


def downgrade():
    raise RuntimeError('Preserve queued email snapshots: restore a verified backup instead.')
