import importlib.util
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Text, JSON, DateTime, select
from jinja2 import Environment, DictLoader

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('article_seo', ROOT / 'scripts/article_seo.py')
seo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seo)


class SEOMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine('sqlite:///' + str(Path(self.temp.name) / 'db.sqlite'))
        meta = MetaData()
        self.articles = Table('article', meta, Column('id', Integer, primary_key=True),
            *[Column(k, Text) for k in set(seo.FIELDS) - {'read_minutes', 'featured'}],
            Column('read_minutes', Integer), Column('featured', Integer), Column('slug', String),
            Column('status', String), Column('updated_at', DateTime))
        self.history = Table('article_revision', meta, Column('id', Integer, primary_key=True),
            Column('article_id', Integer), Column('number', Integer), Column('snapshot', JSON),
            Column('actor_id', Integer), Column('actor_name', String), Column('reason', String), Column('created_at', DateTime))
        Table('governance_audit', meta, Column('id', Integer, primary_key=True),
            Column('actor_id', Integer), Column('actor_name', String), Column('action', String),
            Column('entity', String), Column('entity_id', Integer), Column('detail', String), Column('created_at', DateTime))
        meta.create_all(self.engine)
        row = {k: '' for k in seo.FIELDS}
        row.update(id=1, title='Título anterior', summary='Resumo anterior', body='# Repetição\n\n### Secção',
                   read_minutes=5, featured=0, slug='endereco-original', status='published', updated_at=datetime(2026, 1, 1))
        with self.engine.begin() as conn:
            conn.execute(self.articles.insert().values(**row))
        self.before = self.row()
        self.plan = {'articles': [{'id': 1, 'fingerprint': seo.digest(self.before),
                     'after': {'title': 'Como as células obtêm energia',
                               'summary': 'O artigo descreve os processos celulares de obtenção de energia e a sua relação com o metabolismo.'},
                     'reviewed': True, 'reason': 'Exemplo sintético para teste.'}]}

    def row(self):
        with self.engine.connect() as conn:
            return dict(conn.execute(select(self.articles)).mappings().one())

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def test_apply_repeat_restore_and_history(self):
        import json
        backup = Path(self.temp.name) / 'backup.json'
        self.assertEqual(seo.change(self.engine, self.plan, backup, 'Teste')['changed'], 1)
        self.assertEqual(seo.change(self.engine, self.plan, backup, 'Teste')['changed'], 0)
        after = self.row()
        for k in self.before.keys() - {'title', 'summary', 'updated_at'}:
            self.assertEqual(after[k], self.before[k])
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        recovery = json.loads(backup.read_text())
        seo.change(self.engine, recovery, Path(self.temp.name) / 'undo.json', 'Teste', restore=True)
        self.assertEqual(self.row()['title'], self.before['title'])
        with self.engine.connect() as conn:
            self.assertEqual(len(conn.execute(select(self.history)).all()), 3)

    def test_stale_plan_rejected_without_backup(self):
        with self.engine.begin() as conn:
            conn.execute(self.articles.update().values(body='Alteração concorrente'))
        with self.assertRaises(ValueError):
            seo.change(self.engine, self.plan, Path(self.temp.name) / 'backup.json', 'Teste')
        self.assertFalse((Path(self.temp.name) / 'backup.json').exists())

    def test_no_overwriting_backup(self):
        backup = Path(self.temp.name) / 'backup.json'
        backup.write_text('preservar')
        with self.assertRaises(FileExistsError):
            seo.change(self.engine, self.plan, backup, 'Teste')
        self.assertEqual(self.row(), self.before)

    def test_protected_fields_and_limits(self):
        for values in ({'slug': 'novo'}, {'title': 'x' * 70}, {'summary': 'curto'}):
            self.plan['articles'][0]['after'] = values
            with self.assertRaises(ValueError):
                seo.change(self.engine, self.plan, Path(self.temp.name) / 'backup.json', 'Teste')

    def test_audit_flags_headings_and_counts(self):
        report = seo.audit([self.before])['articles'][0]
        self.assertTrue(any('H1 no corpo' in s for s in report['issues']))
        self.assertTrue(any('Salto H1 → H3' in s for s in report['issues']))
        self.assertEqual(report['title_chars'], len(self.before['title']))

    def test_actual_template_title_and_description(self):
        env = Environment(loader=DictLoader({'base.html': '<title>{% block title %}{% endblock %}</title><meta name="description" content="{% block meta_description %}{% endblock %}">',
            'partials/social_icons.html': '{% macro x_icon() %}{% endmacro %}'}), autoescape=True)
        # Other blocks are not rendered by this minimal base; all filters must compile.
        for name in ('social_image', 'image_variant', 'image_srcset', 'safe_image_url', 'article_cover_video', 'markdown'):
            env.filters[name] = lambda value, *args: value
        template = env.from_string((ROOT / 'templates/article.html').read_text())
        for n in (20, 48, 49, 69):
            title = 'Á' * n
            rendered = template.render(article={'title': title, 'summary': 'Descrição & rigor'})
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(rendered, 'html.parser')
            self.assertEqual(soup.title.string, seo.page_title(title))
            self.assertLess(len(soup.title.string), 70)
            self.assertEqual(len(soup.select('meta[name="description"]')), 1)
            self.assertEqual(soup.select_one('meta')['content'], 'Descrição & rigor')


if __name__ == '__main__':
    unittest.main()
