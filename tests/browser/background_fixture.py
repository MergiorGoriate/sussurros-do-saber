"""Synthetic articles for background checks; isolated SQLite only."""
import json, os, sys, uuid
from pathlib import Path
if not os.environ.get('DATABASE_URL','').startswith('sqlite:'):
    raise RuntimeError('Article background browser fixtures require isolated SQLite')
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app import app
from models import db, Article, Author, Category, utcnow
with app.app_context():
    token=uuid.uuid4().hex
    author=Author(name='Autor de demonstração',slug='background-'+token)
    category=Category.query.first()
    if not category:
        category=Category(name='Ciência de demonstração',slug='background-'+token);db.session.add(category)
    db.session.add(author);db.session.flush()
    text='''[capitular] A ciência procura explicar o mundo com observações verificáveis. Esta página serve apenas para validar a apresentação de conteúdos.

## Métodos e resultados

Leia a [fonte de demonstração](https://example.org/estudo) e a nota[^1].

> Os resultados devem ser interpretados à luz das limitações do estudo.

| Condição | Resultado |
| --- | --- |
| Controlo | 12 |
| Ensaio | 18 |

    exemplo_de_codigo = 42

Um valor pode ser representado por `x = 42`.

[portrait: Símbolo do portal|Legenda da figura de demonstração.|Crédito de demonstração](http://127.0.0.1:5000/static/img/favicon.png)

[^1]: Nota com [ligação verificável](https://example.org/fonte).
'''
    records=[]
    for variant,state in [('draft','draft'),('default','published'),('aged_paper','published')]:
        a=Article(title='Como interpretamos os resultados científicos',slug='background-'+variant+'-'+token,
                  author_id=author.id,category_id=category.id,summary='Uma apresentação editorial legível de conceitos, métodos, resultados e limitações.',
                  body=text,references='1. Fonte de demonstração: [Estudo](https://example.org/estudo).',
                  status=state,background='aged_paper' if variant=='aged_paper' else 'default',published_at=utcnow() if state=='published' else None)
        db.session.add(a);records.append(a)
    db.session.commit()
    print(json.dumps(dict(draft_id=records[0].id,draft_slug=records[0].slug,default_slug=records[1].slug,paper_slug=records[2].slug)))
