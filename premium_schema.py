"""Additive Premium schema installation; never touches articles or journals."""
from sqlalchemy import select, func
from models import db
from premium_models import PremiumPlan, PremiumSubscription, PremiumContent, PremiumAudit


def upgrade_premium_schema(connection):
    tables = [model.__table__ for model in (PremiumPlan, PremiumSubscription, PremiumContent, PremiumAudit)]
    db.metadata.create_all(connection, tables=tables, checkfirst=True)
    from premium_catalogue_schema import upgrade_catalogue_schema
    upgrade_catalogue_schema(connection)
    upgrade_learning_schema(connection)
    if not connection.scalar(select(func.count()).select_from(PremiumPlan.__table__)):
        connection.execute(PremiumPlan.__table__.insert(), [
            dict(name='Premium Mensal', interval='monthly', price_minor=0, currency='MZN',
                 description='Acesso à biblioteca Premium durante o período atribuído.', active=False, version=1),
            dict(name='Premium Anual', interval='annual', price_minor=0, currency='MZN',
                 description='Acesso à biblioteca Premium durante o período atribuído.', active=False, version=1),
        ])


def upgrade_learning_schema(connection):
    import premium_models
    names = ('premium_resource','premium_file','premium_lesson','premium_progress','premium_event',
             'premium_registration','premium_collection_item','premium_certificate','premium_setting',
             'premium_staff','premium_plan_terms','premium_category','premium_usage')
    db.metadata.create_all(connection, tables=[db.metadata.tables[name] for name in names], checkfirst=True)

