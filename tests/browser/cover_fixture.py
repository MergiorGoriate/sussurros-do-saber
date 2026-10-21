"""Synthetic cover assets: URLs are intercepted by browser tests, never uploaded."""
import os, sys, uuid, json
from pathlib import Path
if not os.environ.get('DATABASE_URL','').startswith('sqlite:'):
    raise RuntimeError('Cover browser fixtures require isolated SQLite')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app import app
from models import Article, Author, Category, db, utcnow
with app.app_context():
    token=uuid.uuid4().hex
    author=Author(name='Autor de capas de demonstração',slug='cover-'+token)
    category=Category.query.first()
    if not category:
        category=Category(name='Ciência de demonstração',slug='cover-'+token);db.session.add(category)
    db.session.add(author);db.session.flush()
    result={}
    for mode in ['image','video_animated','video_controls','external','draft']:
        video='https://res.cloudinary.com/'+os.getenv('CLOUDINARY_CLOUD_NAME','cover-fixture')+'/video/upload/v1/fixture.webm'
        a=Article(title='A ciência em movimento: capa de demonstração',slug='cover-'+mode+'-'+token,
                  summary='Resumo de demonstração para validar capas, leitura e acessibilidade.',body='## Resultados e limites\n\n'+'Conteúdo científico de demonstração. '*30,
                  author_id=author.id,category_id=category.id,image='https://example.org/cover-poster.svg',
                  cover_mode='image' if mode=='draft' else ('video_controls' if mode=='external' else mode),
                  cover_video='https://youtu.be/dQw4w9WgXcQ' if mode=='external' else video,
                  featured=os.getenv('COVER_HERO_ANIMATED')=='1' and mode=='video_animated',
                  status='draft' if mode=='draft' else 'published',published_at=None if mode=='draft' else utcnow(),
                  background='aged_paper' if mode=='video_animated' else 'default')
        db.session.add(a);db.session.flush();result[mode]={'id':a.id,'slug':a.slug}
    db.session.commit();print(json.dumps(result))
