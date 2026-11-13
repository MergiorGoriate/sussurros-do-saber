"""Synthetic public/private publications for discovery tests, never production."""
import json
import os
import sys
import uuid
from pathlib import Path

if not os.environ.get('DATABASE_URL', '').startswith('sqlite:') or os.environ.get('FLASK_ENV') == 'production' or os.environ.get('RENDER', '').lower() == 'true':
    raise RuntimeError('Scientific search fixture requires isolated SQLite outside production')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app import app
from models import db, Journal, Article, Author, Category

with app.app_context():
    token = uuid.uuid4().hex
    doi = '10.12345/discovery.' + token
    journal = Journal(title='Revista de teste '+token, article_title='Investigação '+token,
        slug='search-'+token, field='Biologia', description='Pesquisa científica de teste',
        doi=doi, content_markdown='## Resultados\n\nConteúdo sintético para teste.',
        authors_data=json.dumps([{'name':'Coautora '+token,
            'orcid':'https://orcid.org/0000-0001-5109-3700','description':''}]), published=True)
    hidden = Journal(title=journal.title, slug='hidden-search-'+token,
        field='Biologia', description=journal.description, doi=doi, published=False)
    author = Author(name='Autor '+token, slug='search-author-'+token, role='Investigador', bio='Teste')
    category = Category(name='Categoria '+token, slug='search-category-'+token)
    db.session.add_all([author, category])
    db.session.flush()
    article = Article(title='Imunologia do cérebro '+token, slug='fuzzy-'+token,
        summary='Artigo para teste de pesquisa', body='Conteúdo sintético.',
        author_id=author.id, category_id=category.id, status='published')
    private = Article(title=article.title, slug='hidden-fuzzy-'+token,
        summary=article.summary, body=article.body,
        author_id=author.id, category_id=category.id, status='draft')
    db.session.add_all([journal, hidden, article, private])
    db.session.commit()
    print(json.dumps({'slug':journal.slug,'private_slug':hidden.slug,'doi':doi,
                     'author':'Coautora '+token, 'article_slug':article.slug,
                     'private_article_slug':private.slug, 'article_query':'imunlogia cerebro '+token}))

