"""Additive metrics installation, including coverage dates for existing content."""
from sqlalchemy import inspect, select
from models import db, Journal, utcnow
from scientific_metrics_models import ScientificMetricDay, ScientificMetricReceipt, ScientificMetricStart, ScientificMetricSource, ScientificMetricProvider


def upgrade_scientific_metrics(connection):
    tables = [m.__table__ for m in (ScientificMetricDay, ScientificMetricReceipt, ScientificMetricStart, ScientificMetricSource, ScientificMetricProvider)]
    db.metadata.create_all(connection, tables=tables, checkfirst=True)
    # Historical migration fixtures may contain only an earlier module's tables.
    # Do not create editorial records merely to establish metrics coverage.
    if not inspect(connection).has_table('journal'):
        return
    table = ScientificMetricStart.__table__
    now = utcnow()
    for ident in connection.scalars(select(Journal.id)):
        if not connection.scalar(select(table.c.journal_id).where(table.c.journal_id == ident)):
            connection.execute(table.insert().values(journal_id=ident, started_at=now))
