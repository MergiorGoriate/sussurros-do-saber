"""Synthetic verified readers; never runs against production."""
import json
import secrets
import sys
from datetime import timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import app
from models import Article, Author, Category, Journal, db, utcnow
from submission_models import Researcher
from reader_accounts import ReaderJournal
from werkzeug.security import generate_password_hash

with app.app_context():
    if db.engine.dialect.name != 'sqlite':
        raise RuntimeError('Browser fixtures require an isolated SQLite database')
    if len(sys.argv) > 1:
        journal = Journal.query.filter_by(slug=sys.argv[1]).one()
        row = ReaderJournal.query.filter_by(journal_id=journal.id, following=True).one()
        row.followed_at = utcnow() - timedelta(days=1)
        journal.updated_at = utcnow()
        db.session.commit()
    else:
        token = secrets.token_hex(8)
        account = Researcher(name='Leitor de auditoria', email=token+'@example.org',
            password_hash=generate_password_hash('audit-reader-password-123'),
            token_nonce=token, verified=True)
        article = Article(title='Artigo favorito '+token, slug='audit-article-'+token,
            summary='Artigo público para teste de favoritos.', body='Texto público do artigo.',
            status='published', author_id=Author.query.first().id, category_id=Category.query.first().id)
        journal = Journal(title='Revista de auditoria '+token, article_title='Artigo seguido '+token,
            slug='audit-journal-'+token, description='Conteúdo público do teste.', field='Biologia',
            published=True, content_markdown='# Artigo seguido '+token+'\n\n## Introdução\n\nTexto científico.')
        db.session.add_all([account, article, journal]); db.session.commit()
        print(json.dumps({'email': account.email, 'password': 'audit-reader-password-123',
            'article_id': article.id, 'article_slug': article.slug, 'article_title': article.title,
            'journal_slug': journal.slug, 'journal_title': journal.article_title}))
