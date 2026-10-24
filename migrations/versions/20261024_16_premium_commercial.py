"""Pró/Max identities, subscriber access history, enrolments and service requests."""
from alembic import op
from premium_commercial_schema import upgrade_commercial_schema
revision = '20261024_16'
down_revision = '20261024_15'
branch_labels = None
depends_on = None


def upgrade():
    upgrade_commercial_schema(op.get_bind())


def downgrade():
    raise RuntimeError('Preserve commercial identities and subscriber records when reverting code.')
