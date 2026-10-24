"""Add saved editorial choices and an opt-in weekly newsletter plan."""
from alembic import op
from models import db
import submission_models

revision = '20261024_14'
down_revision = '20261023_13'
branch_labels = None
depends_on = None


def upgrade():
    db.metadata.tables['newsletter_plan'].create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Preserve newsletter planning and audit history when reverting code.')
