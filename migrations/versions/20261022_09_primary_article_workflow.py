"""Allow primary administrators to manage authorship without staff membership."""
from alembic import op
from workflow_schema import upgrade_workflow_schema

revision = '20261022_09'
down_revision = '20261021_08'
branch_labels = None
depends_on = None


def upgrade():
    upgrade_workflow_schema(op.get_bind())


def downgrade():
    raise RuntimeError('Preserve workflows without staff ownership; restore a verified backup with matching code.')
