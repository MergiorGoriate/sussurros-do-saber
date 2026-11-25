"""Add the science video catalogue and anonymous playback records."""
from alembic import op

from video_models import ScienceVideo, VideoPlayback

revision = '20261125_22'
down_revision = '20261122_21'
branch_labels = None
depends_on = None


def upgrade():
    ScienceVideo.__table__.create(op.get_bind(), checkfirst=True)
    VideoPlayback.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Exporte os vídeos e as estatísticas antes de remover estas tabelas.')
