"""Additive commercial upgrade. Existing plans and contract snapshots are preserved."""
from sqlalchemy import inspect, text
from models import db
import premium_models


def upgrade_commercial_schema(connection):
    inspector = inspect(connection)
    if 'tier' not in {c['name'] for c in inspector.get_columns('premium_plan')}:
        connection.exec_driver_sql("ALTER TABLE premium_plan ADD COLUMN tier VARCHAR(8) NOT NULL DEFAULT 'legacy'")
    if 'course_limit' not in {c['name'] for c in inspect(connection).get_columns('premium_plan')}:
        connection.exec_driver_sql('ALTER TABLE premium_plan ADD COLUMN course_limit INTEGER')
    connection.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS premium_product_identity ON premium_plan (tier, interval, currency) WHERE tier IN ('pro','max')")
    names = ('premium_access_history','premium_enrollment','premium_service_request')
    db.metadata.create_all(connection,tables=[db.metadata.tables[n] for n in names],checkfirst=True)
    connection.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS premium_request_open ON premium_service_request (owner_id, kind, COALESCE(order_id,''), COALESCE(content_id,0)) WHERE state IN ('pending','review','approved')")
    for tier,label in (('pro','Pró'),('max','Max')):
        for interval,period in (('monthly','Mensal'),('annual','Anual')):
            if not connection.scalar(text('SELECT id FROM premium_plan WHERE tier=:tier AND interval=:period AND currency=\'MZN\''),{'tier':tier,'period':interval}):
                connection.execute(premium_models.PremiumPlan.__table__.insert().values(
                    tier=tier,name=label+' '+period,interval=interval,price_minor=0,currency='MZN',
                    description='',benefits=[],active=False,version=1))
    # A prior saved progress row is evidence of access, not of course completion.
    connection.exec_driver_sql('INSERT INTO premium_access_history (owner_id, content_id, first_access_at) '
        'SELECT p.owner_id, p.content_id, p.updated_at FROM premium_progress p WHERE NOT EXISTS '
        '(SELECT 1 FROM premium_access_history h WHERE h.owner_id=p.owner_id AND h.content_id=p.content_id)')
