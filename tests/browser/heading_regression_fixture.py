"""Synthetic article and journal used only by heading browser tests."""
import json
import sys
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import app
from models import Article, Author, Category, Journal, db, utcnow

with app.app_context():
    token = uuid.uuid4().hex
    author = Author(name='Autor de teste dos cabeçalhos', slug='headings-' + token)
    category = Category.query.first()
    db.session.add(author)
    if not category:
        category = Category(name='Teste dos cabeçalhos', slug='headings-' + token)
        db.session.add(category)
    db.session.flush()
    body = '\n\n'.join('#' * n + ' Nível ' + str(n) for n in range(1, 7))
    body += '\n\n```markdown\n# Literal\n###### Literal\n```\n\n\\# Escapado\n\n`## Inline`\n\n## Nível 2\n\n[Secção](#sec-nivel-2)'
    body += '\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nTexto com **ênfase**.'
    article = Article(title='Título principal de teste', slug='headings-' + token,
                      author_id=author.id, category_id=category.id, status='draft',
                      summary='Resumo científico para verificar todos os níveis de cabeçalhos.', body=body)
    public = Article(title=article.title, slug='headings-public-' + token,
                     author_id=author.id, category_id=category.id, status='published',
                     published_at=utcnow(), summary=article.summary, body=body)
    journal = Journal(title='Revista de teste de cabeçalhos', slug='headings-' + token,
                      field='Ciência', description='Teste isolado do índice existente.',
                      content_markdown='# Artigo científico\n\n' + '\n\n'.join('#' * n + ' Secção ' + str(n) for n in range(2, 7)),
                      published=True)
    db.session.add_all([article, public, journal])
    db.session.commit()
    print(json.dumps(dict(article_id=article.id, slug=public.slug, journal_slug=journal.slug, body=body)))
