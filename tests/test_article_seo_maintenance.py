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
        for name in ('social_image', 'image_variant', 'image_srcset', 'safe_image_url', 'article_cover_video', 'markdown', 'article_markdown'):
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

    def test_structure_preserves_prose_fences_and_repeats_without_changes(self):
        body = '# Título anterior\n\nTexto científico intacto.\n\n### Secção\n\n##### Parte\n\n```markdown\n# Código\n```\n'
        expected = '\nTexto científico intacto.\n\n## Secção\n\n### Parte\n\n```markdown\n# Código\n```\n'
        corrected = seo.structure_body(body, 'Título anterior')
        self.assertEqual(corrected, expected)
        self.assertEqual(seo.structure_body(corrected, 'Título anterior'), corrected)

    def test_ambiguous_bodies_stay_unchanged(self):
        for body in ('<h1>Título anterior</h1>\n### Parte',
                     'Título\n======\n### Parte', '<pre>\n# Exemplo\n</pre>'):
            self.assertEqual(seo.structure_body(body, 'Título anterior'), body)

    def test_structure_only_update_and_recovery_preserve_metadata(self):
        import json
        original = self.before['body']
        self.plan['articles'][0]['after'] = {'body': seo.structure_body(original, self.before['title'])}
        backup = Path(self.temp.name) / 'before.json'
        seo.change(self.engine, self.plan, backup, 'Teste')
        self.assertEqual(self.row()['summary'], self.before['summary'])
        seo.change(self.engine, json.loads(backup.read_text()), Path(self.temp.name) / 'undo.json', 'Teste', restore=True)
        self.assertEqual(self.row()['body'], original)

    def test_body_rewriting_and_unreviewed_plans_are_rejected(self):
        self.plan['articles'][0]['after'] = {'body': 'Prosa substituída.'}
        with self.assertRaises(ValueError):
            seo.change(self.engine, self.plan, Path(self.temp.name) / 'before.json', 'Teste')
        self.plan['articles'][0]['after'] = {'title': 'Título proposto'}
        for flag in (False, 'true', 1):
            self.plan['articles'][0]['reviewed'] = flag
            with self.assertRaises(ValueError):
                seo.change(self.engine, self.plan, Path(self.temp.name) / 'before.json', 'Teste')

    def test_editorial_plan_resolves_slug_and_rejects_changed_observations(self):
        proposal = {'articles': [{'slug': self.before['slug'], 'expected': {k: self.before[k] for k in ('title', 'summary')},
                     'after': {'title': 'Título novo'}, 'reason': 'Revisão editorial.'}]}
        result = seo.editorial_plan([self.before], proposal)
        self.assertEqual(result['articles'][0]['id'], self.before['id'])
        self.assertFalse(result['articles'][0]['reviewed'])
        self.assertEqual(result['articles'][0]['fingerprint'], seo.digest(self.before))
        proposal['articles'][0]['expected']['title'] = 'Desactualizado'
        with self.assertRaises(ValueError):
            seo.editorial_plan([self.before], proposal)

    def test_svg_title_is_accessibility_text_not_an_extra_html_title(self):
        html = '<html><head><title>Artigo</title><meta name="description" content="' + 'a' * 60 + '"></head><body><h1>Artigo</h1><h2>Secção</h2><svg><title>Gráfico acessível</title></svg></body></html>'
        self.assertTrue(seo.inspect_html(html)['passed'])
        duplicate = html.replace('</head>', '<meta name="description" content="outra"></head>')
        self.assertFalse(seo.inspect_html(duplicate)['passed'])

    def test_sql_failure_rolls_back_changes_and_history_after_backup(self):
        from unittest.mock import patch
        backup = Path(self.temp.name) / 'before.json'
        original = seo.revisions
        count = 0
        def fail_second(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError('Simulação de falha SQL')
            return original(*args, **kwargs)
        with patch.object(seo, 'revisions', side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                seo.change(self.engine, self.plan, backup, 'Teste')
        self.assertTrue(backup.exists())
        self.assertEqual(self.row(), self.before)
        with self.engine.connect() as conn:
            self.assertEqual(len(conn.execute(select(self.history)).all()), 0)

    def test_executable_cli_audit_plan_apply_and_restore(self):
        import json
        import os
        import subprocess
        import sys
        folder = Path(self.temp.name)
        env = dict(os.environ, DATABASE_URL=str(self.engine.url))
        def command(*args):
            return subprocess.run([sys.executable, str(ROOT / 'scripts/article_seo.py'), *map(str, args)],
                env=env, capture_output=True, text=True, timeout=15)
        audit = folder / 'audit.json'
        self.assertEqual(command('audit', '--include-content', '--output', audit).returncode, 0)
        data = json.loads(audit.read_text())
        self.assertEqual(data['articles'][0]['body'], self.before['body'])
        proposal = {'articles': [{'slug': self.before['slug'],
            'expected': {k: self.before[k] for k in ('title', 'summary')},
            'after': self.plan['articles'][0]['after'], 'reason': 'Revisão de teste.'}]}
        source = folder / 'proposal.json'
        source.write_text(json.dumps(proposal))
        plan_path = folder / 'plan.json'
        self.assertEqual(command('plan-editorial', '--input', source, '--output', plan_path).returncode, 0)
        backup = folder / 'backup.json'
        self.assertNotEqual(command('apply', '--plan', plan_path, '--backup', backup, '--actor', 'Teste').returncode, 0)
        plan = json.loads(plan_path.read_text())
        plan['articles'][0]['reviewed'] = True
        plan_path.write_text(json.dumps(plan))
        self.assertEqual(command('apply', '--plan', plan_path, '--backup', backup, '--actor', 'Teste').returncode, 0)
        self.assertEqual(command('restore', '--plan', backup, '--backup', folder / 'undo.json', '--actor', 'Teste').returncode, 0)
        self.assertEqual(self.row()['title'], self.before['title'])
        structural = folder / 'structure.json'
        self.assertEqual(command('plan-structure', '--output', structural).returncode, 0)
        self.assertFalse(json.loads(structural.read_text())['articles'][0]['reviewed'])

    def test_public_verification_uses_full_page_and_reports_unchanged_address(self):
        from unittest.mock import patch
        from email.message import Message
        from io import BytesIO
        html = '<head><title>Artigo</title><meta name="description" content="' + 'a' * 60 + '"></head><body><h1>Artigo</h1><h2>Secção</h2></body>'
        response = BytesIO(html.encode())
        response.headers = Message()
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        response.status = 200
        response.url = 'https://www.sussurrosdosaber.com/artigo/exemplo'
        with patch.object(seo, 'urlopen', return_value=response):
            result = seo.verify_public({'articles': [{'id': 1, 'slug': 'exemplo'}]}, 'https://www.sussurrosdosaber.com')
        self.assertTrue(result['articles'][0]['passed'])
        self.assertTrue(result['articles'][0]['unchanged_url'])


if __name__ == '__main__':
    unittest.main()
