"""Add independent PT/EN science news versions without changing articles."""
from alembic import op

from news_models import NewsStory, NewsVersion

revision = '20261122_21'
down_revision = '20261102_20'
branch_labels = None
depends_on = None


def upgrade():
    NewsStory.__table__.create(op.get_bind(), checkfirst=True)
    NewsVersion.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('A remoção das tabelas de notícias exige exportação e confirmação editorial.')
