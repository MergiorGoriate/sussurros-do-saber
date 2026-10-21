"""Add cover presentation while preserving existing image and controlled video covers."""
from alembic import op
import sqlalchemy as sa
revision = '20261021_07'
down_revision = '20261021_06'
branch_labels = None
depends_on = None


def upgrade():
    columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('article')}
    if 'cover_mode' not in columns:
        op.add_column('article', sa.Column('cover_mode', sa.String(24), nullable=False, server_default='auto'))


def downgrade():
    raise RuntimeError('Preserve cover preferences: restore a verified backup instead.')
