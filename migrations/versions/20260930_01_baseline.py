"""Baseline of the application schema as of 2026-09-30.
Existing databases are validated before being registered; data is preserved.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260930_01"
down_revision = None
branch_labels = None
depends_on = None

EXPECTED_COLUMNS = {'admin_user': ['active', 'created_at', 'display_name', 'email', 'id', 'is_superadmin', 'last_login_at', 'password_hash', 'recovery_code_hashes', 'totp_secret', 'two_factor_enabled', 'username'], 'author': ['academic_background', 'active', 'bio', 'created_at', 'display_order', 'editorial_experience', 'email', 'google_scholar', 'headline', 'id', 'institution', 'interests', 'name', 'orcid', 'photo', 'projects', 'publications', 'researchgate', 'role', 'slug'], 'category': ['id', 'name', 'slug'], 'contact_message': ['created_at', 'email', 'id', 'message', 'name', 'read', 'subject'], 'journal': ['abbreviation', 'cover_alt', 'cover_image', 'created_at', 'current_issue', 'description', 'field', 'frequency', 'guidelines', 'id', 'issn', 'published', 'slug', 'title', 'updated_at'], 'subscriber': ['active', 'created_at', 'email', 'id'], 'article': ['author_id', 'body', 'category_id', 'created_at', 'doi', 'featured', 'id', 'image', 'keywords', 'published_at', 'read_minutes', 'references', 'scheduled_at', 'slug', 'status', 'summary', 'title', 'updated_at'], 'comment': ['approved', 'article_id', 'body', 'created_at', 'email', 'id', 'name']}

EXPECTED_TYPES = {
    'admin_user': {'id': sa.Integer(), 'username': sa.String(length=60), 'display_name': sa.String(length=120), 'email': sa.String(length=180), 'password_hash': sa.String(length=300), 'is_superadmin': sa.Boolean(), 'active': sa.Boolean(), 'created_at': sa.DateTime(), 'last_login_at': sa.DateTime(), 'two_factor_enabled': sa.Boolean(), 'totp_secret': sa.String(length=64), 'recovery_code_hashes': sa.Text()},
    'author': {'id': sa.Integer(), 'name': sa.String(length=120), 'slug': sa.String(length=160), 'email': sa.String(length=180), 'role': sa.String(length=140), 'headline': sa.String(length=220), 'academic_background': sa.Text(), 'institution': sa.String(length=220), 'bio': sa.Text(), 'interests': sa.Text(), 'projects': sa.Text(), 'orcid': sa.String(length=19), 'google_scholar': sa.String(length=600), 'researchgate': sa.String(length=600), 'publications': sa.Text(), 'editorial_experience': sa.Text(), 'photo': sa.String(length=600), 'display_order': sa.Integer(), 'active': sa.Boolean(), 'created_at': sa.DateTime()},
    'category': {'id': sa.Integer(), 'name': sa.String(length=80), 'slug': sa.String(length=90)},
    'contact_message': {'id': sa.Integer(), 'name': sa.String(length=120), 'email': sa.String(length=180), 'subject': sa.String(length=220), 'message': sa.Text(), 'read': sa.Boolean(), 'created_at': sa.DateTime()},
    'journal': {'id': sa.Integer(), 'title': sa.String(length=180), 'slug': sa.String(length=200), 'abbreviation': sa.String(length=30), 'field': sa.String(length=140), 'description': sa.Text(), 'issn': sa.String(length=9), 'frequency': sa.String(length=80), 'current_issue': sa.String(length=120), 'guidelines': sa.Text(), 'cover_image': sa.String(length=600), 'cover_alt': sa.String(length=300), 'published': sa.Boolean(), 'created_at': sa.DateTime(), 'updated_at': sa.DateTime()},
    'subscriber': {'id': sa.Integer(), 'email': sa.String(length=180), 'active': sa.Boolean(), 'created_at': sa.DateTime()},
    'article': {'id': sa.Integer(), 'title': sa.String(length=240), 'slug': sa.String(length=260), 'summary': sa.Text(), 'body': sa.Text(), 'references': sa.Text(), 'keywords': sa.String(length=500), 'doi': sa.String(length=180), 'image': sa.String(length=600), 'status': sa.String(length=20), 'read_minutes': sa.Integer(), 'featured': sa.Boolean(), 'published_at': sa.DateTime(), 'scheduled_at': sa.DateTime(), 'created_at': sa.DateTime(), 'updated_at': sa.DateTime(), 'author_id': sa.Integer(), 'category_id': sa.Integer()},
    'comment': {'id': sa.Integer(), 'article_id': sa.Integer(), 'name': sa.String(length=80), 'email': sa.String(length=254), 'body': sa.Text(), 'approved': sa.Boolean(), 'created_at': sa.DateTime()},
}

EXPECTED_FOREIGN_KEYS = {'admin_user': [], 'author': [], 'category': [], 'contact_message': [], 'journal': [], 'subscriber': [], 'article': [(('author_id',), ('author.id',)), (('category_id',), ('category.id',))], 'comment': [(('article_id',), ('article.id',))]}

def upgrade():
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())
    if existing.intersection(EXPECTED_COLUMNS):
        missing_tables = set(EXPECTED_COLUMNS) - existing
        mismatch = [name for name, columns in EXPECTED_COLUMNS.items()
                    if name in existing and sorted(c["name"] for c in inspector.get_columns(name)) != columns]
        for name, expected_types in EXPECTED_TYPES.items():
            if name not in existing:
                continue
            columns = {c["name"]: c for c in inspector.get_columns(name)}
            for column, expected_type in expected_types.items():
                if column in columns and str(columns[column]["type"].compile(dialect=op.get_bind().dialect)).upper() != str(expected_type.compile(dialect=op.get_bind().dialect)).upper():
                    mismatch.append(name)
            actual_fks = sorted((tuple(fk["constrained_columns"]), tuple(fk["referred_table"] + "." + c for c in fk["referred_columns"]))
                                for fk in inspector.get_foreign_keys(name))
            if actual_fks != EXPECTED_FOREIGN_KEYS[name]:
                mismatch.append(name)
        if missing_tables or mismatch:
            raise RuntimeError("Baseline refused: reconcile existing schema in staging first")
        return
# ### commands auto generated by Alembic - please adjust! ###
    op.create_table('admin_user',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=60), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=180), nullable=True),
    sa.Column('password_hash', sa.String(length=300), nullable=False),
    sa.Column('is_superadmin', sa.Boolean(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(), nullable=True),
    sa.Column('two_factor_enabled', sa.Boolean(), nullable=False),
    sa.Column('totp_secret', sa.String(length=64), nullable=True),
    sa.Column('recovery_code_hashes', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_admin_user_username'), 'admin_user', ['username'], unique=True)
    op.create_table('author',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('slug', sa.String(length=160), nullable=False),
    sa.Column('email', sa.String(length=180), nullable=True),
    sa.Column('role', sa.String(length=140), nullable=True),
    sa.Column('headline', sa.String(length=220), nullable=True),
    sa.Column('academic_background', sa.Text(), nullable=True),
    sa.Column('institution', sa.String(length=220), nullable=True),
    sa.Column('bio', sa.Text(), nullable=True),
    sa.Column('interests', sa.Text(), nullable=True),
    sa.Column('projects', sa.Text(), nullable=True),
    sa.Column('orcid', sa.String(length=19), nullable=True),
    sa.Column('google_scholar', sa.String(length=600), nullable=True),
    sa.Column('researchgate', sa.String(length=600), nullable=True),
    sa.Column('publications', sa.Text(), nullable=True),
    sa.Column('editorial_experience', sa.Text(), nullable=True),
    sa.Column('photo', sa.String(length=600), nullable=True),
    sa.Column('display_order', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_author_slug'), 'author', ['slug'], unique=True)
    op.create_table('category',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('slug', sa.String(length=90), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('contact_message',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=180), nullable=False),
    sa.Column('subject', sa.String(length=220), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('read', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('journal',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=180), nullable=False),
    sa.Column('slug', sa.String(length=200), nullable=False),
    sa.Column('abbreviation', sa.String(length=30), nullable=True),
    sa.Column('field', sa.String(length=140), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('issn', sa.String(length=9), nullable=True),
    sa.Column('frequency', sa.String(length=80), nullable=True),
    sa.Column('current_issue', sa.String(length=120), nullable=True),
    sa.Column('guidelines', sa.Text(), nullable=True),
    sa.Column('cover_image', sa.String(length=600), nullable=True),
    sa.Column('cover_alt', sa.String(length=300), nullable=True),
    sa.Column('published', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_journal_slug'), 'journal', ['slug'], unique=True)
    op.create_table('subscriber',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(length=180), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('article',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=240), nullable=False),
    sa.Column('slug', sa.String(length=260), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('references', sa.Text(), nullable=False),
    sa.Column('keywords', sa.String(length=500), nullable=True),
    sa.Column('doi', sa.String(length=180), nullable=True),
    sa.Column('image', sa.String(length=600), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('read_minutes', sa.Integer(), nullable=False),
    sa.Column('featured', sa.Boolean(), nullable=False),
    sa.Column('published_at', sa.DateTime(), nullable=True),
    sa.Column('scheduled_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('author_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['author.id'], ),
    sa.ForeignKeyConstraint(['category_id'], ['category.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('comment',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('article_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=80), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('approved', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['article_id'], ['article.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_comment_approved'), 'comment', ['approved'], unique=False)
    op.create_index(op.f('ix_comment_article_id'), 'comment', ['article_id'], unique=False)
    op.create_index(op.f('ix_comment_created_at'), 'comment', ['created_at'], unique=False)
    # ### end Alembic commands ###

def downgrade():
    raise RuntimeError("Baseline downgrade would remove application data and is intentionally disabled")
