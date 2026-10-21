"""Persist coordinated outbox limits, campaigns, claims and attempt history."""
from alembic import op
from mail_schema import upgrade_mail_schema

revision='20261021_08'
down_revision='20261021_07'
branch_labels=None
depends_on=None


def upgrade():
    upgrade_mail_schema(op.get_bind())


def downgrade():
    raise RuntimeError('Preserve campaigns and SMTP acceptance history. Restore a verified backup with the matching old code; destructive downgrade is refused.')
