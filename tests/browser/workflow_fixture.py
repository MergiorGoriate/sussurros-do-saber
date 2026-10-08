"""Synthetic editorial article for browser UI checks; never imported by application routes."""
import json,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from app import app
from models import db,Article,Author,Category,utcnow
from governance_models import TeamMember,ArticleWorkflow
with app.app_context():
    token=uuid.uuid4().hex
    author=Author(name='Autor editorial de teste',slug='workflow-'+token)
    category=Category.query.first()
    if not category:
        category=Category(name='Teste editorial',slug='workflow-'+token)
        db.session.add(category)
    member=TeamMember(author=author,name=author.name,status='active',accepted_at=utcnow())
    db.session.add_all([author,member]);db.session.flush()
    article=Article(title='Artigo isolado para validar o fluxo editorial',slug='workflow-'+token,author_id=author.id,category_id=category.id,summary='Resumo científico de teste para a interface editorial.',body='Conteúdo científico de teste. '*30,status='draft')
    db.session.add(article);db.session.flush()
    db.session.add(ArticleWorkflow(article_id=article.id,owner_id=member.id,stage='draft'))
    db.session.commit()
    print(json.dumps({'article_id':article.id}))
