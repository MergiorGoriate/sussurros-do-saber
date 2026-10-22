"""Auditoria e actualização controlada; usa DATABASE_URL sem importar a aplicação."""
import argparse
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

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
    directory = os.open(Path(path).resolve().parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def structure_body(body, title):
    """Minimal ATX-only edit; ambiguous HTML/Setext bodies remain unchanged."""
    lines = body.splitlines(keepends=True)
    fence = None
    headings = []
    first_content = next((i for i, line in enumerate(lines) if line.strip()), None)
    for i, line in enumerate(lines):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line.rstrip('\r\n'))
        if marker:
            token, tail = marker.groups()
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not tail.strip():
                fence = None
            continue
        if fence is not None or line.startswith(('    ', '\t')):
            continue
        # Never attempt a general Markdown/HTML rewrite or alter nested blocks.
        if re.search(r'<(?:h[1-6]\b|pre\b|code\b|script\b|style\b|textarea\b|div\b|section\b|article\b|table\b|!--)|^ {0,3}(?:=+|-+)\s*$', line, re.I):
            return body
        match = re.match(r'^(#{1,6})(?=[ \t]|$)(.*)$', line.rstrip('\r\n'))
        if match:
            headings.append((i, len(match[1]), match[2]))
    stack = []
    for i, original, rest in headings:
        plain = BeautifulSoup(markdown.markdown(rest.strip().rstrip('#').rstrip()), 'html.parser').get_text()
        if original == 1 and i == first_content and plain.strip().casefold() == title.strip().casefold():
            lines[i] = ''
            continue
        while stack and stack[-1][0] >= original:
            stack.pop()
        level = min(6, stack[-1][1] + 1) if stack else 2
        stack.append((original, level))
        lines[i] = '#' * level + lines[i][original:]
    return ''.join(lines)


def inspect_html(html):
    """Inspect the complete server-rendered page, including shared components."""
    soup = BeautifulSoup(html, 'html.parser')
    titles = [tag for tag in soup.find_all('title') if not tag.find_parent('svg')]
    descriptions = soup.find_all('meta', attrs={'name': re.compile('^description$', re.I)})
    h1s = soup.find_all('h1')
    headings, skips, previous = [], [], 0
    for heading in soup.find_all(re.compile('^h[1-6]$')):
        level = int(heading.name[1])
        label = heading.get_text(' ', strip=True)
        headings.append({'level': level, 'text': label})
        if level > previous + 1:
            skips.append({'from': previous, 'to': level, 'text': label})
        previous = level
    title = titles[0].get_text() if len(titles) == 1 else None
    description = descriptions[0].get('content', '') if len(descriptions) == 1 else None
    return {'title_count': len(titles), 'html_title': title,
            'html_title_chars': len(title) if title is not None else None,
            'meta_description_count': len(descriptions), 'meta_description': description,
            'meta_description_chars': len(description) if description is not None else None,
            'h1_count': len(h1s), 'h1': [h.get_text(' ', strip=True) for h in h1s],
            'headings': headings, 'heading_skips': skips,
            'passed': (len(titles) == len(descriptions) == len(h1s) == 1 and
                       0 < len(title) < 70 and 0 < len(h1s[0].get_text(' ', strip=True)) < 70 and
                       60 <= len(description) <= 160 and not skips),
            'images_to_review': [{'src': im.get('src'), 'alt': im.get('alt')}
                                 for im in soup.find_all('img') if not im.get('alt')]}


def verify_public(audit_data, base_url):
    origin = urlsplit(base_url)
    if origin.scheme != 'https' or not origin.netloc or origin.username or origin.password or origin.query or origin.fragment or origin.path not in ('', '/'):
        raise ValueError('Use uma origem HTTPS pública, sem credenciais ou caminhos.')
    results = []
    for item in audit_data['articles']:
        url = base_url.rstrip('/') + '/artigo/' + quote(item['slug'], safe='')
        result = {'id': item['id'], 'url': url}
        try:
            with urlopen(Request(url, headers={'User-Agent': 'SussurrosDoSaber-SEO-Audit/1.0'}), timeout=15) as response:
                payload = response.read(4 * 1024 * 1024 + 1)
                if len(payload) > 4 * 1024 * 1024 or response.headers.get_content_type() != 'text/html':
                    raise ValueError('Resposta incompatível com HTML.')
                result.update(status=response.status, final_url=response.url,
                              unchanged_url=response.url == url,
                              **inspect_html(payload.decode(response.headers.get_content_charset() or 'utf-8')))
                result['passed'] = result['passed'] and response.status == 200 and response.url == url
        except Exception:
            result.update(passed=False, error='Página não verificada; confirmar resposta HTTP, acesso e URL.')
        results.append(result)
    return {'articles': results, 'scope': 'HTML completo recebido por HTTP; sem executar JavaScript, sem sessão editorial e sem inspecção visual das imagens.'}


def audit(rows, include_content=False):
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
                       'legacy_template_title': row['title'] + SUFFIX, 'legacy_template_title_chars': len(row['title'] + SUFFIX),
                       'html_title': page_title(row['title']), 'html_title_chars': len(page_title(row['title'])),
                       'summary': row['summary'], 'summary_chars': len(row['summary']),
                       'issues': issues, 'images': images,
                       'structure_change_available': structure_body(row.get('body') or '', row['title']) != (row.get('body') or ''),
                       **({'body': row.get('body'), 'references': row.get('references')} if include_content else {})})
    return {'status': 'Auditoria; nenhuma alteração aplicada.', 'articles': result,
            'limits': 'Critérios editoriais; sem garantia de apresentação ou posição no Google.',
            'rendering': 'Estrutura estimada a partir de Markdown; confirmar no HTML público completo.'}


def editorial_plan(rows, proposals):
    by_slug = {r['slug']: r for r in rows}
    result, seen = [], set()
    for proposal in proposals['articles']:
        slug = proposal['slug']
        if slug in seen or slug not in by_slug:
            raise ValueError('Slug repetido, inexistente ou não publicado no plano editorial.')
        seen.add(slug)
        row = by_slug[slug]
        after = proposal['after']
        if not after or set(after) - {'title', 'summary'}:
            raise ValueError('As propostas editoriais admitem apenas título e resumo.')
        if all(row[k] == v for k, v in after.items()):
            continue
        expected = proposal['expected']
        if set(expected) != {'title', 'summary'} or any(row[k] != v for k, v in expected.items()):
            raise ValueError('Os valores de produção diferem dos observados. Reveja a proposta.')
        result.append({'id': row['id'], 'fingerprint': digest(row), 'after': after,
                       'reviewed': False, 'reason': proposal.get('reason', '')})
    return {'articles': result, 'status': 'Plano preparado para revisão; nenhuma alteração aplicada.'}


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
                    wanted = {k: item['before'][k] for k in item.get('changed_fields', ('title', 'summary'))}
                    expected = item['after_fingerprint']
                else:
                    wanted = item['after']
                    expected = item['fingerprint']
                if not wanted or set(wanted) - {'title', 'summary', 'body'}:
                    raise ValueError('Só são permitidos title, summary e a correcção estrutural determinística de body.')
                if any(not isinstance(v, str) for v in wanted.values()):
                    raise ValueError('Os valores devem ser texto.')
                if all(row[k] == v for k, v in wanted.items()):
                    continue
                if digest(row) != expected:
                    raise ValueError('O artigo mudou desde a auditoria; volte a auditar.')
                updated = dict(row, **wanted)
                if not restore and (('title' in wanted and not 5 <= len(updated['title']) < 70) or ('summary' in wanted and not 60 <= len(updated['summary']) <= 160)):
                    raise ValueError('Título ou meta descrição fora dos limites.')
                if not restore and any(v.strip() != v for k, v in wanted.items() if k in ('title', 'summary')):
                    raise ValueError('Remova espaços exteriores.')
                if not restore and (item.get('reviewed') is not True or not isinstance(item.get('reason'), str) or not item['reason'].strip()):
                    raise ValueError('Confirme reviewed=true e justifique a fidelidade ao conteúdo em reason.')
                if not restore and 'body' in wanted and wanted['body'] != structure_body(row['body'], row['title']):
                    raise ValueError('O corpo contém alterações para além da estrutura ATX permitida.')
                updated['updated_at'] = datetime.now(timezone.utc).replace(tzinfo=None)
                prepared.append((row, updated))
            final = dict(by_id)
            final.update({new['id']: new for old, new in prepared})
            if not restore:
                for field in ('title', 'summary'):
                    counts = Counter(r[field].strip().casefold() for r in final.values())
                    for old, new in prepared:
                        if new[field] != old[field] and counts[new[field].strip().casefold()] > 1:
                            raise ValueError('O resultado contém um título ou descrição duplicados.')
            recovery = {'articles': [{'id': old['id'], 'before': old,
                         'after_fingerprint': digest(new),
                         'changed_fields': [k for k in ('title', 'summary', 'body') if old[k] != new[k]],
                         'rendered_title_before': page_title(old['title']),
                         'rendered_title_before_chars': len(page_title(old['title'])),
                         'rendered_title_after': page_title(new['title']),
                         'rendered_title_after_chars': len(page_title(new['title'])),
                         'changes': {k: {'before': old[k], 'after': new[k],
                             'before_chars': len(old[k]), 'after_chars': len(new[k])}
                             for k in ('title', 'summary', 'body') if old[k] != new[k]}}
                         for old, new in prepared]}
            if not prepared:
                conn.rollback()
                return {'changed': 0}
            write_new(backup, recovery)
            for old, new in prepared:
                revisions(conn, history, old, 'Antes do ajuste SEO' if not restore else 'Antes da recuperação SEO', actor)
                conn.execute(articles.update().where(articles.c.id == old['id']).values(
                    title=new['title'], summary=new['summary'], body=new['body'], updated_at=new['updated_at']))
                revisions(conn, history, new, 'Ajuste SEO' if not restore else 'Recuperação SEO', actor)
                conn.execute(logs.insert().values(actor_id=None, actor_name=actor,
                    action='article.seo.restore' if restore else 'article.seo.update', entity='article',
                    entity_id=old['id'], detail='Ajuste SEO revisto; endereços, autoria, referências e estado preservados.',
                    created_at=new['updated_at']))
            conn.commit()
            return {'changed': len(prepared), 'backup': str(backup)}
        except Exception:
            conn.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['audit', 'plan-editorial', 'plan-structure', 'apply', 'restore', 'verify'])
    parser.add_argument('--output')
    parser.add_argument('--plan')
    parser.add_argument('--backup')
    parser.add_argument('--actor')
    parser.add_argument('--include-content', action='store_true')
    parser.add_argument('--input')
    parser.add_argument('--base-url', default='https://www.sussurrosdosaber.com')
    args = parser.parse_args()
    if args.action == 'verify':
        if not args.input or not args.output:
            parser.error('Indique --input com a auditoria e --output para o relatório HTTP.')
        try:
            write_new(args.output, verify_public(json.loads(Path(args.input).read_text(encoding='utf-8')), args.base_url))
        except Exception:
            raise SystemExit('Verificação interrompida; confirme os ficheiros e a origem HTTPS.') from None
        print('Relatório HTTP guardado; consulte os resultados por artigo.')
        return
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
        if args.action in ('audit', 'plan-editorial', 'plan-structure'):
            if not args.output:
                raise ValueError('Indique --output para um ficheiro novo e privado.')
            with engine.connect() as conn:
                if engine.dialect.name == 'postgresql':
                    conn.execute(text('SET TRANSACTION READ ONLY'))
                else:
                    conn.execute(text('PRAGMA query_only = ON'))
                table = Table('article', MetaData(), autoload_with=conn)
                rows = [dict(r) for r in conn.execute(select(table).where(table.c.status == 'published')).mappings()]
                if args.action == 'audit':
                    output = audit(rows, args.include_content)
                elif args.action == 'plan-editorial':
                    if not args.input:
                        raise ValueError('Indique --input com as propostas editoriais.')
                    output = editorial_plan(rows, json.loads(Path(args.input).read_text(encoding='utf-8')))
                else:
                    output = {'articles': [{'id': r['id'], 'fingerprint': digest(r),
                        'after': {'body': structure_body(r['body'], r['title'])},
                        'reviewed': False, 'reason': ''}
                        for r in rows if structure_body(r['body'], r['title']) != r['body']]}
                write_new(args.output, output)
            print('Auditoria guardada. Nenhum registo alterado.' if args.action == 'audit' else 'Plano guardado para revisão. Nenhum registo alterado.')
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
