"""Run on the VPS: python scripts/audit_published_content.py > content-audit.json
Uses DATABASE_URL; does not import Flask, seed the database or change content.
Only published article titles, slugs, DOI strings and editorial signals are exported.
"""
import json
import os
import sys
from pathlib import Path
from sqlalchemy import MetaData, Table, create_engine, select, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from content_audit import assess_article


def inspect_database(url):
    if url.startswith(('postgres://', 'postgresql://')):
        url = 'postgresql+psycopg://' + url.split('://', 1)[1]
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            if engine.dialect.name == 'postgresql':
                conn.execute(text('SET TRANSACTION READ ONLY'))
            elif engine.dialect.name == 'sqlite':
                conn.execute(text('PRAGMA query_only = ON'))
            else:
                raise ValueError('Use PostgreSQL ou SQLite.')
            table = Table('article', MetaData(), autoload_with=conn)
            statement = select(table.c.slug, table.c.title, table.c.body,
                               table.c.references, table.c.image).where(table.c.status == 'published').order_by(table.c.slug)
            articles = [assess_article(dict(row)) for row in conn.execute(statement).mappings()]
        return {'published_articles': len(articles), 'articles': articles,
                'scope': 'Editorial signals only; not an AdSense approval, plagiarism scan, full scientific review or licence validation.'}
    finally:
        engine.dispose()


if __name__ == '__main__':
    url = os.getenv('DATABASE_URL')
    if not url:
        raise SystemExit('Defina DATABASE_URL no ambiente do serviço; não cole credenciais na linha de comandos.')
    try:
        result = inspect_database(url)
    except Exception:
        # SQLAlchemy connection errors may contain connection details: do not print them.
        raise SystemExit('Auditoria não executada. Confirme acesso de leitura à base de dados e o esquema da aplicação.') from None
    print(json.dumps(result, ensure_ascii=False, indent=2))
