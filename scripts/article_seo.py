"""Auditoria e actualização controlada; usa DATABASE_URL sem importar a aplicação."""
import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from bs4 import BeautifulSoup
import markdown
from sqlalchemy import MetaData, Table, create_engine, select, text

SUFFIX = ' — Sussurros do Saber'
FIELDS = ('title', 'summary', 'body', 'references', 'keywords', 'doi', 'image',
          'cover_video', 'read_minutes', 'featured', 'background', 'cover_mode')


def page_title(title):
    return title + SUFFIX if len(title + SUFFIX) < 70 else title


def serial(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def digest(row):
    return hashlib.sha256(json.dumps(dict(row), default=serial, sort_keys=True,
                                    ensure_ascii=False).encode()).hexdigest()


def write_new(path, value):
    # Exclusive creation prevents overwriting a recovery copy. fsync before SQL.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=serial)
        stream.flush()
        os.fsync(stream.fileno())


def audit(rows):
    titles = Counter(r['title'].strip().casefold() for r in rows)
    summaries = Counter(r['summary'].strip().casefold() for r in rows)
    result = []
    for row in rows:
        issues = []
        if not 5 <= len(row['title']) < 70:
            issues.append('Título fora de 5–69 caracteres.')
        if titles[row['title'].strip().casefold()] > 1:
            issues.append('Título duplicado.')
        if not 60 <= len(row['summary']) <= 160:
            issues.append('Meta descrição fora de 60–160 caracteres.')
        if summaries[row['summary'].strip().casefold()] > 1:
            issues.append('Meta descrição duplicada.')
        soup = BeautifulSoup(markdown.markdown(row.get('body') or '', extensions=['extra']), 'html.parser')
        previous = 1
        for heading in soup.find_all(re.compile('^h[1-6]$')):
            level = int(heading.name[1])
            if level == 1:
                issues.append('H1 no corpo: ' + heading.get_text(' ', strip=True))
            if level > previous + 1:
                issues.append(f'Salto H{previous} → H{level}: ' + heading.get_text(' ', strip=True))
            previous = level
        images = [{'src': im.get('src'), 'alt': im.get('alt'),
                   'review': 'Inspecção visual e classificação informativa/decorativa pendentes.'}
                  for im in soup.find_all('img')]
        if row.get('image'):
            images.insert(0, {'src': row['image'], 'review': 'Capa sem campo próprio de alt; inspecção pendente.'})
        result.append({'id': row['id'], 'slug': row['slug'], 'fingerprint': digest(row),
                       'title': row['title'], 'title_chars': len(row['title']),
                       'previous_html_title': row['title'] + SUFFIX, 'previous_html_title_chars': len(row['title'] + SUFFIX),
                       'html_title': page_title(row['title']), 'html_title_chars': len(page_title(row['title'])),
                       'summary': row['summary'], 'summary_chars': len(row['summary']),
                       'issues': issues, 'images': images})
    return {'status': 'Auditoria; nenhuma alteração aplicada.', 'articles': result,
            'limits': 'Critérios editoriais; sem garantia de apresentação ou posição no Google.',
            'rendering': 'Estrutura estimada a partir de Markdown; confirmar no HTML público completo.'}


def revisions(conn, table, row, reason, actor):
    last = conn.execute(select(table.c.number, table.c.snapshot).where(
        table.c.article_id == row['id']).order_by(table.c.number.desc()).limit(1)).first()
    snapshot = {name: row[name] for name in FIELDS}
    if last and last.snapshot == snapshot:
        return
    conn.execute(table.insert().values(article_id=row['id'], number=last.number + 1 if last else 1,
        snapshot=snapshot, actor_id=None, actor_name=actor, reason=reason,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None)))


def change(engine, plan, backup, actor, restore=False):
    if not actor or len(actor) > 120:
        raise ValueError('Identifique o operador (1–120 caracteres).')
    with engine.connect() as conn:
        if engine.dialect.name == 'sqlite':
            conn.exec_driver_sql('BEGIN IMMEDIATE')
        else:
            conn.begin()
            conn.execute(text('LOCK TABLE article IN SHARE ROW EXCLUSIVE MODE'))
        try:
            meta = MetaData()
            articles = Table('article', meta, autoload_with=conn)
            history = Table('article_revision', meta, autoload_with=conn)
            logs = Table('governance_audit', meta, autoload_with=conn)
            rows = [dict(r) for r in conn.execute(select(articles).where(articles.c.status == 'published')).mappings()]
            by_id = {r['id']: r for r in rows}
            prepared, seen = [], set()
            for item in plan['articles']:
                ident = item['id']
                if ident in seen or ident not in by_id:
                    raise ValueError('Identificador repetido, inexistente ou não publicado.')
                seen.add(ident)
                row = by_id[ident]
                if restore:
                    wanted = {k: item['before'][k] for k in ('title', 'summary')}
                    expected = item['after_fingerprint']
                else:
                    wanted = item['after']
                    expected = item['fingerprint']
                if not wanted or set(wanted) - {'title', 'summary'}:
                    raise ValueError('Só são permitidos title e summary; estrutura e imagens exigem revisão própria.')
                if any(not isinstance(v, str) for v in wanted.values()):
                    raise ValueError('Os valores devem ser texto.')
                if all(row[k] == v for k, v in wanted.items()):
                    continue
                if digest(row) != expected:
                    raise ValueError('O artigo mudou desde a auditoria; volte a auditar.')
                updated = dict(row, **wanted)
                if not restore and (not 5 <= len(updated['title']) < 70 or not 60 <= len(updated['summary']) <= 160):
                    raise ValueError('Título ou meta descrição fora dos limites.')
                if not restore and (updated['title'].strip() != updated['title'] or updated['summary'].strip() != updated['summary']):
                    raise ValueError('Remova espaços exteriores.')
                if not restore and (not item.get('reviewed') or not item.get('reason')):
                    raise ValueError('Confirme reviewed=true e justifique a fidelidade ao conteúdo em reason.')
                updated['updated_at'] = datetime.now(timezone.utc).replace(tzinfo=None)
                prepared.append((row, updated))
            final = dict(by_id)
            final.update({new['id']: new for old, new in prepared})
            if not restore:
                for field in ('title', 'summary'):
                    counts = Counter(r[field].strip().casefold() for r in final.values())
                    for old, new in prepared:
                        if counts[new[field].strip().casefold()] > 1:
                            raise ValueError('O resultado contém um título ou descrição duplicados.')
            recovery = {'articles': [{'id': old['id'], 'before': old,
                         'after_fingerprint': digest(new),
                         'changes': {k: {'before': old[k], 'after': new[k],
                             'before_chars': len(old[k]), 'after_chars': len(new[k])}
                             for k in ('title', 'summary') if old[k] != new[k]}}
                         for old, new in prepared]}
            if not prepared:
                conn.rollback()
                return {'changed': 0}
            write_new(backup, recovery)
            for old, new in prepared:
                revisions(conn, history, old, 'Antes do ajuste SEO' if not restore else 'Antes da recuperação SEO', actor)
                conn.execute(articles.update().where(articles.c.id == old['id']).values(
                    title=new['title'], summary=new['summary'], updated_at=new['updated_at']))
                revisions(conn, history, new, 'Ajuste SEO' if not restore else 'Recuperação SEO', actor)
                conn.execute(logs.insert().values(actor_id=None, actor_name=actor,
                    action='article.seo.restore' if restore else 'article.seo.update', entity='article',
                    entity_id=old['id'], detail='Título/resumo; endereços e estado preservados.',
                    created_at=new['updated_at']))
            conn.commit()
            return {'changed': len(prepared), 'backup': str(backup)}
        except Exception:
            conn.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['audit', 'apply', 'restore'])
    parser.add_argument('--output')
    parser.add_argument('--plan')
    parser.add_argument('--backup')
    parser.add_argument('--actor')
    args = parser.parse_args()
    url = os.environ.get('DATABASE_URL')
    if not url:
        parser.error('Defina DATABASE_URL no ambiente do serviço, sem a imprimir.')
    if url.startswith(('postgres://', 'postgresql://')):
        url = 'postgresql+psycopg://' + url.split('://', 1)[1]
    engine = None
    try:
        engine = create_engine(url, hide_parameters=True)
        if engine.dialect.name not in ('postgresql', 'sqlite'):
            raise ValueError('Use PostgreSQL ou SQLite.')
        if args.action == 'audit':
            if not args.output:
                raise ValueError('Indique --output para um ficheiro novo e privado.')
            with engine.connect() as conn:
                if engine.dialect.name == 'postgresql':
                    conn.execute(text('SET TRANSACTION READ ONLY'))
                else:
                    conn.execute(text('PRAGMA query_only = ON'))
                table = Table('article', MetaData(), autoload_with=conn)
                rows = [dict(r) for r in conn.execute(select(table).where(table.c.status == 'published')).mappings()]
                write_new(args.output, audit(rows))
            print('Auditoria guardada. Nenhum registo alterado.')
        else:
            if not all((args.plan, args.backup, args.actor)):
                raise ValueError('Indique --plan, --backup e --actor.')
            plan = json.loads(Path(args.plan).read_text(encoding='utf-8'))
            print(json.dumps(change(engine, plan, args.backup, args.actor, args.action == 'restore'), ensure_ascii=False))
    except ValueError as error:
        raise SystemExit(str(error)) from None
    except Exception:
        raise SystemExit('Operação interrompida; confirme acesso, esquema e ficheiros. Nenhuma credencial foi impressa. Se existir uma cópia, confirme o estado dos registos antes de a utilizar.') from None
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    main()
