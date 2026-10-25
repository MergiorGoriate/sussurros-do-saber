"""Add editorial translations without modifying source articles or journal PDFs."""
from alembic import op
from translation_schema import upgrade_translations
revision = '20261025_18'
down_revision = '20261025_17'
branch_labels = None
depends_on = None


def upgrade():
    upgrade_translations(op.get_bind())


def downgrade():
    raise RuntimeError('Preserve published translations and their editorial history.')
