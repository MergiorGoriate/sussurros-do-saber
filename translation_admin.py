"""Translation administration uses live existing mandates and explicit decisions."""
import hashlib
import json
import ast
from pathlib import Path
from functools import wraps
from flask import Blueprint, abort, redirect, render_template, request, session, current_app, send_file
import click
from models import db, Article, Journal, utcnow
from admin import enforce_admin_authentication, protect_admin_responses, validate_csrf
from governance import current_member, active_member, mandates
from translation_models import ContentTranslation as Translation, TranslationVersion as Version
from translation_models import TranslationEvent as Event, TranslationJob as Job, InterfaceTranslation, InterfaceBatch
import translation_service as service
from translation_limits import quota_summary, set_daily_limit
from translation_models import TranslationLimitChange
from dissemination_ai import GenerationError
from i18n_catalog import EN
from i18n_templates import SOURCES

translations_bp=Blueprint('translation_admin',__name__,url_prefix='/admin/internacionalizacao')
translations_bp.before_request(enforce_admin_authentication)
translations_bp.after_request(protect_admin_responses)


def can(action):
    if session.get('admin_superuser'):
        return True
    member=current_member()
    return bool(active_member(member) and any(a.journal_id is None and 'translations.'+action in (a.role.permissions or []) for a in mandates(member)))


def access(view):
    @wraps(view)
    def wrapped(*args,**kwargs):
        if not any(can(x) for x in ('manage','approve','publish')):
            abort(403)
        return view(*args,**kwargs)
    return wrapped


def require(action):
    if not can(action):
        abort(403)


@translations_bp.get('/documentacao')
@access
def documentation():
    return send_file(Path(current_app.root_path)/'docs/INTERNACIONALIZACAO_E_DIVULGACAO.md',
        mimetype='text/markdown; charset=utf-8',as_attachment=True,download_name='Internacionalizacao_e_Divulgacao.md')


@translations_bp.app_context_processor
def context():
    return dict(translation_can=can)


@translations_bp.get('/')
@access
def dashboard():
    query=request.args.get('q','').strip()[:150]
    kind=request.args.get('kind','article')
    if kind not in {'article','journal'}:
        abort(400)
    model=Article if kind=='article' else Journal
    results=model.query
    if query:
        results=results.filter(model.title.ilike('%'+query+'%'))
    try:
        page=max(1,int(request.args.get('page',1)))
    except ValueError:
        abort(400)
    records=results.order_by(model.updated_at.desc()).paginate(page=page,per_page=30,error_out=False)
    ids=[x.id for x in records.items]
    translations={x.source_id:x for x in Translation.query.filter(Translation.kind==kind,Translation.source_id.in_(ids))} if ids else {}
    statuses={ident:service.state(item) for ident,item in translations.items()}
    return render_template('admin/translations.html',records=records,translations=translations,statuses=statuses,
        states=service.STATES,kind=kind,query=query,configured=service.configured(),
        jobs=Job.query.order_by(Job.id.desc()).limit(60).all(),
        quota=quota_summary(), can_edit_limits=bool(session.get('admin_superuser')),
        limit_changes=TranslationLimitChange.query.order_by(TranslationLimitChange.id.desc()).limit(10).all()
            if session.get('admin_superuser') else [])


@translations_bp.post('/limite-diario')
@access
def update_daily_limit():
    if not session.get('admin_superuser'):
        abort(403)
    validate_csrf()
    try:
        set_daily_limit(request.form.get('daily_units', ''), request.form.get('limit_version'),
                        session.get('admin_id'), session.get('admin_username'))
        db.session.commit()
    except GenerationError as exc:
        db.session.rollback()
        abort(409, description=str(exc))
    return redirect('/admin/internacionalizacao/')


@translations_bp.post('/lote')
@access
def batch():
    require('manage');validate_csrf()
    try:
        ids=list(dict.fromkeys(int(x) for x in request.form.getlist('source_ids')))
        if not 1<=len(ids)<=20:
            raise GenerationError('Seleccione entre 1 e 20 artigos por lote.')
        for ident in ids:
            service.queue(request.form.get('kind','article'),ident,int(request.form.get('priority',50)))
        db.session.commit()
    except (ValueError,GenerationError) as exc:
        db.session.rollback();abort(400,description=str(exc))
    return redirect('/admin/internacionalizacao/')


@translations_bp.get('/<int:ident>')
@access
def detail(ident):
    item=db.get_or_404(Translation,ident)
    return render_template('admin/translation_detail.html',item=item,row=service.version(item),
        state=service.state(item),states=service.STATES,
        versions=Version.query.filter_by(translation_id=ident).order_by(Version.number.desc()).all(),
        events=Event.query.filter_by(translation_id=ident).order_by(Event.id.desc()).all())


@translations_bp.post('/<int:ident>/accao')
@access
def action(ident):
    validate_csrf()
    item=db.session.execute(db.select(Translation).where(Translation.id==ident).with_for_update()).scalar_one_or_none()
    if not item:
        abort(404)
    try:
        if int(request.form.get('version','-1'))!=item.version:
            raise GenerationError('A tradução mudou. Actualize a página.')
        operation=request.form.get('action');row=service.version(item)
        if operation=='generate':
            require('manage');service.queue(item.kind,item.source_id)
        elif operation=='edit':
            require('manage')
            if not row or item.state in {'pending','processing'} or service.stale(item,row):
                raise GenerationError('Aguarde a tarefa ou actualize primeiro a tradução desactualizada.')
            content={key:request.form.get(key,'') for key in row.source}
            service.validate(row.source,content)
            service.add_version(item,row.source,content,{'ready':False,'issues':['Revisão da correcção pendente.']})
            service.queue(item.kind,item.source_id,mode='review')
        elif operation=='approve':
            require('approve')
            if not row or item.state!='review' or not row.report.get('ready') or service.stale(item,row):
                raise GenerationError('Resolva os problemas da revisão preliminar e confirme que o original está actualizado.')
            if request.form.get('reviewed')!='yes':
                raise GenerationError('Confirme a revisão editorial da tradução.')
            item.state='approved';item.approved_version=item.version;item.reviewer_id=session.get('admin_id');item.reviewed_at=utcnow()
            item.reviewer_name=session.get('admin_username','Administrador principal')
            service.event(item,'approved')
        elif operation=='publish':
            require('publish')
            if item.state!='approved' or item.approved_version!=item.version or not row or service.stale(item,row):
                raise GenerationError('A publicação exige aprovação da versão actual e original actualizado.')
            if item.kind in {'article','journal'}:
                obj=db.session.get(Article if item.kind=='article' else Journal,item.source_id)
                if not obj or (obj.status!='published' if item.kind=='article' else not obj.published):
                    raise GenerationError('Publique primeiro o original. A tradução pode ser preparada e aprovada durante o processo editorial.')
            item.state='published';item.published_version=item.version;service.event(item,'published')
            if item.kind=='interface':
                for key,text in row.content.items():
                    interface_row=db.session.get(InterfaceTranslation,key)
                    interface_row.english=text;interface_row.published=True
                    interface_row.reviewer_id=session.get('admin_id');interface_row.updated_at=utcnow()
                    interface_row.pending_batch_id=None
        elif operation=='restore':
            require('manage')
            if item.state in {'pending','processing'}:
                raise GenerationError('Aguarde ou cancele a tarefa pendente.')
            old=Version.query.filter_by(translation_id=ident,number=int(request.form.get('number',0))).first()
            if not old:
                raise GenerationError('Versão não encontrada.')
            if old.source_hash!=service.digest(service.source(item.kind,item.source_id)):
                raise GenerationError('Esta versão corresponde a um original anterior. Gere uma versão actualizada.')
            service.add_version(item,old.source,old.content,{'ready':False,'issues':['Recuperação exige nova revisão.']})
            service.queue(item.kind,item.source_id,mode='review')
        else:
            abort(400)
        db.session.commit()
    except (ValueError,GenerationError) as exc:
        db.session.rollback();abort(409,description=str(exc))
    return redirect('/admin/internacionalizacao/'+str(ident))


@translations_bp.post('/tarefas/<int:ident>')
@access
def job_action(ident):
    require('manage');validate_csrf()
    job=db.session.execute(db.select(Job).where(Job.id==ident).with_for_update()).scalar_one_or_none()
    if not job:
        abort(404)
    operation=request.form.get('action')
    target={'pause':'paused','resume':'queued','cancel':'cancelled'}.get(operation)
    if not target or job.state not in ({'queued'} if operation=='pause' else {'paused'} if operation=='resume' else {'queued','paused'}):
        abort(409,description='Apenas tarefas pendentes podem ser suspensas ou canceladas.')
    job.state=target;item=db.session.get(Translation,job.translation_id)
    if operation=='cancel':
        item.state='review' if item.version else 'pending'
    service.event(item,'job_'+operation)
    db.session.commit();return redirect('/admin/internacionalizacao/')


def collect_interface():
    for name in current_app.jinja_env.list_templates():
        if not name.startswith(('admin/','emails/','i18n/')):
            current_app.jinja_env.get_template(name)
    for filename in ('app.py','reader_accounts.py','submissions.py','premium.py','premium_members.py','premium_features.py','premium_resources.py','billing.py'):
        module=ast.parse((Path(current_app.root_path)/filename).read_text())
        for node in ast.walk(module):
            if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id in {'KINDS','TYPES','FORMATS','INTERVALS','STATES'} for target in node.targets):
                try:
                    mapping=ast.literal_eval(node.value)
                    if isinstance(mapping,dict):
                        SOURCES.update(value for value in mapping.values() if isinstance(value,str) and value.strip())
                except (ValueError,TypeError):
                    pass
            if isinstance(node,ast.keyword) and node.arg in {'message','error','description'} and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):
                SOURCES.add(node.value.value)
            if isinstance(node,ast.Dict):
                for key,value in zip(node.keys,node.values):
                    if isinstance(key,ast.Constant) and key.value in {'message','error'} and isinstance(value,ast.Constant) and isinstance(value.value,str):
                        SOURCES.add(value.value)
    # Public product descriptions are presentation text, never prices, plan IDs or entitlements.
    from premium_models import PremiumPlan, PremiumContent, PremiumPlanTerms
    from models import Author, EditorialPolicy
    for plan in PremiumPlan.query.filter_by(active=True):
        SOURCES.update(value for value in (plan.name,plan.description) if value.strip())
        SOURCES.update(value for value in (plan.benefits or []) if isinstance(value,str) and value.strip())
    for content in PremiumContent.query.filter_by(published=True):
        SOURCES.update(value for value in (content.title,content.summary,content.category) if value.strip())
    # Only public presentation fields enter the catalogue, never identities,
    # payment values, private submissions or the body of scientific manuscripts.
    for model,fields in ((EditorialPolicy,('page_title','page_description','page_content',
            'author_guidelines','reviewer_guidelines','ethics_policy','ai_policy',
            'data_policy','fees_policy','open_access_policy')),
            (PremiumPlanTerms,('renewal','cancellation','refund','limitations'))):
        for row in model.query:
            SOURCES.update(value for field in fields if (value:=getattr(row,field,'')) and value.strip())
    for author in Author.query.filter_by(active=True):
        SOURCES.update(value for field in ('role','headline','academic_background','bio','interests',
            'projects','editorial_experience') if (value:=getattr(author,field,'')) and value.strip())
    for text in sorted(SOURCES):
        key=hashlib.sha256(text.encode()).hexdigest()
        if not db.session.get(InterfaceTranslation,key):
            translated=EN.get(text) or EN.get(' '.join(text.split())) or ''
            db.session.add(InterfaceTranslation(key=key,source=text,english=translated,published=bool(translated)))
    db.session.commit()


@translations_bp.route('/interface',methods=['GET','POST'])
@access
def interface():
    if request.method=='POST':
        validate_csrf()
        if request.form.get('action')=='collect':
            require('manage');collect_interface()
        elif request.form.get('action')=='generate':
            require('manage')
            selected=InterfaceTranslation.query.filter_by(published=False,pending_batch_id=None).order_by(InterfaceTranslation.key).limit(20).all()
            if not selected:
                abort(409,description='Não existem textos novos por traduzir. Consulte os lotes em curso.')
            batch=InterfaceBatch(keys=[row.key for row in selected]);db.session.add(batch);db.session.flush()
            for row in selected:
                row.pending_batch_id=batch.id
            try:
                item=service.queue('interface',batch.id);db.session.commit()
            except GenerationError as exc:
                db.session.rollback();abort(409,description=str(exc))
            return redirect('/admin/internacionalizacao/'+str(item.id))
        else:
            require('approve');require('publish')
            row=db.session.get(InterfaceTranslation,request.form.get('key',''))
            if not row:
                abort(404)
            text=request.form.get('english','').strip()
            if not text or len(text)>20000 or request.form.get('reviewed')!='yes':
                abort(400)
            # UI translations are plain text; no HTML, script or Jinja can be injected.
            row.english=text;row.published=True;row.reviewer_id=session.get('admin_id');row.updated_at=utcnow()
            db.session.commit()
        return redirect('/admin/internacionalizacao/interface')
    try:
        page=max(1,int(request.args.get('page',1)))
    except ValueError:
        abort(400)
    q=InterfaceTranslation.query
    if request.args.get('missing','1')=='1':
        q=q.filter_by(published=False)
    return render_template('admin/interface_translations.html',rows=q.order_by(InterfaceTranslation.source).paginate(page=page,per_page=20,error_out=False),
        total=InterfaceTranslation.query.count(),missing=InterfaceTranslation.query.filter_by(published=False).count(),
        batches=Translation.query.filter_by(kind='interface').order_by(Translation.id.desc()).limit(30).all(),states=service.STATES)


def register_cli(app):
    @app.cli.command('processar-traducoes')
    @click.option('--limit',type=click.IntRange(1,10),default=1)
    def worker(limit):
        count=0
        for _ in range(limit):
            if not service.process_one():
                break
            count+=1
        click.echo(f'{count} tarefa(s) de tradução processada(s).')
