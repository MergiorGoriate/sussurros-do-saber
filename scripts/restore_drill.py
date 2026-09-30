"""Restore a pg_dump archive into a newly created, isolated PostgreSQL database.

RESTORE_ADMIN_URL must point to the PostgreSQL maintenance database, not the app.
No existing database is overwritten or removed. Credentials are never printed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
from datetime import datetime, timezone

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

TABLES = ("article", "author", "category", "journal", "admin_user",
          "comment", "contact_message", "subscriber")
PG_ENV = {"host": "PGHOST", "hostaddr": "PGHOSTADDR", "port": "PGPORT",
          "user": "PGUSER", "password": "PGPASSWORD", "passfile": "PGPASSFILE",
          "sslmode": "PGSSLMODE", "sslrootcert": "PGSSLROOTCERT",
          "sslcert": "PGSSLCERT", "sslkey": "PGSSLKEY",
          "connect_timeout": "PGCONNECT_TIMEOUT", "application_name": "PGAPPNAME"}


def restore_archive(archive, admin_url):
    archive = Path(archive).resolve(strict=True)
    if not archive.is_file() or not shutil.which("pg_restore"):
        raise ValueError("Arquivo ou pg_restore indisponível.")
    config = conninfo_to_dict(admin_url)
    if config.get("dbname") != "postgres":
        raise ValueError("RESTORE_ADMIN_URL deve usar a base de manutenção postgres.")
    if set(config) - set(PG_ENV) - {"dbname"}:
        raise ValueError("Use parâmetros PostgreSQL explícitos suportados pelo procedimento.")
    # Validate archive before creating anything. Never use --create or --clean.
    subprocess.run(["pg_restore", "--list", str(archive)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    name = "sussurros_restore_" + secrets.token_hex(8)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
    target_url = make_conninfo(admin_url, dbname=name)
    env = dict(os.environ)
    # Remove libpq defaults that could route pg_restore to a different database.
    for key in list(env):
        if key.startswith("PG"):
            env.pop(key)
    for key, value in config.items():
        if key in PG_ENV:
            env[PG_ENV[key]] = value
    subprocess.run(["pg_restore", "--dbname", name, "--no-owner", "--no-acl", "--exit-on-error",
                    "--single-transaction", str(archive)], env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3600)
    with psycopg.connect(target_url) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        counts = {}
        for table in TABLES:
            counts[table] = connection.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier(table))).fetchone()[0]
        broken = connection.execute("""
            SELECT count(*) FROM article a
            LEFT JOIN author au ON au.id = a.author_id
            LEFT JOIN category c ON c.id = a.category_id
            WHERE au.id IS NULL OR c.id IS NULL
        """).fetchone()[0]
        broken += connection.execute("""
            SELECT count(*) FROM comment c LEFT JOIN article a ON a.id = c.article_id
            WHERE a.id IS NULL
        """).fetchone()[0]
    if broken:
        raise ValueError("A cópia restaurada contém relações inválidas.")
    with archive.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"restored_at_utc": datetime.now(timezone.utc).isoformat(),
            "database": name, "archive_sha256": digest, "counts": counts,
            "broken_relations": broken, "restore_completed": True,
            "content_review_completed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    admin_url = os.environ.get("RESTORE_ADMIN_URL", "")
    if not admin_url:
        parser.error("Configure RESTORE_ADMIN_URL num ambiente privado.")
    try:
        report = restore_archive(args.archive, admin_url)
        # Create privately; refuse overwriting an earlier report.
        fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(report, output, ensure_ascii=False, indent=2)
    except Exception:
        parser.exit(1, "Restauração não validada. Consulte o PostgreSQL; a base de teste é preservada.\n")
    print("Restauração isolada concluída. Reveja os conteúdos antes de validar a recuperação.")


if __name__ == "__main__":
    main()
