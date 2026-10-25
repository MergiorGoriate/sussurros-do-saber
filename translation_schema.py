from models import db
import translation_models
import dissemination_video


def upgrade_translations(connection):
    names = {'content_translation', 'translation_version', 'translation_job', 'translation_event',
             'translation_quota', 'translation_worker', 'interface_translation', 'interface_batch','dissemination_video'}
    for table in db.metadata.sorted_tables:
        if table.name in names:
            table.create(connection, checkfirst=True)
