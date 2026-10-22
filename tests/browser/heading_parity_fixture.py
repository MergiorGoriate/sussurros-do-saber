"""Disposable records for heading preview/publication parity checks."""
import json
import os
import sys
import uuid
from pathlib import Path
if not os.environ.get('DATABASE_URL', '').startswith('sqlite:') or os.environ.get('FLASK_ENV', '').lower() == 'production':
    raise RuntimeError('Heading parity fixtures require isolated SQLite outside production')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import app
from models import Article, Author, Category, db, utcnow

with app.app_context():
    token = uuid.uuid4().hex
    author = Author(name='Autor de teste de cabeçalhos', slug='headings-' + token)
    category = Category.query.first()
    if category is None:
        category = Category(name='Teste de cabeçalhos', slug='headings-' + token)
        db.session.add(category)
    db.session.add(author)
    db.session.flush()
    title = 'Hierarquia de títulos num artigo de teste'
    body = '# ' + title + '\n\n## Introdução\n\nTexto de teste.\n\n### Contexto\n\n#### Critérios de selecção\n\n##### Detalhes\n\n###### Último nível\n\n```python\n# Código literal\n## Não é uma secção\n```\n\n`### Código em linha`\n\n\\# Texto literal\n\n| A | B |\n|---|---|\n| 1 | 2 |\n'
    records = []
    for state in ['draft', 'published']:
        item = Article(title=title, slug='headings-' + state + '-' + token,
                       author_id=author.id, category_id=category.id,
                       summary='Resumo isolado para testar a hierarquia dos cabeçalhos.',
                       body=body, status=state, published_at=utcnow() if state == 'published' else None)
        db.session.add(item)
        records.append(item)
    db.session.commit()
    print(json.dumps(dict(article_id=records[0].id, slug=records[1].slug, title=title, body=body)))
