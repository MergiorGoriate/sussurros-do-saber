"""Persist IndexNow notifications in the editorial transaction."""
from alembic import op
from indexnow_service import IndexNowNotification

revision = '20261102_20'
down_revision = '20261026_19'
branch_labels = None
depends_on = None


def upgrade():
    IndexNowNotification.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    IndexNowNotification.__table__.drop(op.get_bind(), checkfirst=True)
