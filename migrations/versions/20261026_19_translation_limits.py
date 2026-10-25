"""Allow the primary administrator to manage the daily translation limit."""
from alembic import op
from translation_schema import upgrade_translation_limits

revision = '20261026_19'
down_revision = '20261025_18'
branch_labels = None
depends_on = None


def upgrade():
    upgrade_translation_limits(op.get_bind())


def downgrade():
    raise RuntimeError('Preserve translation settings and their audit history.')
