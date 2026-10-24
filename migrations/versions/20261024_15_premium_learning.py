"""Private resources, learning, events and Premium-only administration."""
from alembic import op
from premium_schema import upgrade_learning_schema

revision = '20261024_15'
down_revision = '20261024_14'
branch_labels = None
depends_on = None


def upgrade():
    upgrade_learning_schema(op.get_bind())


def downgrade():
    raise RuntimeError('Preserve private resources and learning records when reverting the application.')
