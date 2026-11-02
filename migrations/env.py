"""Standalone migration entrypoint; never imports the app or seeds content."""
import os

from alembic import context
from sqlalchemy import create_engine, pool, text
from models import db
import submission_models
import governance_models
import premium_models
import billing_models
import scientific_metrics_models
import dissemination_models
import translation_models
import indexnow_service

url = os.environ.get("DATABASE_URL", "")
if not url:
    raise RuntimeError("DATABASE_URL is required for schema migrations")
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

if context.is_offline_mode():
    raise RuntimeError("Baseline validation requires an online database connection")

engine = create_engine(url, poolclass=pool.NullPool)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=db.metadata, compare_type=True)
    with context.begin_transaction():
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(1936028275)"))
        context.run_migrations()




