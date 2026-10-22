"""Disposable articles for heading persistence, preview and mobile layout."""
import json
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import app
from models import db, Article, Author, Category, utcnow

with app.app_context():
    token = uuid.uuid4().hex
    author = Author(name='Autor de teste de cabeçalhos', slug='headings-' + token)
    category = Category.query.first()
    if not category:
        category = Category(name='Teste de cabeçalhos', slug='headings-' + token)
        db.session.add(category)
    db.session.add(author)
    db.session.flush()
    body = '\n\n'.join('#' * n + ' Secção ' + str(n) for n in range(1, 7))
    body += '\n\n```markdown\n# Código literal\n###### Código literal\n```\n\n\\# Texto literal'
    body += '\n\n## Secção 2\n\n[Ir à secção](#sec-seccao-6)'
    body += '\n\n#### ' + 'Cabeçalhoextensosemespaços' * 8
    body += '\n\nParágrafo com **negrito**, *itálico* e $E=mc^2$.'
    draft = Article(title='Teste dos níveis de cabeçalhos', slug='headings-draft-' + token,
                    author_id=author.id, category_id=category.id, summary='Resumo para verificar a hierarquia de títulos.',
                    body=body, status='draft')
    public = Article(title=draft.title, slug='headings-public-' + token,
                     author_id=author.id, category_id=category.id, summary=draft.summary,
                     body=body, status='published', published_at=utcnow())
    db.session.add_all([draft, public])
    db.session.commit()
    print(json.dumps(dict(article_id=draft.id, slug=public.slug, body=body)))
