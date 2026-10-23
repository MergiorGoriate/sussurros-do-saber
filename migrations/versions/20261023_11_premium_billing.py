"""Auditable billing without changing public scientific content or complimentary grants."""
from alembic import op
from billing_schema import upgrade_billing_schema
revision = '20261023_11'
down_revision = '20261023_10'
branch_labels = None
depends_on = None


def upgrade():
    upgrade_billing_schema(op.get_bind())


def downgrade():
    raise RuntimeError('Financial history is retained. Revert application code without dropping billing tables.')
