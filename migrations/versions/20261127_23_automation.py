"""Add isolated automation persistence and disabled operator defaults."""
from alembic import op
from sqlalchemy import select
from automation.config import REGISTRY
from automation.models import AutomationAlert, AutomationDiscovery, AutomationOperator, AutomationRun

revision = '20261127_23'
down_revision = '20261125_22'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    for model in (AutomationOperator, AutomationRun, AutomationAlert, AutomationDiscovery):
        model.__table__.create(connection, checkfirst=True)
    table = AutomationOperator.__table__
    existing = set(connection.execute(select(table.c.code)).scalars())
    missing = [dict(code=code, enabled=False, interval_minutes=spec.interval, settings=spec.settings,
                    cursor={}, notify=False, retention_days=90)
               for code, spec in REGISTRY.items() if code not in existing]
    if missing:
        connection.execute(table.insert(), missing)


def downgrade():
    raise RuntimeError('Desactive o worker e conserve os dados de automação para eventual recuperação.')
