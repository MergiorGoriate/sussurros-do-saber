"""Workflow invariants, source grounding, cost reservations and durable worker."""
import copy
import hashlib
import json
import os
import re
import secrets
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit
import requests
from flask import current_app, session, has_request_context
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from models import db, Article, Journal, utcnow
from dissemination_models import (DisseminationMaterial as Material, DisseminationVersion as Version,
    DisseminationEvent as Event, DisseminationJob as Job, DisseminationBudget as Budget)
from dissemination_ai import GenerationError
import dissemination_ai as ai
from dissemination_render import compose

NETWORKS = {'facebook': 'Facebook', 'instagram': 'Instagram', 'bluesky': 'Bluesky', 'x': 'X', 'reddit': 'Reddit'}
KINDS = {'curiosity': 'Imagem de curiosidade', 'infographic': 'Infográfico conceptual',
         'carousel': 'Carrossel educativo', 'poster': 'Cartaz de descoberta', 'text': 'Texto de divulgação'}
STATES = {'generating': 'Em geração', 'review': 'A aguardar revisão', 'correction': 'Em correcção',
          'approved': 'Aprovado', 'published': 'Publicado', 'rejected': 'Rejeitado', 'failed': 'Falha na geração'}
CAPTION_LIMITS = {'facebook': 3000, 'instagram': 1800, 'bluesky': 200, 'x': 180, 'reddit': 5000}


def integer_setting(name, default=None):
    try:
        value = int(os.getenv(name, str(default) if default is not None else ''))
        if not 1 <= value <= 1_000_000:
            raise ValueError()
        return value
    except ValueError as exc:
        raise GenerationError('Configure limites inteiros positivos: ' + name) from exc


def snapshot(kind, ident):
    if kind == 'portal_en':
        from translation_service import published, stale
        translation,row=published('article',ident)
        item=Article.public_query().filter_by(id=ident).first()
        if not item or not row or stale(translation,row):
            raise GenerationError('A versão inglesa não está publicada ou precisa de actualização.')
        source=dict(kind=kind,id=item.id,title=row.content['title'],
            body=row.content['summary']+'\n'+row.content['body'],references=row.content['references'],
            path='/en/artigo/'+quote(item.slug,safe=''),language='en',translation_version=row.number)
    elif kind == 'portal':
        item = Article.public_query().populate_existing().filter_by(id=ident).first()
        if not item:
            raise GenerationError('O artigo de origem deixou de estar publicado.')
        source = dict(kind=kind, id=item.id, title=item.title, body=item.summary + '\n' + item.body,
                      references=item.references or '', path='/artigo/' + quote(item.slug, safe=''))
    elif kind == 'journal':
        item = Journal.query.populate_existing().filter_by(id=ident, published=True).first()
        if not item or not (item.content_markdown or '').strip():
            raise GenerationError('O artigo científico não está publicado ou não tem conteúdo.')
        source = dict(kind=kind, id=item.id, title=item.article_title or item.title,
                      body=(item.description or '') + '\n' + item.content_markdown, references=item.references or '',
                      path='/revistas/' + quote(item.slug, safe=''))
    else:
        raise GenerationError('Origem inválida.')
    if len(source['body']) + len(source['references']) > 60_000:
        raise GenerationError('O artigo excede o limite de análise de 60 000 caracteres. Não foi truncado.')
    source['fingerprint'] = hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return source


def current_version(material):
    return Version.query.filter_by(material_id=material.id, number=material.version).first()


def event(material, action, detail=''):
    db.session.add(Event(material_id=material.id, version=material.version, action=action,
        state=material.status, detail=detail[:4000],
        actor_id=session.get('admin_id') if has_request_context() else None,
        actor_name=session.get('admin_username', 'Administrador autorizado') if has_request_context() else 'Trabalhador assíncrono'))


def invalidate(material):
    if material.approved_version is not None:
        material.token = secrets.token_urlsafe(24)
    material.approved_version = None
    material.approved_by = None
    material.approved_at = None
    material.publication_url = ''


def reserve(require_images=True):
    issues = ai.configuration_issues(require_images)
    if issues:
        raise GenerationError(' '.join(issues))
    units = integer_setting('DISSEMINATION_JOB_UNITS')
    limit = integer_setting('DISSEMINATION_DAILY_UNITS')
    jobs = integer_setting('DISSEMINATION_DAILY_JOBS', 20)
    day = utcnow().date()
    # Insert once, then reserve with a single conditional UPDATE on both databases.
    if not db.session.get(Budget, day):
        try:
            with db.session.begin_nested():
                db.session.add(Budget(day=day, units=0, jobs=0))
                db.session.flush()
        except IntegrityError:
            pass
    result = db.session.execute(update(Budget).where(Budget.day == day,
        Budget.units + units <= limit, Budget.jobs < jobs).values(units=Budget.units + units, jobs=Budget.jobs + 1))
    if result.rowcount != 1:
        raise GenerationError('Limite diário de utilização atingido. Não foi efectuada uma chamada à IA.')
    return units


def enqueue(material, mode='generate', instruction=''):
    units = reserve(require_images=material.kind != 'text')
    material.status = 'generating'
    material.error = ''
    invalidate(material)
    db.session.add(Job(material_id=material.id, reserved_units=units, mode=mode, instruction=instruction[:2000]))
    event(material, 'queued', instruction)


def create(kind, ident, network, output):
    if network not in NETWORKS or output not in KINDS:
        raise GenerationError('Rede social ou formato inválido.')
    snapshot(kind, ident)
    material = Material(source_kind=kind, source_id=ident, network=network, kind=output,
                        created_by=session.get('admin_id'), token=secrets.token_urlsafe(24))
    db.session.add(material)
    db.session.flush()
    enqueue(material)
    return material


def validate_payload(payload, source, material):
    """Fail closed on malformed structure, ungrounded quotations and missing slides."""
    issues = []
    if not isinstance(payload, dict):
        raise GenerationError('Estrutura do material inválida.')
    for key, maximum in (('title', 90), ('caption', CAPTION_LIMITS[material.network]), ('illustration', 2000)):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise GenerationError('Campo inválido ou demasiado longo: ' + key)
    if material.network in {'x', 'bluesky'}:
        complete = payload['title'] + '\n\n' + payload['caption'] + '\n\n' + tracking_url(material)
        if len(complete) > (280 if material.network == 'x' else 300):
            raise GenerationError('Encurte o título e a legenda para caberem com a ligação na rede seleccionada.')
    if payload.get('layout') not in {'balanced', 'compact'} or payload.get('accent') not in {'teal', 'blue', 'purple'}:
        raise GenerationError('Composição visual inválida.')
    if payload.get('visual_label') not in {'Ilustração conceptual', 'Reconstrução hipotética'}:
        raise GenerationError('Identifique a representação conceptual ou hipotética.')
    claims = payload.get('claims')
    if not isinstance(claims, list) or not 1 <= len(claims) <= 8:
        raise GenerationError('O material deve incluir entre 1 e 8 afirmações fundamentadas.')
    full = source['title'] + '\n' + source['body'] + '\n' + source['references']
    for index, claim in enumerate(claims):
        if not isinstance(claim, dict) or not all(isinstance(claim.get(k), str) and claim[k].strip() for k in ('text', 'evidence')):
            raise GenerationError('Afirmação sem texto ou evidência.')
        if len(claim['text']) > 600 or len(claim['evidence']) > 2000:
            raise GenerationError('Afirmação ou evidência demasiado longa.')
        if len(claim['evidence']) < 15 or claim['evidence'] not in full:
            issues.append(f'Afirmação {index + 1}: o trecho de suporte não foi encontrado literalmente no artigo.')
        for number in re.findall(r'\d+(?:[.,]\d+)?', claim['text']):
            if number not in claim['evidence']:
                issues.append(f'Afirmação {index + 1}: valor numérico sem suporte no trecho citado.')
    slides = payload.get('slides')
    expected = range(3, 6) if material.kind == 'carousel' else [1]
    if not isinstance(slides, list) or len(slides) not in expected:
        raise GenerationError('Número de slides incompatível com o formato.')
    for slide in slides:
        if not isinstance(slide, dict):
            raise GenerationError('Slide inválido.')
        for key, maximum in (('heading', 70), ('body', 240)):
            if not isinstance(slide.get(key), str) or not slide[key].strip() or len(slide[key]) > maximum:
                raise GenerationError('Texto de slide inválido ou demasiado longo.')
        ids = slide.get('claim_ids')
        if not isinstance(ids, list) or not ids or any(type(i) is not int or i < 0 or i >= len(claims) for i in ids):
            raise GenerationError('Slide sem ligação válida às afirmações científicas.')
    return issues


def checked_report(source, payload, material, images):
    issues = validate_payload(payload, source, material)
    report = ai.review(source, payload, images)
    checks = report.get('claim_checks')
    valid = (isinstance(checks, list) and len(checks) == len(payload['claims'])
        and all(isinstance(c, dict) and type(c.get('id')) is int and type(c.get('supported')) is bool
                and isinstance(c.get('reason'), str) for c in checks)
        and sorted(c['id'] for c in checks) == list(range(len(payload['claims'])))
        and isinstance(report.get('issues'), list) and all(isinstance(i, str) for i in report['issues'])
        and all(type(report.get(k)) is bool for k in ('scientific_ok', 'language_ok', 'visual_ok')))
    if not valid:
        raise GenerationError('A revisão automática está incompleta. A aprovação foi bloqueada.')
    report['issues'] = (issues + report['issues'])[:40]
    report['ready'] = (not report['issues'] and all(report[k] for k in ('scientific_ok', 'language_ok', 'visual_ok'))
                       and all(c['supported'] for c in checks))
    report['disclaimer'] = 'Verificação preliminar por IA; exige revisão humana e não garante exactidão científica.'
    return report


def asset_root():
    root = Path(os.getenv('DISSEMINATION_STORAGE_DIR', str(Path(current_app.instance_path) / 'dissemination'))).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def save_asset(raw):
    name = secrets.token_hex(24) + '.png'
    path = asset_root() / name
    with path.open('xb') as stream:
        stream.write(raw)
    path.chmod(0o600)
    return {'name': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def read_asset(asset):
    if not re.fullmatch(r'[a-f0-9]{48}\.png', asset.get('name', '')):
        raise GenerationError('Identificador do recurso inválido.')
    raw = (asset_root() / asset['name']).read_bytes()
    if hashlib.sha256(raw).hexdigest() != asset['sha256']:
        raise GenerationError('O ficheiro foi alterado. Solicite nova geração e revisão.')
    return raw


def add_version(material, source, payload, report, assets):
    material.version += 1
    row = Version(material_id=material.id, number=material.version, source=source,
        payload=copy.deepcopy(payload), report=report, assets=assets,
        actor_id=session.get('admin_id') if has_request_context() else None)
    db.session.add(row)
    invalidate(material)
    return row


def origin():
    value = current_app.config.get('DISSEMINATION_SITE_URL') or os.getenv('SITE_URL', 'https://sussurrosdosaber.com')
    parts = urlsplit(value)
    if parts.scheme != 'https' or not parts.netloc or parts.username or parts.query or parts.fragment or parts.path not in ('', '/'):
        raise GenerationError('SITE_URL deve ser uma origem HTTPS válida, sem caminho.')
    return value.rstrip('/')


def destination(material, source):
    return origin() + source['path'] + '?' + urlencode(dict(utm_source=material.network,
        utm_medium='social', utm_campaign='divulgacao_' + str(material.id), utm_content='v' + str(material.version)))


def tracking_url(material):
    return origin() + '/divulgacao/' + material.token


def check_source(material, version):
    source = snapshot(material.source_kind, material.source_id)
    if source['fingerprint'] != version.source['fingerprint']:
        raise GenerationError('O artigo foi alterado. Regenere o material para nova revisão.')
    return source


def verify_link(material, version):
    source = check_source(material, version)
    try:
        # Only a trusted server-configured origin plus a DB-derived path. No arbitrary user URLs.
        response = requests.get(origin() + source['path'], timeout=(5, 10), allow_redirects=False, stream=True)
        try:
            if response.status_code != 200:
                raise GenerationError('A ligação pública do artigo não devolveu HTTP 200.')
        finally:
            response.close()
    except requests.RequestException as exc:
        raise GenerationError('Não foi possível verificar a ligação pública do artigo.') from exc
    return source


def export_allowed(material, version):
    if version is None or material.status not in {'approved', 'published'} or material.approved_version != material.version or not material.approved_at:
        raise GenerationError('A exportação exige aprovação da versão actual.')
    check_source(material, version)
    for asset in version.assets:
        read_asset(asset)


def process_one():
    job_id = db.session.execute(select(Job.id).where(Job.status == 'queued').order_by(Job.id).limit(1)).scalar()
    if job_id is None:
        return False
    claimed = db.session.execute(update(Job).where(Job.id == job_id, Job.status == 'queued')
        .values(status='running', started_at=utcnow()))
    db.session.commit()
    if claimed.rowcount != 1:
        return False
    job = db.session.get(Job, job_id)
    material = db.session.get(Material, job.material_id)
    try:
        issues = ai.configuration_issues(require_images=material.kind != 'text' and job.mode != 'review')
        if issues:
            raise GenerationError('Configuração do trabalhador: ' + ' '.join(issues))
        source = snapshot(material.source_kind, material.source_id)
        previous = current_version(material)
        if job.mode == 'review':
            if not previous or source['fingerprint'] != previous.source['fingerprint']:
                raise GenerationError('O artigo de origem mudou durante a correcção. Solicite nova geração.')
            payload = copy.deepcopy(previous.payload)
            art = read_asset(previous.assets[0]) if previous.assets and previous.assets[0].get('role') == 'illustration' else None
        else:
            payload = ai.generate(source, material.network, material.kind, job.instruction)
            if source.get('language')=='en':
                payload['language']='en'
            validate_payload(payload, source, material)
            art = ai.illustration(payload['illustration']) if material.kind != 'text' else None
        images = compose(payload, material.network, art, current_app.static_folder, kind=material.kind) if material.kind != 'text' else []
        report = checked_report(source, payload, material, images)
        # A cancelled/expired worker must never replace a newer job's material.
        job = db.session.execute(select(Job).where(Job.id == job_id).with_for_update()
            .execution_options(populate_existing=True)).scalar_one()
        material = db.session.execute(select(Material).where(Material.id == job.material_id).with_for_update()
            .execution_options(populate_existing=True)).scalar_one()
        if job.status != 'running' or material.status != 'generating':
            db.session.rollback()
            return True
        # Do not approve against a source edited while the provider was working.
        if snapshot(material.source_kind, material.source_id)['fingerprint'] != source['fingerprint']:
            raise GenerationError('O artigo mudou durante a geração. Repita a operação.')
        assets = []
        if art:
            assets.append(dict(save_asset(art), role='illustration'))
        for image in images:
            assets.append(dict(save_asset(image), role='slide'))
        add_version(material, source, payload, report, assets)
        material.status = 'review'
        material.error = ''
        event(material, 'generated' if job.mode == 'generate' else 'reviewed', 'Verificação preliminar concluída; aprovação humana pendente.')
        job.status = 'done'
    except Exception as exc:
        db.session.rollback()
        material = db.session.get(Material, job.material_id)
        job = db.session.get(Job, job_id)
        material.status = 'failed'
        invalidate(material)
        material.error = str(exc) if isinstance(exc, GenerationError) else 'Falha interna na geração. Consulte os registos operacionais.'
        event(material, 'failed', material.error)
        job.status = 'failed'
        # Never log exception bodies: third-party errors can contain keys or content.
        current_app.logger.warning('Dissemination job %s failed (%s)', job_id, type(exc).__name__)
    job.finished_at = utcnow()
    db.session.commit()
    return True


def expire_jobs():
    stale = Job.query.filter(Job.status == 'running', Job.started_at < utcnow() - timedelta(minutes=30)).all()
    for job in stale:
        result = db.session.execute(update(Job).where(Job.id == job.id, Job.status == 'running')
            .values(status='failed', finished_at=utcnow()))
        if result.rowcount:
            material = db.session.get(Material, job.material_id)
            material.status = 'failed'
            invalidate(material)
            material.error = 'Trabalhador interrompido. A tentativa pode ter gerado custos; não há repetição automática.'
            event(material, 'worker_expired', material.error)
    db.session.commit()

