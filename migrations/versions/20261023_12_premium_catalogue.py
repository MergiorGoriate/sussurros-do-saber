"""Configurable benefits and public catalogue categories; preserve all existing records."""
from alembic import op
from premium_catalogue_schema import upgrade_catalogue_schema
revision = '20261023_12'
down_revision = '20261023_11'
branch_labels = None
depends_on = None


def upgrade():
    upgrade_catalogue_schema(op.get_bind())


def downgrade():
    raise RuntimeError('Retain configured benefits and categories; revert application code without dropping data.')
