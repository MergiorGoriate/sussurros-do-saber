"""Populate news only in the isolated browser-test SQLite database."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
if not os.environ.get('DATABASE_URL', '').startswith('sqlite:'):
    raise RuntimeError('News fixtures require isolated SQLite.')

from app import app
from models import Author, Category, db, utcnow
from news_models import NewsStory, NewsVersion


with app.app_context():
    title = 'Investigação de ensaio no telemóvel'
    item = NewsVersion.query.filter_by(language='pt', slug='ensaio-noticia-movel').first()
    if item is None:
        story = NewsStory()
        db.session.add(story)
        db.session.flush()
        item = NewsVersion(
            story_id=story.id, language='pt', slug='ensaio-noticia-movel', title=title,
            summary='Resumo sintético para validar o percurso móvel.',
            body='Texto de ensaio para validação do portal.',
            author=Author.query.first(), category=Category.query.filter_by(name='Saúde').one(),
            sources=[{'label': 'Publicação primária de ensaio', 'url': 'https://example.org/primary-source'}],
            status='published', published_at=utcnow(),
        )
        db.session.add(item)
        db.session.commit()
    print(json.dumps({'title': item.title, 'theme': item.category.slug}))
