"""Isolated unpublished records for responsive editor regression tests."""
import json, sys, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import app
from models import db, Article, Author, Category, Journal
with app.app_context():
    token = uuid.uuid4().hex
    author = Author(name="Autor de teste responsivo", slug="responsive-" + token)
    category = Category.query.first()
    if not category:
        category = Category(name="Teste responsivo", slug="responsive-" + token)
        db.session.add(category)
    db.session.add(author)
    db.session.flush()
    body = "## Conteúdo de teste\n\n" + "https://example.org/" + "segmento" * 40 + "\n\n| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |"
    article = Article(title="Artigo para edição responsiva", slug="responsive-" + token,
                      author_id=author.id, category_id=category.id, status="draft",
                      summary="Resumo isolado para testar o formulário de edição.", body=body)
    journal = Journal(title="Revista para edição responsiva", slug="responsive-" + token,
                      field="Ciência", description="Revista isolada para testar o formulário de edição.",
                      content_markdown=body, published=False)
    db.session.add_all([article, journal])
    db.session.commit()
    print(json.dumps({"article_id": article.id, "journal_id": journal.id}))
