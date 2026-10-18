"""Preserve article content versions without changing existing content."""
from alembic import op
from governance_models import ArticleRevision
revision = '20261018_04'
down_revision = '20261008_03'
branch_labels = None
depends_on = None


def upgrade():
    ArticleRevision.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Preserve article history: restore a verified backup instead of deleting revisions.')
