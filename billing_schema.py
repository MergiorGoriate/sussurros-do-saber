"""Additive billing schema and database-enforced immutable journal/events."""
from sqlalchemy import inspect
from models import db
from billing_models import BillingAccount, BillingOrder, BillingGrant, BillingJournal, BillingEvent, BillingRisk


def upgrade_billing_schema(connection):
    inspector=inspect(connection)
    if inspector.has_table('premium_content') and 'open_access_required' not in {c['name'] for c in inspector.get_columns('premium_content')}:
        connection.exec_driver_sql('ALTER TABLE premium_content ADD COLUMN open_access_required BOOLEAN NOT NULL DEFAULT FALSE')
    db.metadata.create_all(connection, tables=[m.__table__ for m in
        (BillingAccount, BillingOrder, BillingGrant, BillingJournal, BillingEvent, BillingRisk)], checkfirst=True)
    for table in ('billing_journal','billing_event'):
        if connection.dialect.name == 'sqlite':
            for operation in ('UPDATE','DELETE'):
                connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'Immutable financial record'); END")
        elif connection.dialect.name == 'postgresql':
            connection.exec_driver_sql("CREATE OR REPLACE FUNCTION billing_reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Immutable financial record'; END; $$")
            connection.exec_driver_sql(f'DROP TRIGGER IF EXISTS {table}_immutable ON {table}')
            connection.exec_driver_sql(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION billing_reject_mutation()')
        else:
            raise RuntimeError('Billing supports SQLite and PostgreSQL only.')
