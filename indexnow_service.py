"""Transactional IndexNow outbox; HTTP delivery never runs in an editorial request."""
import os
import ipaddress
import threading
import time
from datetime import timedelta
from urllib.parse import quote, urlsplit

import click
import requests
from flask import current_app, has_app_context
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session

from models import Article, Journal, db, utcnow

KEY = "790c8a9d2960414f923b2ccf49e86d72"
ENDPOINT = "https://api.indexnow.org/indexnow"
ARTICLE_FIELDS = (
    "title", "slug", "summary", "body", "references", "keywords", "doi",
    "image", "cover_video", "cover_mode", "background", "status", "read_minutes",
    "featured", "published_at", "author_id", "category_id",
)
JOURNAL_FIELDS = tuple(c.name for c in Journal.__table__.columns
                       if c.name not in {"id", "created_at", "updated_at"})


class IndexNowNotification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(2048), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    next_attempt_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    attempts = db.Column(db.Integer, default=0, nullable=False)
    sent_at = db.Column(db.DateTime, index=True)
    last_status = db.Column(db.Integer)
    last_error = db.Column(db.String(240), default="", nullable=False)


def _settings():
    if not has_app_context():
        return None
    settings = current_app.extensions.get("indexnow")
    if settings and current_app.config.get("INDEXNOW_ENABLED"):
        return settings
    return None


def _content_url(settings, obj, slug):
    # Escape the slug as a single URL segment, never a host or query string.
    prefix = "/artigo/" if isinstance(obj, Article) else "/revistas/"
    return settings["origin"] + prefix + quote(slug, safe="") if slug else None


@event.listens_for(Session, "before_flush")
def collect_changes(session, flush_context, instances):
    settings = _settings()
    if not settings:
        return
    changes = session.info.setdefault("indexnow_changes", {})
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if not isinstance(obj, (Article, Journal)):
            continue
        if obj in changes:
            continue
        fields = ARTICLE_FIELDS if isinstance(obj, Article) else JOURNAL_FIELDS
        deleted = obj in session.deleted
        new = obj in session.new
        if not new and not deleted and not any(
            inspect(obj).attrs[field].history.has_changes() for field in fields
        ):
            continue
        # Read the committed visibility/slug in the same transaction. This also
        # works for expired ORM attributes and a published -> draft -> delete edit.
        table = obj.__table__
        visibility = table.c.status if isinstance(obj, Article) else table.c.published
        previous = None if new else session.connection().execute(
            select(table.c.slug, visibility).where(table.c.id == obj.id)
        ).first()
        was_public = bool(previous and (
            previous[1] == "published" if isinstance(obj, Article) else previous[1]
        ))
        changes[obj] = (was_public, previous[0] if previous else None)


@event.listens_for(Session, "before_commit")
def enqueue_committed_changes(session):
    settings = _settings()
    if not settings or session.in_nested_transaction():
        return
    # Explicit flushes may expose intermediate statuses within the transaction.
    # Enqueue only the final state that is about to become publicly committed.
    session.flush()
    urls = set()
    for obj, (was_public, old_slug) in session.info.get("indexnow_changes", {}).items():
        public = not inspect(obj).deleted and (
            obj.status == "published" if isinstance(obj, Article) else bool(obj.published)
        )
        if was_public:
            urls.add(_content_url(settings, obj, old_slug))
        if public:
            urls.add(_content_url(settings, obj, obj.slug))
    for url in sorted(urls - {None}):
        session.add(IndexNowNotification(url=url))
    if urls - {None}:
        session.info["indexnow_changed"] = True


@event.listens_for(Session, "after_commit")
def deliver_after_commit(session):
    if session.in_nested_transaction():
        return
    session.info.pop("indexnow_changes", None)
    session.info.pop("indexnow_savepoints", None)
    if session.info.pop("indexnow_changed", False) and _settings():
        wake_worker(current_app._get_current_object())


@event.listens_for(Session, "after_rollback")
def discard_rollback_marker(session):
    if session.in_nested_transaction():
        return
    session.info.pop("indexnow_changed", None)
    session.info.pop("indexnow_changes", None)
    session.info.pop("indexnow_savepoints", None)


@event.listens_for(Session, "after_transaction_create")
def remember_savepoint(session, transaction):
    if transaction.nested:
        session.info.setdefault("indexnow_savepoints", {})[transaction] = dict(
            session.info.get("indexnow_changes", {})
        )


@event.listens_for(Session, "after_soft_rollback")
def restore_savepoint(session, previous_transaction):
    if previous_transaction.nested:
        session.info["indexnow_changes"] = session.info.get("indexnow_savepoints", {}).pop(
            previous_transaction, {}
        )


def process_pending(app, limit=100):
    """Send one bounded batch, locking only outbox rows on PostgreSQL.

    Repeated delivery after a process crash is harmless: IndexNow is an update
    notification, not a transaction with an external business side effect.
    """
    settings = _settings()
    if not settings:
        return 0
    now = utcnow()
    rows = (IndexNowNotification.query.filter(
        IndexNowNotification.sent_at.is_(None),
        IndexNowNotification.next_attempt_at <= now,
    ).order_by(IndexNowNotification.id).with_for_update(skip_locked=True).limit(limit).all())
    if not rows:
        db.session.rollback()
        return 0
    host = urlsplit(settings["origin"]).netloc
    valid, invalid = [], []
    for row in rows:
        parsed = urlsplit(row.url)
        if (parsed.scheme == "https" and parsed.netloc == host and
                parsed.path.startswith(("/artigo/", "/revistas/")) and
                not parsed.query and not parsed.fragment):
            valid.append(row)
        else:
            invalid.append(row)
    status, error, retry_after = None, "", 0
    if valid:
        try:
            response = requests.post(ENDPOINT, json={
                "host": host,
                "key": KEY,
                "keyLocation": settings["origin"] + "/" + KEY + ".txt",
                "urlList": list(dict.fromkeys(row.url for row in valid)),
            }, timeout=(3, 10), allow_redirects=False)
            status = response.status_code
            if status not in {200, 202}:
                error = "IndexNow HTTP " + str(status)
                value = response.headers.get("Retry-After", "")
                if value.isdigit():
                    retry_after = min(int(value), 86400)
        except requests.RequestException as exc:
            # Do not log request URLs, payloads or exception strings with secrets.
            error = type(exc).__name__
    for row in valid + invalid:
        row.attempts += 1
        row.last_status = status if row in valid else None
        if row in valid and status in {200, 202}:
            row.sent_at = now
            row.last_error = ""  # 202 means received, with key validation pending.
        else:
            row.last_error = error if row in valid else "URL outside the configured public origin"
            delay = max(retry_after, min(86400, 60 * 2 ** min(row.attempts - 1, 11)))
            row.next_attempt_at = now + timedelta(seconds=delay)
    db.session.commit()
    if error or invalid:
        app.logger.warning("IndexNow: batch retained for retry (%s).", error or "invalid origin")
    return sum(row.sent_at is not None for row in rows)


def wake_worker(app):
    settings = app.extensions["indexnow"]
    if (app.testing or not app.config.get("INDEXNOW_ENABLED") or
            time.monotonic() < settings["next_wake"]):
        return
    if not settings["lock"].acquire(blocking=False):
        return
    settings["next_wake"] = time.monotonic() + 30

    def run():
        try:
            with app.app_context():
                try:
                    process_pending(app)
                except Exception:
                    db.session.rollback()
                    app.logger.exception("IndexNow: delivery interrupted; pending records preserved.")
                finally:
                    db.session.remove()
        finally:
            settings["lock"].release()

    try:
        threading.Thread(target=run, name="indexnow-delivery", daemon=True).start()
    except Exception:
        settings["lock"].release()
        app.logger.exception("IndexNow: could not start delivery worker.")


def install_indexnow(app, site_url):
    """Install after seeding, so deployment never resubmits historical content."""
    if "indexnow" in app.extensions:
        return
    origin = site_url.rstrip("/")
    parsed = urlsplit(origin)
    host = (parsed.hostname or "").lower()
    local = host == "localhost" or host.endswith((".localhost", ".test"))
    try:
        local = local or ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    app.config.setdefault("INDEXNOW_ENABLED", os.getenv("INDEXNOW_ENABLED", "true").lower() == "true")
    if local:
        # Browser/CI servers use HTTP loopback. Never submit local fixtures.
        app.config["INDEXNOW_ENABLED"] = False
    if app.config["INDEXNOW_ENABLED"] and (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.path or parsed.query or parsed.fragment):
        raise ValueError("IndexNow requires an HTTPS SITE_URL with no path or credentials")
    app.extensions["indexnow"] = {"origin": origin, "lock": threading.Lock(), "next_wake": 0.0}

    @app.after_request
    def resume_indexnow_delivery(response):
        # Future requests retry pending work, including after worker restarts.
        if response.status_code < 500 and request_is_content_request():
            wake_worker(app)
        return response

    @app.cli.command("processar-indexnow")
    def process_indexnow_command():
        """Entrega um lote pendente; pode ser executado periodicamente no Coolify."""
        count = process_pending(app)
        click.echo(f"{count} notificação(ões) recebida(s) pelo IndexNow.")


def request_is_content_request():
    from flask import request
    return request.endpoint not in {"static", "healthcheck", "indexnow_key"}
