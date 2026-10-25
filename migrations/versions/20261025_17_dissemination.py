"""Private scientific dissemination, approvals and asynchronous queue."""
from alembic import op
from dissemination_schema import upgrade_dissemination_schema
revision = '20261025_17'
down_revision = '20261024_16'
branch_labels = None
depends_on = None


def upgrade():
    upgrade_dissemination_schema(op.get_bind())


def downgrade():
    raise RuntimeError('Preserve dissemination decisions and version history.')
