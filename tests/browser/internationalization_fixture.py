"""Reviewed synthetic translation for isolated browser tests; no provider calls."""
import os
import sys
import json
import secrets
from pathlib import Path
if not os.getenv('DATABASE_URL','').startswith('sqlite:') or os.getenv('FLASK_ENV')=='production' or os.getenv('RENDER')=='true':
    raise RuntimeError('Internationalization fixtures require isolated SQLite outside production')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app import app
from models import db,Article,Author,Category,utcnow
from translation_models import ContentTranslation
from translation_service import source,add_version
with app.app_context():
    token=secrets.token_hex(5)
    article=Article(title='Luz e plantas '+token,slug='translated-browser-'+token,
        summary='As plantas utilizam luz.',body='## Método\nAs plantas utilizam luz.',
        references='Referência sintética de teste.',keywords='plantas',status='published',
        author_rel=Author.query.first(),category_rel=Category.query.first())
    db.session.add(article);db.session.flush()
    item=ContentTranslation(kind='article',source_id=article.id);db.session.add(item);db.session.flush()
    original=source('article',article.id)
    translated=dict(original,title='Light and plants '+token,summary='Plants use light.',body='## Method\nPlants use light.',keywords='plants')
    add_version(item,original,translated,dict(ready=True,faithful=True,issues=[]))
    item.state='published';item.published_version=1;item.approved_version=1;item.reviewed_at=utcnow()
    db.session.commit()
    print(json.dumps(dict(slug=article.slug,title=translated['title'],portuguese=article.title)))
