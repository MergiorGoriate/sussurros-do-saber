from models import db
import dissemination_models


def upgrade_dissemination_schema(connection):
    for table in db.metadata.sorted_tables:
        if table.name.startswith('dissemination_'):
            table.create(connection, checkfirst=True)
