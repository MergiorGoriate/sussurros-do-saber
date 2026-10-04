"""Synthetic accounts and an open journal used only by browser tests."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import app
from models import Journal, db
from submission_models import Researcher, SubmissionSetting
from werkzeug.security import generate_password_hash
with app.app_context():
    journal = Journal.query.filter_by(slug='submission-browser-fixture').first()
    if not journal:
        journal = Journal(title='Revista de submissão de teste',slug='submission-browser-fixture',field='Biologia',description='Revista exclusiva para testes de submissão científica.')
        db.session.add(journal);db.session.flush()
    setting = db.session.get(SubmissionSetting,journal.id) or SubmissionSetting(journal_id=journal.id)
    setting.enabled=True;setting.article_types='Artigo original\nArtigo de revisão';setting.main_formats='txt,docx';setting.editorial_email='editorial@example.org';db.session.add(setting)
    for number in (1,2):
        email=f'author-browser-{number}@example.org'
        account=Researcher.query.filter_by(email=email).first()
        if not account:
            account=Researcher(email=email,name=f'Autor de teste {number}',token_nonce=f'browser-fixture-{number}',password_hash=generate_password_hash('browser-author-password-123'),verified=True)
            db.session.add(account)
    db.session.commit()
