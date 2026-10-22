"""Synthetic content shared by preview, save/reopen and public heading checks."""
import json
import os
import sys
import uuid
from pathlib import Path
if not os.environ.get('DATABASE_URL', '').startswith('sqlite:') or os.environ.get('FLASK_ENV', '').lower() == 'production':
    raise RuntimeError('Heading browser fixtures require isolated SQLite outside production')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import app
from models import db, Article, Author, Category, Journal, utcnow

with app.app_context():
    token = uuid.uuid4().hex
    author = Author(name='Autor de teste de títulos', slug='headings-' + token)
    category = Category.query.first()
    db.session.add(author)
    db.session.flush()
    body = '\n\n'.join('#' * n + f' Nível {n}' for n in range(1, 7))
    body += '\n\n## Métodos\n\n## Métodos\n\n```python\n# literal\n```\n\n\\# escapado\n\nTexto **forte** e $E=mc^2$.'
    values = dict(title='Artigo de teste de títulos', summary='Resumo isolado para testar os seis níveis de títulos.',
                  body=body, author_id=author.id, category_id=category.id)
    draft = Article(slug='headings-draft-' + token, status='draft', **values)
    public = Article(slug='headings-public-' + token, status='published', published_at=utcnow(), **values)
    journal = Journal(title='Revista de teste de títulos', slug='headings-journal-' + token,
                      field='Biologia', description='Revista isolada para testar o índice existente.',
                      content_markdown=body, published=True)
    db.session.add_all([draft, public, journal])
    db.session.commit()
    print(json.dumps(dict(article_id=draft.id, slug=public.slug, journal_slug=journal.slug, body=body)))
