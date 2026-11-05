"""Administrative UI and approved-only exports. Phase one has no social API sender."""
import copy
import io
import json
import secrets
import zipfile
from pathlib import Path
from functools import wraps
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from datetime import timezone
import click
from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   session, send_file, current_app)
from admin import enforce_admin_authentication, protect_admin_responses, validate_csrf
from extensions import limiter
from governance import current_member, mandates, active_member
from models import db, Article, Journal, utcnow
from dissemination_models import DisseminationMaterial as Material, DisseminationVersion as Version
from dissemination_models import (DisseminationEvent as Event, DisseminationClick as Click,
    DisseminationBudget as Budget, DisseminationJob as Job)
from dissemination_ai import GenerationError, configured, configuration_issues
import dissemination_service as service

centre_bp = Blueprint('dissemination', __name__, url_prefix='/admin/divulgacao')
tracking_bp = Blueprint('dissemination_tracking', __name__)
centre_bp.before_request(enforce_admin_authentication)
centre_bp.after_request(protect_admin_responses)


def can(action):
    # No legacy account fallback. Only explicit, general accepted mandates or primary admin.
    if session.get('admin_superuser'):
        return True
    member = current_member()
    return bool(active_member(member) and any(
        a.journal_id is None and 'dissemination.' + action in (a.role.permissions or []) for a in mandates(member)))


def access(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not any(can(action) for action in ('manage', 'approve', 'publish')):
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def require(action):
    if not can(action):
        abort(403)


@centre_bp.get('/documentacao')
@access
def documentation():
    return send_file(Path(current_app.root_path) / 'docs/CENTRO_DIVULGACAO_CIENTIFICA.md',
        mimetype='text/markdown; charset=utf-8', as_attachment=True,
        download_name='Centro_de_Divulgacao_Cientifica.md')


@centre_bp.app_context_processor
def context():
    def local_time(value):
        return value.replace(tzinfo=timezone.utc).astimezone(ZoneInfo('Africa/Maputo')).strftime('%d/%m/%Y %H:%M') if value else '—'
    return {'dissemination_can': can, 'dissemination_time': local_time}


@centre_bp.get('/')
@access
def dashboard():
    from translation_models import ContentTranslation
    search = request.args.get('q', '').strip()[:120]
    portal = Article.public_query()
    journals = Journal.query.filter(Journal.published.is_(True), Journal.content_markdown.isnot(None), db.func.trim(Journal.content_markdown) != '')
    if search:
        portal = portal.filter(Article.title.ilike('%' + search + '%'))
        journals = journals.filter(db.or_(Journal.article_title.ilike('%' + search + '%'), Journal.title.ilike('%' + search + '%')))
    try:
        page = max(1, min(100000, int(request.args.get('page', 1))))
    except ValueError:
        abort(400)
    return render_template('admin/dissemination.html', search=search,
        english_ids={x.source_id for x in ContentTranslation.query.filter(ContentTranslation.kind=='article',ContentTranslation.published_version.isnot(None))},
        portal=portal.order_by(Article.id.desc()).limit(40).all(),
        journals=journals.order_by(Journal.id.desc()).limit(40).all(),
        materials=Material.query.order_by(Material.id.desc()).paginate(page=page, per_page=20, error_out=False),
        states=service.STATES, kinds=service.KINDS, networks=service.NETWORKS,
        configured=configured(require_images=False), images_configured=configured(),
        configuration_issues=configuration_issues(require_images=False),
        queued_jobs=Job.query.filter_by(status='queued').count(),
        budget=db.session.get(Budget, utcnow().date()))


@centre_bp.post('/gerar')
@limiter.limit('10 per minute')
@access
def generate():
    require('manage')
    validate_csrf()
    try:
        kind, ident = request.form.get('source', '').split(':', 1)
        material = service.create(kind, int(ident), request.form.get('network'), request.form.get('kind'))
        db.session.commit()
    except (GenerationError, ValueError) as exc:
        db.session.rollback()
        abort(400, description=str(exc) if isinstance(exc, GenerationError) else 'Seleccione um artigo publicado.')
    flash('Geração colocada na fila. Actualize esta página para acompanhar o resultado.', 'success')
    return redirect('/admin/divulgacao/' + str(material.id))


@centre_bp.get('/<int:ident>')
@access
def detail(ident):
    from dissemination_video import DisseminationVideo
    material = db.get_or_404(Material, ident)
    version = service.current_version(material)
    assets_available = True
    if version:
        try:
            for asset in version.assets:
                service.read_asset(asset)
        except (GenerationError, OSError):
            assets_available = False
    try:
        public_link = service.tracking_url(material) if material.status in {'approved', 'published'} else ''
        if version and public_link:
            service.export_allowed(material, version)
    except (GenerationError, OSError):
        public_link = ''
    return render_template('admin/dissemination_detail.html', material=material, version=version,
        videos=DisseminationVideo.query.filter_by(material_id=ident).order_by(DisseminationVideo.id.desc()).all(),
        states=service.STATES, kinds=service.KINDS, networks=service.NETWORKS, public_link=public_link,
        assets_available=assets_available,
        versions=Version.query.filter_by(material_id=ident).order_by(Version.number.desc()).all(),
        events=Event.query.filter_by(material_id=ident).order_by(Event.id.desc()).all(),
        clicks=Click.query.filter_by(material_id=ident).count())


@centre_bp.post('/<int:ident>/accao')
@access
def action(ident):
    validate_csrf()
    material = db.session.execute(db.select(Material).where(Material.id == ident).with_for_update()).scalar_one_or_none()
    if not material:
        abort(404)
    try:
        expected = int(request.form.get('version', '-1'))
    except ValueError:
        abort(400)
    if expected != material.version:
        abort(409, description='O material mudou. Actualize a página antes de decidir.')
    version = service.current_version(material)
    operation = request.form.get('action')
    note = request.form.get('note', '').strip()[:2000]
    try:
        if operation in {'approve', 'reject'}:
            require('approve')
            if not version or material.status not in {'review', 'correction'}:
                raise GenerationError('O material não está disponível para decisão editorial.')
            if operation == 'approve':
                if material.status != 'review' or version.report.get('ready') is not True:
                    raise GenerationError('Resolva os problemas da verificação preliminar antes da aprovação.')
                if request.form.get('human_review') != 'yes':
                    raise GenerationError('Confirme a revisão científica, linguística e visual.')
                service.verify_link(material, version)
                for asset in version.assets:
                    service.read_asset(asset)
                material.status = 'approved'
                material.approved_version = material.version
                material.approved_by = session.get('admin_id')
                material.approved_at = utcnow()
                material.token = secrets.token_urlsafe(24)
                service.event(material, 'approved', 'Revisão humana confirmada; ligação pública verificada.')
            else:
                if not note:
                    raise GenerationError('Registe o motivo da rejeição.')
                material.status = 'rejected'
                service.invalidate(material)
                service.event(material, 'rejected', note)
        elif operation == 'correct':
            if not (can('manage') or can('approve')):
                abort(403)
            if material.status not in {'review', 'approved', 'published'} or not note:
                raise GenerationError('Indique as correcções necessárias num material disponível para revisão.')
            material.status = 'correction'
            service.invalidate(material)
            service.event(material, 'correction_requested', note)
        elif operation in {'regenerate', 'edit', 'restore'}:
            require('manage')
            if material.status not in {'review', 'correction', 'failed'}:
                raise GenerationError('Solicite primeiro correcção. Materiais rejeitados permanecem bloqueados.')
            if operation == 'regenerate':
                service.enqueue(material, instruction=note)
            else:
                if not version:
                    raise GenerationError('Não há versão para corrigir.')
                base = version
                if operation == 'restore':
                    base = Version.query.filter_by(material_id=ident, number=int(request.form.get('restore_version', '0'))).first()
                    if not base:
                        raise GenerationError('Versão anterior não encontrada.')
                    payload = copy.deepcopy(base.payload)
                else:
                    payload = copy.deepcopy(version.payload)
                    payload.update(title=request.form.get('title', '').strip(), caption=request.form.get('caption', '').strip(),
                                   layout=request.form.get('layout'), accent=request.form.get('accent'),
                                   visual_label=request.form.get('visual_label'))
                    for index, slide in enumerate(payload['slides']):
                        slide['heading'] = request.form.get('heading_' + str(index), '').strip()
                        slide['body'] = request.form.get('body_' + str(index), '').strip()
                    for index, claim in enumerate(payload['claims']):
                        claim['text'] = request.form.get('claim_' + str(index), '').strip()
                        claim['evidence'] = request.form.get('evidence_' + str(index), '').strip()
                source = service.snapshot(material.source_kind, material.source_id)
                service.validate_payload(payload, source, material)
                # Preserve immutable image assets; worker recomposes and reviews edited text.
                service.add_version(material, source, payload, {'ready': False, 'issues': ['Nova revisão pendente.']}, base.assets)
                material.status = 'correction'
                service.event(material, 'restored' if operation == 'restore' else 'edited', note or 'Correcção manual; aprovação anterior invalidada.')
                service.enqueue(material, mode='review')
        elif operation == 'published':
            require('publish')
            service.export_allowed(material, version)
            if material.status != 'approved':
                raise GenerationError('A publicação já foi registada ou não está aprovada.')
            address = request.form.get('publication_url', '').strip()
            hosts = {'facebook': {'facebook.com', 'www.facebook.com', 'm.facebook.com'},
                     'instagram': {'instagram.com', 'www.instagram.com'}, 'bluesky': {'bsky.app'},
                     'x': {'x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'},
                     'reddit': {'reddit.com', 'www.reddit.com', 'old.reddit.com'}}
            parts = urlsplit(address)
            if len(address) > 1000 or parts.scheme != 'https' or parts.hostname not in hosts[material.network] or parts.username or parts.password or parts.port not in (None, 443):
                raise GenerationError('Indique uma ligação HTTPS da publicação na rede social seleccionada.')
            material.publication_url = address
            material.status = 'published'
            service.event(material, 'publication_reported', address + '\nPublicação manual declarada pelo administrador; não confirmada por API.')
        else:
            abort(400)
        db.session.commit()
    except (GenerationError, ValueError, OSError) as exc:
        db.session.rollback()
        abort(409, description=str(exc) if isinstance(exc, GenerationError) else 'Não foi possível concluir a operação. Verifique os dados e os ficheiros.')
    return redirect('/admin/divulgacao/' + str(ident))


@centre_bp.get('/<int:ident>/imagem/<int:number>/<int:index>')
@access
def preview(ident, number, index):
    version = Version.query.filter_by(material_id=ident, number=number).first_or_404()
    assets = [a for a in version.assets if a.get('role') == 'slide']
    if index < 1 or index > len(assets):
        abort(404)
    try:
        raw = service.read_asset(assets[index - 1])
    except (GenerationError, OSError):
        abort(404)
    response = send_file(io.BytesIO(raw), mimetype='image/png')
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@centre_bp.get('/<int:ident>/descarregar')
@access
def download(ident):
    require('publish')
    material = db.get_or_404(Material, ident)
    version = service.current_version(material)
    try:
        service.export_allowed(material, version)
        link = service.tracking_url(material)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('texto.txt', version.payload['title'] + '\n\n' + version.payload['caption'] + '\n\n' + link)
            archive.writestr('revisao.json', json.dumps(dict(source=version.source, report=version.report,
                version=version.number, approved_by=material.approved_by,
                approved_at=material.approved_at.isoformat(), link=link), ensure_ascii=False, indent=2))
            for index, asset in enumerate(a for a in version.assets if a.get('role') == 'slide'):
                archive.writestr(f'slide-{index + 1}.png', service.read_asset(asset))
        service.event(material, 'downloaded', 'Pacote aprovado descarregado.')
        db.session.commit()
        stream.seek(0)
        return send_file(stream, mimetype='application/zip', as_attachment=True, download_name=f'divulgacao-{ident}-v{material.version}.zip')
    except (GenerationError, OSError) as exc:
        db.session.rollback()
        abort(409, description=str(exc) if isinstance(exc, GenerationError) else 'Ficheiro indisponível.')


@tracking_bp.route('/divulgacao/<token>', methods=['GET', 'HEAD'])
@limiter.limit('120 per minute')
def track(token):
    material = Material.query.filter_by(token=token).first_or_404()
    version = service.current_version(material)
    try:
        if not version or material.status not in {'approved', 'published'} or material.approved_version != version.number:
            abort(404)
        source = service.check_source(material, version)
    except GenerationError:
        abort(404)
    agent = request.headers.get('User-Agent', '').lower()
    prefetch = request.headers.get('Purpose', '') + request.headers.get('Sec-Purpose', '')
    if request.method == 'GET' and agent and not any(word in agent for word in ('bot', 'crawler', 'spider', 'preview')) and 'prefetch' not in prefetch:
        db.session.add(Click(material_id=material.id, version=material.version))
        db.session.commit()
    response = redirect(service.destination(material, source), code=302)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


def register_cli(app):
    @app.cli.command('diagnosticar-divulgacao')
    def diagnose():
        """Local configuration and queue inspection; no provider calls or secret values."""
        issues = configuration_issues()
        for issue in issues:
            click.echo(issue)
        if not issues:
            click.echo('Variáveis locais válidas. A ligação à IA ainda não foi testada.')
        for status in ('queued', 'running', 'failed', 'done'):
            click.echo(f'{status}: {Job.query.filter_by(status=status).count()}')
        oldest = Job.query.filter_by(status='queued').order_by(Job.id).first()
        if oldest:
            click.echo('Há tarefas na fila. Confirme o agendamento de processar-divulgacao neste serviço.')
        try:
            import tempfile
            from dissemination_render import font
            with tempfile.TemporaryFile(dir=service.asset_root()) as probe:
                probe.write(b'cdc-storage-probe')
                probe.flush()
            font(24)
            logo = Path(current_app.static_folder) / 'img/logo-sussurros-light.png'
            if not logo.is_file():
                raise GenerationError('O logotipo oficial não está disponível.')
            click.echo('Armazenamento local, fonte e ficheiro do logotipo disponíveis.')
            click.echo('Confirme que web e trabalhador usam a mesma base de dados e o mesmo volume persistente.')
        except (OSError, GenerationError):
            issues.append('Verifique permissões do armazenamento, fonte e logotipo neste serviço.')
            click.echo(issues[-1])
        if issues:
            raise click.ClickException('Diagnóstico local com pendências. Nenhuma chamada à IA foi efectuada.')

    @app.cli.command('processar-divulgacao')
    @click.option('--limit', type=click.IntRange(1, 20), default=2)
    def worker(limit):
        """Process bounded durable jobs outside public HTTP workers."""
        service.expire_jobs()
        count = 0
        for _ in range(limit):
            if not service.process_one():
                break
            count += 1
        click.echo(f'{count} tarefa(s) processada(s). Consulte o painel para decisões e falhas.')

