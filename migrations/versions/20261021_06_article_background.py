"""Add the editorial background without changing existing article content."""
from alembic import op
import sqlalchemy as sa

revision = '20261021_06'
down_revision = '20261020_05'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # Also supports installations already upgraded by the existing startup path.
    columns = {column['name'] for column in sa.inspect(bind).get_columns('article')}
    if 'background' not in columns:
        op.add_column('article', sa.Column('background', sa.String(20), nullable=False, server_default='default'))


def downgrade():
    raise RuntimeError('Preserve editorial preferences: restore a verified backup instead.')
