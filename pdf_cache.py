"""Bounded private PDF cache and a cross-worker generation slot (Linux)."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
from flask import Response, current_app

MAX_PDF_BYTES = 16 * 1024 * 1024
CACHE_BYTES = 64 * 1024 * 1024
CACHE_TTL = 300


def cached_pdf_response(journal, build):
    root = Path(current_app.instance_path) / "pdf-cache"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    table = getattr(journal, "__table__", None)
    values = ({column.name: getattr(journal, column.name) for column in table.columns}
              if table is not None else vars(journal))
    values = dict(values)
    values['_format_version'] = 3
    values['_database'] = current_app.config['SQLALCHEMY_DATABASE_URI']
    if table is None or getattr(journal, 'id', None) is None:
        values['_transient'] = secrets.token_hex(16)
    key = hashlib.sha256(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()
    path = root / (key + ".pdf")

    def read():
        try:
            info = path.stat()
            if time.time() - info.st_mtime < CACHE_TTL and info.st_size <= MAX_PDF_BYTES:
                return path.read_bytes()
        except FileNotFoundError:
            pass
        return None

    pdf = read()
    if pdf is None:
        descriptor = os.open(root / "generation.lock", os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, "wb") as slot:
            try:
                fcntl.flock(slot, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return Response("Há um PDF em preparação. Tente novamente dentro de alguns instantes.",
                                status=503, headers={"Retry-After": "5", "Cache-Control": "no-store"})
            pdf = read()
            if pdf is None:
                pdf = build(journal)
                if len(pdf) > MAX_PDF_BYTES:
                    return Response("O PDF excede o tamanho permitido.", status=413,
                                    headers={"Cache-Control": "no-store"})
                entries = sorted(root.glob("*.pdf"), key=lambda p: p.stat().st_mtime)
                total = sum(p.stat().st_size for p in entries)
                for item in entries:
                    if time.time() - item.stat().st_mtime >= CACHE_TTL or total + len(pdf) > CACHE_BYTES:
                        total -= item.stat().st_size
                        item.unlink(missing_ok=True)
                with tempfile.NamedTemporaryFile(dir=root, delete=False) as output:
                    temporary = Path(output.name)
                    try:
                        output.write(pdf)
                        output.flush()
                        os.replace(temporary, path)
                    finally:
                        temporary.unlink(missing_ok=True)
    filename = re.sub(r"[^a-zA-Z0-9._-]+", "-", journal.slug).strip("-") + ".pdf"
    return Response(pdf, mimetype="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    })
