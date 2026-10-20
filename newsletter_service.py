"""Weekly digest using existing subscribers and the transactional outbox."""
import hashlib
import json
import os
import re
from datetime import timedelta
from urllib.parse import quote, urljoin, urlparse

import click
from flask import Blueprint, abort, current_app, render_template, request, url_for
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import exists, select, text

from models import Article, Subscriber, db, utcnow
from submission_models import EditorialNotification

newsletter_bp = Blueprint('newsletter_public', __name__)
CANCELLED = 'Boletim cancelado: inscrição inactiva.'
SUBJECT_PATTERN = r'Sussurros do Saber — Boletim \d{4}-W\d{2}'


def smtp_ready():
    from submissions import email_valid
    return bool(os.getenv('SMTP_HOST', '').strip() and email_valid(os.getenv('SMTP_FROM', ''))
                and (os.getenv('SMTP_TLS', 'true').lower() == 'true'
                     or os.getenv('SMTP_SSL', 'false').lower() == 'true')
                and os.getenv('NEWSLETTER_ENABLED', 'true').lower() == 'true')


def origin():
    return os.getenv('SITE_URL', 'https://www.sussurrosdosaber.com').rstrip('/')


def unsubscribe_token(subscriber):
    return URLSafeSerializer(current_app.secret_key, salt='newsletter-unsubscribe-v1').dumps(
        [subscriber.id, subscriber.created_at.isoformat()])


def unsubscribe_url(subscriber):
    return origin() + '/boletim/cancelar/' + unsubscribe_token(subscriber)


def is_newsletter(row):
    return bool(re.fullmatch(SUBJECT_PATTERN, row.subject))


def newsletter_image_url(value):
    """Use public, absolute cover URLs; do not fetch images on the mail worker."""
    from app import responsive_image_url, safe_image_url
    value = str(value or '').strip()
    if value.startswith('/static/'):
        value = urljoin(origin() + '/', value)
    value = safe_image_url(value)
    parsed = urlparse(value)
    if not value or parsed.username or parsed.password:
        return ''
    image = responsive_image_url(value, 640)
    # Email clients have wider JPEG support than automatic AVIF/WebP variants.
    if parsed.hostname == 'res.cloudinary.com' and '/upload/' in parsed.path:
        image = image.replace('/upload/f_auto,', '/upload/f_jpg,', 1)
    return urljoin(origin() + '/', image) if image.startswith('/static/') else image


def render_digest_html(edition, subscriber):
    # Rendering from the CLI must not invoke request/session context processors.
    return current_app.jinja_env.get_template('emails/newsletter.html').render(
        edition=edition, site_url=origin(), cancellation_url=unsubscribe_url(subscriber))


def digest(now=None):
    """The last complete Monday-to-Monday week, measured in UTC."""
    now = now or utcnow()
    end = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=7)
    year, week, _ = start.isocalendar()
    issue = f'{year}-W{week:02d}'
    articles = Article.public_card_query().filter(
        Article.published_at >= start, Article.published_at < end,
    ).order_by(Article.published_at.desc(), Article.id.desc()).limit(5).all()
    subject = 'Sussurros do Saber — Boletim ' + issue
    cards = [{'title':a.title, 'summary':a.summary[:1000], 'category':a.category,
              'url':origin()+'/artigo/'+quote(a.slug, safe=''),
              'image':newsletter_image_url(a.image)} for a in articles]
    content = '\n\n'.join(f"{card['title']}\n{card['summary']}\n{card['url']}" for card in cards)
    fingerprint = hashlib.sha256((subject+'\n'+json.dumps(cards,ensure_ascii=False,sort_keys=True)).encode()).hexdigest()
    period = start.strftime('%d/%m/%Y') + ' a ' + (end-timedelta(days=1)).strftime('%d/%m/%Y')
    return {'issue':issue, 'subject':subject, 'start':start, 'end':end,
            'articles':articles, 'cards':cards, 'period':period,
            'content':content, 'fingerprint':fingerprint}


def queue_digest(limit=500, expected_hash=None, now=None):
    if not smtp_ready():
        raise ValueError('Configure SMTP seguro e active NEWSLETTER_ENABLED antes de preparar o envio.')
    # Serialize issue preparation without adding tables or modifying subscribers.
    if db.engine.dialect.name == 'postgresql':
        db.session.execute(text('SELECT pg_advisory_xact_lock(1936949612)'))
    elif db.engine.dialect.name == 'sqlite':
        connection = db.session.connection().connection.driver_connection
        if not connection.in_transaction:
            db.session.execute(text('BEGIN IMMEDIATE'))
    edition = digest(now)
    if expected_hash is not None and expected_hash != edition['fingerprint']:
        raise ValueError('A selecção mudou. Reveja o boletim antes de o preparar.')
    if not edition['articles']:
        db.session.commit()
        return 0
    already_queued = exists(select(EditorialNotification.id).where(
        EditorialNotification.recipient == Subscriber.email,
        EditorialNotification.subject == edition['subject'],
    ))
    subscribers = Subscriber.query.filter_by(active=True).filter(~already_queued).order_by(
        Subscriber.id).limit(max(1, min(5000, limit))).all()
    for subscriber in subscribers:
        body = ('Boletim científico — Sussurros do Saber\n'
                + edition['start'].strftime('%d/%m/%Y') + ' a '
                + (edition['end']-timedelta(days=1)).strftime('%d/%m/%Y')
                + '\n\n' + edition['content']
                + '\n\nRecebe este boletim porque subscreveu o Sussurros do Saber.'
                + '\nCancelar a inscrição: ' + unsubscribe_url(subscriber))
        db.session.add(EditorialNotification(recipient=subscriber.email,
            subject=edition['subject'], body=body, html_body=render_digest_html(edition, subscriber)))
    db.session.commit()
    return len(subscribers)


@newsletter_bp.route('/boletim/cancelar/<token>', methods=['GET', 'POST'])
def unsubscribe(token):
    try:
        ident, created = URLSafeSerializer(current_app.secret_key, salt='newsletter-unsubscribe-v1').loads(token)
        if not isinstance(ident, int) or not 1 <= ident <= 2147483647:
            raise ValueError()
        subscriber = db.session.get(Subscriber, ident)
        if not subscriber or subscriber.created_at.isoformat() != created:
            raise ValueError()
    except (BadSignature, ValueError, TypeError):
        abort(400, description='Ligação de cancelamento inválida.')
    cancelled = request.method == 'POST'
    if cancelled:
        subscriber.active = False
        db.session.commit()
    response = current_app.make_response(render_template('newsletter_unsubscribe.html', cancelled=cancelled))
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


def install_newsletter(app):
    app.register_blueprint(newsletter_bp)

    @app.context_processor
    def newsletter_context():
        return {'newsletter_available': smtp_ready()}

    @app.cli.command('preparar-boletim')
    @click.option('--limit', default=500, type=click.IntRange(1, 5000))
    @click.option('--dry-run', is_flag=True, help='Mostrar a edição sem criar mensagens.')
    def prepare(limit, dry_run):
        """Queue the previous complete week's public articles, once per recipient."""
        if dry_run:
            edition = digest()
            click.echo(f"{edition['issue']}: {len(edition['articles'])} artigos; SMTP configurado: {smtp_ready()}.")
            return
        try:
            queued = queue_digest(limit)
        except ValueError as error:
            db.session.rollback()
            raise click.ClickException(str(error)) from error
        click.echo(f'{queued} boletins preparados na fila. Execute enviar-notificacoes para entregar.')
