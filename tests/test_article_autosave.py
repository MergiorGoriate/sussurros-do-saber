"""Draft autosave permissions, version checks and recoverable history."""
import unittest
from unittest.mock import patch
import test_article_history as history
from models import db
from governance_models import ArticleRevision,ArticleWorkflow

class ArticleAutosaveTests(unittest.TestCase):
    setUp=history.ArticleHistoryTests.setUp
    tearDown=history.ArticleHistoryTests.tearDown
    member=history.ArticleHistoryTests.member
    article=history.ArticleHistoryTests.article
    signin=history.ArticleHistoryTests.signin
    post=history.ArticleHistoryTests.post

    def save(self,article,**extra):
        values={name:getattr(article,name) or '' for name in ('title','summary','body','references','keywords','doi')}
        values.update(read_minutes=article.read_minutes,version_token=article.updated_at.isoformat())
        values.update(extra)
        return self.post(f'/admin/artigos/{article.id}/rascunho',**values)

    def test_autosave_records_actor_and_baseline_but_never_publishes_or_changes_metadata(self):
        owner=self.member();article=self.article(owner);self.signin(owner.admin)
        original=article.body;slug=article.slug;author=article.author_id
        response=self.save(article,body='Texto guardado automaticamente. '*8,status='published',author_id=self.primary.id)
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json['ok'])
        self.assertIn('no-store',response.headers['Cache-Control'])
        self.assertEqual(article.status,'draft');self.assertEqual(article.slug,slug);self.assertEqual(article.author_id,author)
        versions=ArticleRevision.query.filter_by(article_id=article.id).order_by(ArticleRevision.number).all()
        self.assertEqual(len(versions),2);self.assertEqual(versions[0].snapshot['body'],original)
        self.assertEqual(versions[-1].snapshot['body'],article.body)
        self.assertEqual(versions[-1].actor_id,owner.admin_id)
        self.assertIn('automática',versions[-1].reason)
        token=response.json['version_token']
        self.assertEqual(self.save(article).json['version_token'],token)
        self.assertEqual(ArticleRevision.query.filter_by(article_id=article.id).count(),2)
        self.assertEqual(self.client.get('/artigo/'+slug).status_code,404)

    def test_stale_or_missing_token_cannot_overwrite_another_session(self):
        owner=self.member();article=self.article(owner);self.signin(owner.admin)
        old=article.updated_at.isoformat()
        self.assertEqual(self.save(article,body='Alteração da primeira sessão. '*5).status_code,200)
        saved=article.body
        for token in [old,'']:
            response=self.save(article,body='Texto da segunda sessão.',version_token=token)
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json['code'],'conflict')
            self.assertEqual(article.body,saved)

    def test_compare_and_swap_failure_creates_no_partial_version(self):
        from flask_sqlalchemy.query import Query
        owner=self.member();article=self.article(owner);self.signin(owner.admin)
        original=article.body
        with patch.object(Query,'update',return_value=0):
            self.assertEqual(self.save(article,body='Uma alteração concorrente.').status_code,409)
        self.assertEqual(article.body,original)
        self.assertEqual(ArticleRevision.query.filter_by(article_id=article.id).count(),0)

    def test_reviewed_or_published_articles_and_advanced_workflows_are_not_autosaved(self):
        owner=self.member();article=self.article(owner);self.signin(self.primary)
        original=article.body
        for state in ['review','approved','scheduled','published']:
            article.status=state;db.session.commit()
            response=self.save(article,body='Não deve substituir o conteúdo.')
            self.assertEqual(response.status_code,409)
            self.assertEqual(article.body,original)
        article.status='draft';db.session.get(ArticleWorkflow,article.id).stage='approved';db.session.commit()
        self.assertEqual(self.save(article,body='Não deve contornar a aprovação.').status_code,409)

    def test_autosave_requires_scope_csrf_and_valid_fields(self):
        owner=self.member();other=self.member();article=self.article(owner);self.signin(other.admin)
        original=article.body
        self.assertEqual(self.save(article,body='Texto sem acesso.').status_code,404)
        self.signin(owner.admin)
        path=f'/admin/artigos/{article.id}/rascunho'
        self.assertEqual(self.client.post(path,data={}).status_code,400)
        self.assertEqual(self.client.get(path).status_code,405)
        for invalid in [dict(title='x'),dict(summary='curto'),dict(read_minutes=0),dict(doi='x'*181)]:
            self.assertEqual(self.save(article,**invalid).status_code,422)
        self.assertEqual(article.body,original)
        self.assertEqual(ArticleRevision.query.filter_by(article_id=article.id).count(),0)
        owner.appointments[0].active=False;db.session.commit();self.signin(owner.admin)
        self.assertIn(self.save(article,body='Texto após revogação.').status_code,(302,403))
        self.assertEqual(article.body,original)
