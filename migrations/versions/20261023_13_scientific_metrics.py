"""Add scientific metrics without changing editorial records."""
from alembic import op
from scientific_metrics_schema import upgrade_scientific_metrics
revision = '20261023_13'
down_revision = '20261023_12'
branch_labels = None
depends_on = None


def upgrade():
    upgrade_scientific_metrics(op.get_bind())


def downgrade():
    raise RuntimeError('Retain collected metrics. Revert application code without dropping history.')
