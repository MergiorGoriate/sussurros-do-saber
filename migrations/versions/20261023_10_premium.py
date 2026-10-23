"""Separate Premium learning products from permanently open scientific articles."""
from alembic import op
from premium_schema import upgrade_premium_schema

revision = '20261023_10'
down_revision = '20261022_09'
branch_labels = None
depends_on = None


def upgrade():
    upgrade_premium_schema(op.get_bind())


def downgrade():
    raise RuntimeError('Premium preserves subscription/audit history. Restore the previous application without dropping these tables.')
