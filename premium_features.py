"""Management and member tools attached only to the existing Premium blueprints."""
import csv
import io
import json
import secrets
from datetime import datetime, timedelta
from html import escape

import click
from flask import abort, current_app, flash, g, redirect, render_template, request, send_file, session, url_for
from sqlalchemy import or_, select, update, func
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.exc import IntegrityError

from admin import validate_csrf, superadmin_required, csv_safe_cell
from models import db, utcnow, AdminUser
from submission_models import Researcher
from premium_models import (PremiumContent, PremiumResource, PremiumFile, PremiumLesson, PremiumProgress,
    PremiumEvent, PremiumRegistration, PremiumCollectionItem, PremiumCertificate, PremiumSetting,
    PremiumStaff, PremiumPlanTerms, PremiumPlan, PremiumSubscription, PremiumUsage, PremiumCategory)
from premium_access import required, can, PERMISSIONS
from premium_resources import (detail, require_access, reader, record_usage, integer, epub_chapters,
                               TYPES, STATES, local_input, visible_clause)
from premium_settings import settings, terms, notify, NOTIFICATIONS


SECTIONS = [('catalogo','Biblioteca Exclusiva','content'),('cursos','Cursos e Formações','content'),
    ('videos','Vídeos e Séries','content'),('eventos','Eventos e Seminários','events'),
    ('coleccoes','Colecções de Aprendizagem','content'),('planos','Planos e Preços','plans'),
    ('beneficios','Benefícios','plans'),('membros','Membros e Subscrições','members'),
    ('relatorios','Métricas e Relatórios','reports'),('notificacoes','Notificações','settings'),
    ('configuracoes','Configurações Gerais','settings')]


def rows_page(query):
    from request_values import pagination_page
    return query.paginate(page=pagination_page(),per_page=20,error_out=False)


def progress_for(account, item):
    row=db.session.get(PremiumProgress,(account.id,item.id))
    if row is None:
        try:
            with db.session.begin_nested():
                row=PremiumProgress(owner_id=account.id,content_id=item.id,position=1,results={},bookmark='',favourite=False)
                db.session.add(row);db.session.flush()
        except IntegrityError:
            row=db.session.get(PremiumProgress,(account.id,item.id))
            if row is None:abort(409)
    return row


def completion(item, account):
    lessons=PremiumLesson.query.filter_by(content_id=item.id,published=True).order_by(PremiumLesson.position,PremiumLesson.id).all()
    progress=db.session.get(PremiumProgress,(account.id,item.id))
    results=progress.results if progress else {}
    completed=[lesson.id for lesson in lessons if results.get(str(lesson.id),{}).get('version')==lesson.version
               and results[str(lesson.id)].get('passed') is True]
    return lessons,completed


def process_publications(limit=100):
    """Run from the Premium CLI; a page visit never changes publication state."""
    from premium import audit, commit, entitled, subscription_for
    from submission_models import Researcher
    count=0
    due=PremiumContent.query.join(PremiumResource,PremiumResource.content_id==PremiumContent.id).filter(
        PremiumResource.state=='scheduled',PremiumResource.publish_at<=utcnow()).order_by(PremiumContent.id).limit(limit)
    # Catalogue edits acquire the content row before touching its metadata too.
    for item in due.with_for_update(of=PremiumContent,skip_locked=True).all():
        resource=db.session.get(PremiumResource,item.id)
        if not resource.metadata_fields.get('rights_confirmed'):continue
        resource.state='published';resource.content.published=True
        resource.notification_done=False;resource.notification_cursor=0
        audit('resource.publish',resource.content,{'scheduled':True});count+=1
    commit()
    # Bounded, durable cursor avoids an unbounded publish request and repeated notices.
    resources=PremiumResource.query.filter_by(state='published',notification_done=False).order_by(PremiumResource.content_id).limit(limit).all()
    for resource in resources:
        if not resource.content.published:continue
        subs=PremiumSubscription.query.filter(PremiumSubscription.owner_id>resource.notification_cursor,
            PremiumSubscription.status=='active',PremiumSubscription.starts_at<=utcnow(),PremiumSubscription.ends_at>utcnow()).order_by(PremiumSubscription.owner_id).limit(limit).all()
        for sub in subs:
            account=db.session.get(Researcher,sub.owner_id)
            if account and entitled(subscription_for(account)) and (not resource.plan_ids or sub.plan_id in resource.plan_ids):
                notify(account.id,'content','Novo recurso: '+resource.content.title,
                    'Disponível na Biblioteca Exclusiva: /premium/conteudos/'+str(resource.content_id),
                    f'publication:{resource.content_id}:{resource.content.version}:{account.id}')
            resource.notification_cursor=sub.owner_id
        resource.notification_done=len(subs)<limit
        commit()
    return count


def install_features(public, admin):
    @public.app_context_processor
    def feature_context():
        from premium import subscription_label
        return dict(premium_detail=detail,premium_types=TYPES,premium_states=STATES,
                    premium_can=can,premium_sections=SECTIONS,premium_local=local_input,premium_terms=terms,
                    premium_subscription_state=subscription_label)

    @public.after_request
    def resource_headers(response):
        if request.endpoint=='premium.resource_reader':
            # This exception is confined to the private reader, not the portal's shared CSP.
            nonce=getattr(g,'csp_nonce','')
            response.headers['Content-Security-Policy']=("default-src 'self'; base-uri 'self'; object-src 'none'; frame-src 'self'; "
                "frame-ancestors 'self'; form-action 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; script-src 'self' 'nonce-"+nonce+"'; connect-src 'self'; media-src 'self'")
        if request.endpoint and request.endpoint.startswith('premium.') and request.endpoint not in {'premium.index','premium.library','premium.conditions'}:
            response.headers['X-Robots-Tag']='noindex, nofollow, noarchive'
        return response

    @public.get('/planos/<int:ident>/condicoes')
    def conditions(ident):
        plan=db.get_or_404(PremiumPlan,ident)
        if not plan.active:abort(404)
        return render_template('premium/conditions.html',plan=plan,terms=terms(plan))

    @admin.route('/gestao/<section>',methods=['GET','POST'])
    @required('any')
    def manage(section):
        entry=next((row for row in SECTIONS if row[0]==section),None)
        if not entry:abort(404)
        permission=entry[2]
        if permission=='settings':
            if not session.get('admin_superuser'):abort(403)
        elif not can(permission):abort(403)
        if request.method=='POST':
            validate_csrf()
            if section not in {'configuracoes','notificacoes'}:abort(405)
            return save_configuration(section)
        query=PremiumContent.query
        mapping={'cursos':['course'],'videos':['video','series','interview'],'eventos':['event'],'coleccoes':['collection']}
        if section in mapping:
            query=query.outerjoin(PremiumResource,PremiumResource.content_id==PremiumContent.id).filter(or_(
                PremiumResource.resource_type.in_(mapping[section]),db.and_(PremiumResource.content_id.is_(None),PremiumContent.kind.in_(mapping[section]))))
        search=request.args.get('q','').strip()[:180]
        if search:query=query.filter(or_(PremiumContent.title.icontains(search,autoescape=True),PremiumContent.category.icontains(search,autoescape=True)))
        members_query=PremiumSubscription.query.join(Researcher,Researcher.id==PremiumSubscription.owner_id)
        if search:members_query=members_query.filter(or_(Researcher.name.icontains(search,autoescape=True),Researcher.email.icontains(search,autoescape=True)))
        from billing_providers import available_methods
        return render_template('admin/premium_manage.html',section=section,heading=entry[1],
            rows=rows_page(query.order_by(PremiumContent.id.desc())),search=search,
            plans=PremiumPlan.query.order_by(PremiumPlan.id).all(),
            members=rows_page(members_query.order_by(PremiumSubscription.id.desc())) if section=='membros' else None,
            values=settings(),values_record=db.session.get(PremiumSetting,1),notification_kinds=NOTIFICATIONS,
            methods_ready=available_methods(configured=False),staff=PremiumStaff.query.all() if session.get('admin_superuser') else [],
            categories=PremiumCategory.query.order_by(PremiumCategory.name).all(),permissions=PERMISSIONS)

    def save_configuration(section):
        from premium import audit, commit
        row=db.session.get(PremiumSetting,1)
        if row and request.form.get('version')!=str(row.version):abort(409)
        if not row:row=PremiumSetting(id=1,values={});db.session.add(row)
        values=dict(row.values)
        try:
            if section=='configuracoes':
                methods=request.form.getlist('methods');currencies=request.form.getlist('currencies')
                if any(x not in {'mpesa','emola','netshop','stripe'} for x in methods) or any(x not in {'MZN','USD','EUR','ZAR'} for x in currencies):raise ValueError('Configuração inválida.')
                values.update(methods=methods,currencies=currencies)
            else:
                prefix=request.form.get('notice_prefix','').strip()
                if not 1<=len(prefix)<=60:raise ValueError('Indique um prefixo até 60 caracteres.')
                templates={}
                for key in NOTIFICATIONS:
                    template=request.form.get('template_'+key,'{mensagem}').strip()
                    if len(template)>2000 or '{mensagem}' not in template:raise ValueError('Cada mensagem deve incluir {mensagem} e ter até 2000 caracteres.')
                    templates[key]=template
                values.update(notice_prefix=prefix,notifications={key:request.form.get(key)=='on' for key in NOTIFICATIONS},notice_templates=templates)
            row.values=values;audit('settings.save',row,{'section':section,'keys':list(values)});commit()
            flash('Configuração do Prémio guardada.','success')
        except ValueError as error:
            db.session.rollback();flash(str(error),'error')
        return redirect(url_for('premium_admin.manage',section=section))

    @admin.post('/permissoes')
    @superadmin_required
    def staff_permission():
        from premium import audit,commit
        validate_csrf()
        try:
            ident=integer(request.form.get('admin_id'))
            account=db.get_or_404(AdminUser,ident)
            permissions=request.form.getlist('permissions')
            if not account.active or any(p not in PERMISSIONS for p in permissions):raise ValueError('Conta ou permissões inválidas.')
            row=db.session.get(PremiumStaff,ident) or PremiumStaff(admin_id=ident)
            row.permissions=list(dict.fromkeys(permissions));db.session.add(row)
            audit('staff.permissions',account,{'permissions':row.permissions});commit()
            flash('Permissões do Prémio actualizadas.','success')
        except ValueError as error:db.session.rollback();flash(str(error),'error')
        return redirect(url_for('premium_admin.manage',section='configuracoes'))

    @admin.post('/categorias')
    @required('content')
    def category_save():
        from premium import audit,commit
        validate_csrf()
        try:
            ident=integer(request.form.get('id')) if request.form.get('id') else None
            row=db.get_or_404(PremiumCategory,ident) if ident else PremiumCategory()
            if request.form.get('action')=='delete':
                if request.form.get('confirm')!='on':raise ValueError('Confirme a eliminação.')
                if PremiumContent.query.filter_by(category=row.name).first():raise ValueError('A categoria ainda está associada a recursos.')
                audit('category.delete',row,{'name':row.name});db.session.delete(row)
            else:
                name=request.form.get('name','').strip();description=request.form.get('description','').strip()
                if not 1<=len(name)<=80 or len(description)>500:raise ValueError('Categoria inválida.')
                if row.id:
                    PremiumContent.query.filter_by(category=row.name).update({'category':name,'version':PremiumContent.version+1},synchronize_session=False)
                row.name,row.description=name,description;db.session.add(row);audit('category.save',row,{'name':name})
            commit();flash('Categoria actualizada.','success')
        except (ValueError,IntegrityError):db.session.rollback();flash('Não foi possível guardar: confirme os campos e as associações da categoria.','error')
        return redirect(url_for('premium_admin.manage',section='catalogo'))

    @admin.get('/coleccoes/recursos')
    @required('content')
    def collection_search():
        search=request.args.get('q','').strip()
        if len(search)>180:abort(400)
        if len(search)<2:return {'items':[]}
        query=PremiumContent.query.filter(PremiumContent.title.icontains(search,autoescape=True)).outerjoin(
            PremiumResource,PremiumResource.content_id==PremiumContent.id).filter(or_(
                PremiumResource.content_id.is_(None),PremiumResource.resource_type!='collection'))
        if request.args.get('exclude'):
            try:query=query.filter(PremiumContent.id!=integer(request.args['exclude']))
            except ValueError:abort(400)
        return {'items':[{'id':item.id,'title':item.title} for item in query.order_by(PremiumContent.id.desc()).limit(20)]}

    @admin.post('/conteudos/<int:ident>/estado')
    @required('content')
    def resource_state(ident):
        from premium import audit,commit,check_version
        validate_csrf();item=db.get_or_404(PremiumContent,ident);check_version(item)
        action=request.form.get('action')
        if action not in {'archive','restore','delete'}:abort(400)
        resource=detail(item)
        if action=='delete':
            if request.form.get('confirm')!='on':abort(400)
            # Learning/attendance history remains auditable: archive used resources.
            from premium_models import PremiumEnrollment, PremiumAccessHistory, PremiumServiceRequest
            used=any(model.query.filter_by(content_id=ident).first() for model in (PremiumProgress,PremiumRegistration,PremiumCertificate,PremiumEnrollment,PremiumAccessHistory,PremiumServiceRequest))
            if used:abort(409,description='Este recurso tem histórico de utilização. Arquive-o para preservar os registos.')
            PremiumCollectionItem.query.filter(or_(PremiumCollectionItem.content_id==ident,PremiumCollectionItem.collection_id==ident)).delete(synchronize_session=False)
            PremiumLesson.query.filter_by(content_id=ident).delete(synchronize_session=False)
            for model in (PremiumFile,PremiumEvent,PremiumResource,PremiumUsage):model.query.filter_by(content_id=ident).delete(synchronize_session=False)
            audit('resource.delete',item,{'title':item.title});db.session.delete(item)
        else:
            resource.state='archived' if action=='archive' else 'draft';item.published=False
            db.session.add(resource);item.version+=1
            audit('resource.'+action,item,{'state':resource.state})
        commit();return redirect(url_for('premium_admin.manage',section='catalogo'))

    @admin.post('/ficheiros/<int:ident>/eliminar')
    @required('content')
    def file_delete(ident):
        from premium import audit,commit,check_version
        validate_csrf();row=db.get_or_404(PremiumFile,ident)
        item=db.get_or_404(PremiumContent,row.content_id);check_version(item)
        if request.form.get('confirm')!='on':abort(400)
        if PremiumLesson.query.filter(or_(PremiumLesson.video_file_id==ident,PremiumLesson.document_file_id==ident)).first():abort(409,description='Retire este ficheiro das aulas antes de eliminar.')
        audit('file.delete',item,{'file_id':row.id,'name':row.name});db.session.delete(row);item.version+=1;commit()
        return redirect(url_for('premium_admin.edit_content',ident=item.id))

    @public.get('/ficheiros/<int:ident>')
    def resource_file(ident):
        row=db.get_or_404(PremiumFile,ident);item=db.get_or_404(PremiumContent,row.content_id)
        resource=require_access(item)
        download=request.args.get('download')=='1'
        if download and not resource.download_allowed:abort(403)
        if not download and row.mime not in {'application/pdf','video/mp4','video/webm','image/jpeg'}:
            abort(403,description='Utilize o leitor integrado ou um descarregamento autorizado.')
        record_usage(item,'download' if download else 'file_view');db.session.commit()
        response=send_file(io.BytesIO(row.payload),mimetype=row.mime,as_attachment=download,download_name=row.name,
                           conditional=True,etag=row.digest,max_age=0)
        response.headers['Cache-Control']='private, no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    @public.post('/ficheiros/<int:ident>/reproducao')
    def video_started(ident):
        validate_csrf();reader()
        file=db.get_or_404(PremiumFile,ident)
        if not file.mime.startswith('video/'):abort(400)
        item=db.get_or_404(PremiumContent,file.content_id);require_access(item)
        record_usage(item,'video_start');db.session.commit()
        return '',204

    @admin.get('/ficheiros/<int:ident>/verificar')
    @required('content')
    def file_preview(ident):
        row=db.get_or_404(PremiumFile,ident)
        return send_file(io.BytesIO(row.payload),mimetype=row.mime,as_attachment=True,download_name=row.name,max_age=0)

    @public.route('/conteudos/<int:ident>/leitor',methods=['GET','POST'])
    def resource_reader(ident):
        from submissions import researcher
        from types import SimpleNamespace
        item=db.get_or_404(PremiumContent,ident);resource=require_access(item);account=researcher()
        if account and (not account.active or not account.verified):account=None
        if not account and not item.open_access_required:abort(403)
        progress=progress_for(account,item) if account else SimpleNamespace(position=1,bookmark='',results={},version=0)
        files=PremiumFile.query.filter_by(content_id=ident).order_by(PremiumFile.id).all()
        if request.args.get('file'):
            try:document_id=integer(request.args['file'])
            except ValueError:abort(400)
            document=next((row for row in files if row.role=='attachment' and row.id==document_id),None)
            if document is None:abort(404)
        else:
            document=next((row for row in files if row.role=='attachment'),None)
        chapters=epub_chapters(document.payload) if document and document.mime=='application/epub+zip' else []
        pages=len(chapters)
        if document and document.mime=='application/pdf':
            from pypdf import PdfReader
            pages=len(PdfReader(io.BytesIO(document.payload)).pages)
        if request.method=='POST':
            validate_csrf()
            if not account:abort(403)
            if request.form.get('version')!=str(progress.version):abort(409)
            try:progress.position=integer(request.form.get('position'),1,pages or 100000)
            except ValueError:abort(400)
            bookmark=request.form.get('bookmark','').strip()
            if len(bookmark)>500:abort(400)
            progress.bookmark=bookmark
            markers=progress.results.get('__bookmarks__',[])
            if bookmark:
                markers=[m for m in markers if m['position']!=progress.position]+[{'position':progress.position,'note':bookmark}]
                progress.results={**progress.results,'__bookmarks__':markers[-20:]}
            progress.updated_at=utcnow();db.session.commit()
            return redirect(url_for('premium.resource_reader',ident=ident,chapter=progress.position,file=document.id if document else None))
        try:position=integer(request.args.get('chapter',str(min(progress.position,pages or 100000))),1,pages or 100000)
        except ValueError:abort(400)
        if chapters:progress.position=position
        record_usage(item,'read');progress.updated_at=utcnow();db.session.commit()
        return render_template('premium/reader.html',item=item,resource=resource,document=document,progress=progress,
            chapter=chapters[position-1] if chapters else '',position=position,total=pages)

    @public.post('/conteudos/<int:ident>/favorito')
    def favourite(ident):
        validate_csrf();item=db.get_or_404(PremiumContent,ident);require_access(item,allow_grace=False)
        progress=progress_for(reader(),item)
        progress.favourite=not progress.favourite
        try:db.session.commit()
        except (StaleDataError,IntegrityError):db.session.rollback();abort(409)
        return redirect(url_for('premium.content',ident=ident))

    @public.get('/minha-aprendizagem')
    def learning():
        account=reader()
        query=PremiumContent.query.join(PremiumProgress,PremiumProgress.content_id==PremiumContent.id).filter(
            PremiumProgress.owner_id==account.id,PremiumContent.published.is_(True),visible_clause())
        if request.args.get('favourites')=='1':query=query.filter(PremiumProgress.favourite.is_(True))
        return render_template('premium/learning.html',rows=rows_page(query.order_by(PremiumProgress.updated_at.desc())))

    @admin.route('/conteudos/<int:ident>/aulas',methods=['GET','POST'])
    @required('content')
    def lessons(ident):
        from premium import audit,commit,check_version
        item=db.get_or_404(PremiumContent,ident)
        if detail(item).resource_type not in {'course','series','interview','video'}:abort(400)
        error=None
        if request.method=='POST':
            validate_csrf();check_version(item)
            try:
                lesson_id=integer(request.form.get('lesson_id')) if request.form.get('lesson_id') else None
                row=PremiumLesson.query.filter_by(id=lesson_id,content_id=ident).first_or_404() if lesson_id else PremiumLesson(content_id=ident)
                if request.form.get('action')=='delete':
                    if request.form.get('confirm')!='on':raise ValueError('Confirme a eliminação da aula.')
                    db.session.delete(row)
                else:
                    title=request.form.get('title','').strip();body=request.form.get('body','').strip();module=request.form.get('module','').strip()
                    if not 1<=len(title)<=180 or len(body)>100000 or len(module)>120:raise ValueError('Campos da aula inválidos.')
                    questions=json.loads(request.form['questions']) if 'questions' in request.form else []
                    if 'questions' not in request.form:
                        for index in range(10):
                            prompt=request.form.get('question_'+str(index),'').strip()
                            if not prompt:continue
                            options=[line.strip() for line in request.form.get('options_'+str(index),'').splitlines() if line.strip()]
                            answer=integer(request.form.get('answer_'+str(index)),1,len(options))-1
                            questions.append({'prompt':prompt,'options':options,'answer':answer})
                    if not isinstance(questions,list) or len(questions)>10:raise ValueError('Utilize até dez perguntas por aula.')
                    for question in questions:
                        if (not isinstance(question,dict) or set(question)!={'prompt','options','answer'} or not isinstance(question['prompt'],str)
                            or not 1<=len(question['prompt'])<=1000 or not isinstance(question['options'],list) or not 2<=len(question['options'])<=6
                            or any(not isinstance(o,str) or not 1<=len(o)<=500 for o in question['options'])
                            or type(question['answer']) is not int or not 0<=question['answer']<len(question['options'])):raise ValueError('Estrutura das perguntas inválida.')
                    video=integer(request.form.get('video_file_id')) if request.form.get('video_file_id') else None
                    if video and not PremiumFile.query.filter_by(id=video,content_id=ident,role='video').first():raise ValueError('Escolha um vídeo privado deste recurso.')
                    document=integer(request.form.get('document_file_id')) if request.form.get('document_file_id') else None
                    if document and not PremiumFile.query.filter_by(id=document,content_id=ident,role='attachment').first():raise ValueError('Escolha um documento deste recurso.')
                    row.title,row.body,row.module=title,body,module
                    row.position=integer(request.form.get('position'),1,1000);row.questions=questions
                    row.video_file_id=video;row.published=request.form.get('published')=='on';db.session.add(row)
                    row.document_file_id=document
                item.version+=1;audit('lesson.save',item,{'lesson':lesson_id});commit()
                return redirect(url_for('premium_admin.lessons',ident=ident))
            except (ValueError,TypeError) as exc:db.session.rollback();error=str(exc)
        return render_template('admin/premium_lessons.html',item=item,lessons=PremiumLesson.query.filter_by(content_id=ident).order_by(PremiumLesson.position,PremiumLesson.id).all(),files=PremiumFile.query.filter_by(content_id=ident,role='video').all(),documents=PremiumFile.query.filter_by(content_id=ident,role='attachment').all(),error=error)

    @public.route('/aulas/<int:ident>',methods=['GET','POST'])
    def lesson(ident):
        row=PremiumLesson.query.filter_by(id=ident,published=True).first_or_404()
        item=db.get_or_404(PremiumContent,row.content_id);resource=require_access(item);account=reader()
        if resource.resource_type=='course':
            from premium import subscription_for
            from premium_members import enrollment_for
            if not item.open_access_required:
                from premium_models import PremiumEnrollment
                sub=subscription_for(account)
                if sub and sub.plan.tier in {'pro','max'} and not db.session.get(PremiumEnrollment,(account.id,item.id)):
                    abort(403,description='Inscreva-se no curso antes de iniciar as aulas.')
                enrollment_for(account,item,resource,sub)
        progress=progress_for(account,item);feedback=None
        if request.method=='POST':
            validate_csrf()
            if request.form.get('lesson_version')!=str(row.version) or request.form.get('progress_version')!=str(progress.version):abort(409)
            correct=0
            for n,question in enumerate(row.questions):
                if request.form.get('answer_'+str(n))==str(question['answer']):correct+=1
            passed=not row.questions or correct==len(row.questions)
            progress.results={**progress.results,str(row.id):{'version':row.version,'passed':passed,'score':correct,'total':len(row.questions)}}
            progress.updated_at=utcnow();record_usage(item,'lesson_completed' if passed else 'assessment_attempt')
            notify(account.id,'learning','Aula concluída' if passed else 'Avaliação registada',row.title,
                f'lesson:{row.id}:{row.version}:{account.id}:{passed}')
            try:db.session.commit()
            except (StaleDataError,IntegrityError):db.session.rollback();abort(409)
            feedback='Aula concluída.' if passed else 'Reveja a aula e tente novamente. Respostas certas: '+str(correct)+' de '+str(len(row.questions))+'.'
        record_usage(item,'lesson_view');db.session.commit()
        return render_template('premium/lesson.html',item=item,lesson=row,progress=progress,feedback=feedback)

    @public.post('/conteudos/<int:ident>/certificado')
    def certificate(ident):
        validate_csrf();item=db.get_or_404(PremiumContent,ident);resource=require_access(item);account=reader()
        lessons,completed=completion(item,account)
        if resource.resource_type!='course' or not resource.certificate_enabled or not lessons or len(completed)!=len(lessons):abort(403)
        certificate=PremiumCertificate.query.filter_by(owner_id=account.id,content_id=ident,content_version=item.version).first()
        from premium_models import PremiumEnrollment
        enrollment=db.session.get(PremiumEnrollment,(account.id,ident))
        if enrollment:enrollment.state='completed'
        if not certificate:
            certificate=PremiumCertificate(id=secrets.token_hex(16),owner_id=account.id,content_id=ident,content_version=item.version,
                snapshot={'name':account.name,'title':item.title,'instructor':resource.metadata_fields.get('instructor',''),'lessons':len(lessons)})
            db.session.add(certificate)
            notify(account.id,'learning','Certificado disponível',item.title,f'certificate:{ident}:{item.version}:{account.id}')
            try:db.session.commit()
            except IntegrityError:db.session.rollback();abort(409)
        return redirect(url_for('premium.certificate_download',token=certificate.id))

    @public.get('/certificados/<token>.pdf')
    def certificate_download(token):
        account=reader()
        certificate=PremiumCertificate.query.filter_by(id=token,owner_id=account.id).first_or_404()
        from app import SITE_URL
        from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        output=io.BytesIO();styles=getSampleStyleSheet()
        doc=SimpleDocTemplate(output)
        doc.build([Paragraph('Sussurros do Saber',styles['Title']),Spacer(1,30),Paragraph('Certificado de conclusão',styles['Heading1']),
            Paragraph(escape(certificate.snapshot['name']),styles['Heading2']),Paragraph('Concluiu o percurso educativo '+escape(certificate.snapshot['title'])+'.',styles['BodyText']),
            Paragraph('Aulas concluídas: '+str(certificate.snapshot['lessons'])+'. Este documento certifica a conclusão do percurso na plataforma; não atribui um grau académico.',styles['BodyText']),
            Spacer(1,30),Paragraph('Emitido em '+certificate.issued_at.strftime('%d/%m/%Y')+' · Referência '+certificate.id,styles['BodyText']),
            Paragraph('Verificar autenticidade: '+escape(SITE_URL.rstrip('/')+url_for('premium.verify_certificate',token=certificate.id)),styles['BodyText'])])
        output.seek(0)
        return send_file(output,mimetype='application/pdf',as_attachment=True,download_name='certificado.pdf',max_age=0)

    @public.post('/eventos/<int:ident>/inscricao')
    def register_event(ident):
        validate_csrf();item=db.get_or_404(PremiumContent,ident);require_access(item,allow_grace=request.form.get('action')=='cancel');account=reader()
        event=db.session.execute(select(PremiumEvent).where(PremiumEvent.content_id==ident).with_for_update()).scalar_one_or_none()
        if not event:abort(404)
        row=db.session.get(PremiumRegistration,(ident,account.id))
        action=request.form.get('action')
        if action not in {'cancel','register'}:abort(400)
        if (action=='cancel' and (not row or row.state=='cancelled') or
                action=='register' and row and row.state!='cancelled'):
            db.session.commit()
            return redirect(url_for('premium.content',ident=ident))
        event.version+=1  # Optimistic gate also protects capacity on SQLite.
        if action=='cancel':
            if event.starts_at<=utcnow():abort(409,description='O evento já começou. Contacte a organização para alterar a participação.')
            if row:row.state='cancelled'
        elif action=='register':
            if event.starts_at<=utcnow():abort(409,description='As inscrições deste evento já terminaram.')
            if not row or row.state=='cancelled':
                occupied=PremiumRegistration.query.filter_by(content_id=ident).filter(PremiumRegistration.state!='cancelled').count()
                if occupied>=event.capacity:abort(409,description='O evento atingiu a capacidade disponível.')
                if not row:row=PremiumRegistration(content_id=ident,owner_id=account.id);db.session.add(row)
                row.state='registered';record_usage(item,'event_registration')
        else:abort(400)
        notify(account.id,'event','Inscrição cancelada' if action=='cancel' else 'Inscrição confirmada',item.title,
            f'event:{ident}:{account.id}:{action}:{event.version}')
        try:db.session.commit()
        except (StaleDataError,IntegrityError):db.session.rollback();abort(409)
        return redirect(url_for('premium.content',ident=ident))

    @admin.route('/eventos/<int:ident>/participantes',methods=['GET','POST'])
    @required('events')
    def participants(ident):
        from premium import audit,commit
        item=db.get_or_404(PremiumContent,ident)
        if not db.session.get(PremiumEvent,ident):abort(404)
        if request.method=='POST':
            validate_csrf()
            try:owner=integer(request.form.get('owner_id'))
            except ValueError:abort(400)
            row=PremiumRegistration.query.filter_by(content_id=ident,owner_id=owner).first_or_404()
            if request.form.get('state') not in {'attended','registered','cancelled'}:abort(400)
            event=db.session.get(PremiumEvent,ident);event.version+=1
            if row.state=='cancelled' and request.form['state']!='cancelled':
                occupied=PremiumRegistration.query.filter_by(content_id=ident).filter(PremiumRegistration.state!='cancelled').count()
                if occupied>=event.capacity:abort(409)
            row.state=request.form['state'];audit('event.participant',item,{'owner':owner,'state':row.state});commit()
        return render_template('admin/premium_participants.html',item=item,rows=rows_page(PremiumRegistration.query.filter_by(content_id=ident).order_by(PremiumRegistration.created_at.desc())))

    @admin.get('/relatorios')
    @required('reports')
    def reports():
        start=request.args.get('from','');end=request.args.get('to','')
        query=db.session.query(PremiumUsage)
        try:
            if start:query=query.filter(PremiumUsage.created_at>=datetime.strptime(start,'%Y-%m-%d'))
            if end:query=query.filter(PremiumUsage.created_at<datetime.strptime(end,'%Y-%m-%d')+timedelta(days=1))
            if start and end and start>end:raise ValueError()
        except (ValueError,OverflowError):abort(400)
        counts=query.with_entities(PremiumUsage.action,func.count(PremiumUsage.id)).group_by(PremiumUsage.action).all()
        popular=query.join(PremiumContent,PremiumContent.id==PremiumUsage.content_id).with_entities(
            PremiumContent.title,func.count(PremiumUsage.id)).group_by(PremiumContent.id,PremiumContent.title).order_by(func.count(PremiumUsage.id).desc()).limit(20).all()
        if request.args.get('export')=='csv':
            output=io.StringIO();writer=csv.writer(output);writer.writerow(['Recurso','Interacções registadas'])
            for title,count in popular:writer.writerow([csv_safe_cell(title),count])
            return current_app.response_class(output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=premium-utilizacao.csv'})
        return render_template('admin/premium_reports.html',counts=counts,popular=popular,start=start,end=end)

    @admin.cli.command('processar')
    @click.option('--limit',default=100,type=click.IntRange(1,500))
    def process_command(limit):
        """Publish due Premium resources and process bounded in-site notices."""
        count=process_publications(limit)
        click.echo(f'{count} recursos publicados; notificações processadas por lotes.')

