"""Staff governance. Permissions are evaluated from live, accepted mandates."""
import io
import re
from datetime import date, datetime, timezone
from urllib.parse import urlparse
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for, send_file
from sqlalchemy import or_
from models import db, utcnow, AdminUser, Author, Article, Journal
from governance_models import (TeamMember, TeamRole, TeamAppointment, StaffTask, StaffDocument,
                               StaffNotice, GovernanceAudit, ArticleWorkflow, StaffPeerReview, PortalReview, StaffContactLog, TaskComment, AuditReport)
from admin import (login_required, superadmin_required, validate_csrf, enforce_admin_authentication,
                   protect_admin_responses)

staff_bp = Blueprint('staff', __name__, url_prefix='/admin')
public_team_bp = Blueprint('public_team', __name__)
staff_bp.before_request(enforce_admin_authentication)
staff_bp.after_request(protect_admin_responses)
PERMISSIONS = {
    'team.manage': 'Gerir equipa, convites e mandatos', 'tasks.manage': 'Distribuir tarefas',
    'reports.read': 'Consultar relatórios e auditoria', 'article.write': 'Escrever artigos próprios',
    'article.edit': 'Editar todos os artigos', 'article.review': 'Rever artigos atribuídos',
    'article.approve': 'Aprovar artigos revistos', 'article.publish': 'Publicar artigos aprovados',
    'article.delete': 'Eliminar artigos', 'authors.manage': 'Gerir autores', 'categories.manage': 'Gerir categorias',
    'journal.manage': 'Gerir revistas', 'journal.publish': 'Publicar revistas',
    'manuscript.read': 'Consultar submissões da revista', 'manuscript.edit': 'Tratar submissões atribuídas',
    'manuscript.assign': 'Atribuir editores e revisores', 'manuscript.decide': 'Emitir decisões científicas',
    'manuscript.production': 'Preparar artigos científicos', 'manuscript.review': 'Emitir pareceres atribuídos',
    'submissions.configure': 'Configurar submissões', 'policies.manage': 'Gerir políticas editoriais',
    'comments.manage': 'Moderar comentários', 'contacts.manage': 'Gerir contactos',
    'subscribers.manage': 'Gerir subscritores',
}
DEFAULT_ROLES = [
    ('direction', 'Direcção institucional', 'Parcerias, estratégia e equipa.', ['team.manage','tasks.manage','reports.read','contacts.manage','subscribers.manage']),
    ('coordination', 'Coordenação do portal', 'Distribuição de trabalho e acompanhamento.', ['tasks.manage','reports.read','article.edit','authors.manage','categories.manage','comments.manage']),
    ('chief_editor', 'Editor científico principal', 'Decisões científicas, conflitos e revisão por pares.', ['manuscript.read','manuscript.edit','manuscript.assign','manuscript.decide','manuscript.production','submissions.configure','journal.manage','journal.publish','policies.manage','reports.read']),
    ('associate_editor', 'Editor associado', 'Triagem e acompanhamento das submissões atribuídas.', ['manuscript.edit']),
    ('reviewer', 'Revisor científico', 'Pareceres fundamentados, disponibilidade e conflitos.', ['manuscript.review']),
    ('author', 'Autor do portal', 'Produção de artigos de divulgação.', ['article.write']),
    ('portal_reviewer', 'Revisor do portal', 'Verificação dos artigos atribuídos.', ['article.review']),
    ('portal_editor', 'Editor do portal', 'Aprovação editorial após revisão independente.', ['article.edit','article.approve']),
    ('publisher', 'Responsável de publicação', 'Publicação de conteúdos aprovados.', ['article.publish']),
    ('secretariat', 'Secretariado editorial', 'Apoio documental e acompanhamento das submissões.', ['tasks.manage','manuscript.read']),
    ('production', 'Produção científica', 'Preparação de publicações aceites.', ['manuscript.production']),
]
MEMBER_STATES = {'invited':'Convidado','contacted':'Contactado','conversation':'Em conversa','offered':'Proposta enviada',
                 'active':'Activo','declined':'Recusou','deferred':'Adiado','suspended':'Suspenso','ended':'Terminado'}
TASK_STATES = {'pending':'Pendente','in_progress':'Em curso','blocked':'Bloqueada','done':'Concluída','cancelled':'Cancelada'}
# Only these grants operate on journal resources. Other grants need a general mandate.
JOURNAL_PERMISSIONS = {'journal.manage','journal.publish','manuscript.read','manuscript.edit',
    'manuscript.assign','manuscript.decide','manuscript.production','manuscript.review','submissions.configure'}
MANUSCRIPT_ACCESS_PERMISSIONS = ('manuscript.read','manuscript.edit','manuscript.assign','manuscript.decide','manuscript.production')
ARTICLE_ACCESS_PERMISSIONS = ('article.write','article.edit','article.review','article.approve','article.publish','article.delete')

ARTICLE_STAGES = {'draft':'Rascunho','submitted':'Submetido','review':'Em revisão','changes':'Correcções solicitadas','approved':'Aprovado','scheduled':'Programado','published':'Publicado'}


def seed_roles():
    for code, name, purpose, permissions in DEFAULT_ROLES:
        if not TeamRole.query.filter_by(code=code).first():
            db.session.add(TeamRole(code=code, name=name, purpose=purpose, duties=purpose,
                                    limits='Acesso limitado às permissões e ao âmbito do mandato.', permissions=permissions))
    db.session.commit()


def current_member():
    ident = session.get('admin_id')
    return TeamMember.query.filter_by(admin_id=ident).first() if ident else None


def active_member(member):
    return bool(member and not member.removed_at and member.status == 'active' and member.accepted_at
                and member.admin_id and member.admin and member.admin.active)


def mandates(member):
    today = date.today()
    return [a for a in member.appointments if a.active and a.starts_on <= today
            and (not a.ends_on or a.ends_on >= today)] if active_member(member) else []


def has_permission(permission, journal_id=None, *, member=None):
    if permission not in PERMISSIONS:
        return False
    if permission not in JOURNAL_PERMISSIONS:
        journal_id=None
    if member is None:
        if session.get('admin_superuser'):
            return True
        member = current_member()
        # Historical accounts keep existing content access until explicitly migrated.
        # New accounts always receive an invited member record, with no automatic grants.
        if member is None:
            account=db.session.get(AdminUser,session.get('admin_id')) if session.get('admin_id') else None
            return bool(account and account.active and not account.governance_managed) and permission not in {'team.manage','manuscript.decide','manuscript.assign'}
    return any(permission in (a.role.permissions or []) and (a.journal_id is None or a.journal_id == journal_id)
               for a in mandates(member))


def has_any_permission(permission):
    if permission not in JOURNAL_PERMISSIONS:
        return has_permission(permission)
    if session.get('admin_superuser') or current_member() is None:
        return has_permission(permission)
    return any(permission in (a.role.permissions or []) for a in mandates(current_member()))


def require(permission, journal_id=None):
    if not has_permission(permission, journal_id):
        abort(403, description='A sua função ou o âmbito do mandato não permite esta acção.')


def audit(action, entity, ident=None, detail=''):
    from internal_notices import dispatch
    db.session.add(GovernanceAudit(actor_id=session.get('admin_id'), actor_name=session.get('admin_username','Responsável principal'),
                                  action=action, entity=entity, entity_id=ident, detail=detail[:1000]))
    dispatch(action,entity,ident,detail)


def notice(member, subject, body=''):
    if member and member.admin_id:
        db.session.add(StaffNotice(admin_id=member.admin_id, subject=subject[:240], body=body[:10000]))


def parse_date(value, required=False):
    try:
        result = date.fromisoformat(value) if value else None
    except ValueError:
        abort(400, description='Data inválida.')
    if required and not result:
        abort(400, description='Informe a data obrigatória.')
    return result


def field(name, maximum, required=False):
    value = request.form.get(name, '').strip()
    if len(value) > maximum or (required and not value):
        abort(400, description='Campo inválido: ' + name)
    return value


def eligible(permission, journal_id=None):
    return [m for m in TeamMember.query.order_by(TeamMember.name).all() if has_permission(permission,journal_id,member=m)]


def conflicts(member, manuscript):
    addresses = {a.email.strip().lower() for a in manuscript.authors}
    from submission_models import Researcher
    owner = db.session.get(Researcher, manuscript.owner_id)
    if owner:
        addresses.add(owner.email.strip().lower())
    return member.email.lower() in addresses or bool(member.admin and member.admin.email and member.admin.email.lower() in addresses)


def manuscript_access(manuscript, permission=None):
    member = current_member()
    if not manuscript or manuscript.removed_at:return False
    if member and conflicts(member, manuscript):
        return False
    if permission:
        granted = has_permission(permission, manuscript.journal_id)
        if permission == 'manuscript.edit':
            return granted and (session.get('admin_superuser') or manuscript.editor_id == session.get('admin_id'))
        if permission == 'manuscript.production':
            return granted and manuscript.status in {'accepted','production','published'}
        return granted
    return (has_permission('manuscript.assign', manuscript.journal_id)
            or has_permission('manuscript.decide', manuscript.journal_id)
            or has_permission('manuscript.read', manuscript.journal_id)
            or (has_permission('manuscript.edit', manuscript.journal_id) and manuscript.editor_id == session.get('admin_id'))
            or (has_permission('manuscript.production', manuscript.journal_id) and manuscript.status in {'accepted','production','published'}))


def scope_manuscripts(query):
    from submission_models import Manuscript
    query=query.filter(Manuscript.removed_at.is_(None))
    if session.get('admin_superuser'):
        return query
    if current_member() is None:
        return query if has_permission('manuscript.read') else query.filter(db.false())
    member = current_member()
    clauses = []
    for appointment in mandates(member):
        perms = appointment.role.permissions or []
        scope = Manuscript.journal_id == appointment.journal_id if appointment.journal_id else db.true()
        if any(p in perms for p in ('manuscript.read','manuscript.assign','manuscript.decide')):
            clauses.append(scope)
        if 'manuscript.edit' in perms:
            clauses.append(db.and_(scope, Manuscript.editor_id == session.get('admin_id')))
        if 'manuscript.production' in perms:
            clauses.append(db.and_(scope, Manuscript.status.in_(['accepted','production','published'])))
    from submission_models import ManuscriptAuthor, Researcher
    addresses = {member.email.lower()}
    if member.admin and member.admin.email:
        addresses.add(member.admin.email.lower())
    author_conflict = db.select(ManuscriptAuthor.manuscript_id).where(db.func.lower(ManuscriptAuthor.email).in_(addresses))
    owner_conflict = db.select(Researcher.id).where(db.func.lower(Researcher.email).in_(addresses))
    return query.filter(or_(*clauses) if clauses else db.false()).filter(~Manuscript.id.in_(author_conflict), ~Manuscript.owner_id.in_(owner_conflict))


def guard_existing_endpoint():
    endpoint = (request.endpoint or '').split('.')[-1]
    mapping = {
        'authors':'authors.manage','delete_author':'authors.manage', 'categories':'categories.manage','delete_category':'categories.manage',
        'editorial_policies':'policies.manage','preview_author_guidelines':'policies.manage',
        'comments':'comments.manage','update_comment_status':'comments.manage','delete_comment':'comments.manage',
        'contacts':'contacts.manage','delete_contact':'contacts.manage','export_contacts':'contacts.manage',
        'subscribers':'subscribers.manage','toggle_subscriber':'subscribers.manage','export_subscribers':'subscribers.manage',
        'delete_article':'article.delete',
    }
    if endpoint in mapping:
        require(mapping[endpoint])
    if endpoint == 'delete_journal':
        require('journal.manage', request.view_args.get('journal_id'))
    if endpoint == 'articles' and not any(has_permission(p) for p in ARTICLE_ACCESS_PERMISSIONS):
        abort(403)
    if endpoint in {'upload_inline_image','upload_inline_video','journal_markdown_preview'}:
        if not any(has_any_permission(p) for p in ('article.write','article.edit','manuscript.production','journal.manage')):
            abort(403)


@staff_bp.app_context_processor
def staff_context():
    return dict(staff_can=has_permission, staff_has_any=has_any_permission, staff_member=current_member(), member_states=MEMBER_STATES,
                task_states=TASK_STATES, article_stages=ARTICLE_STAGES,
                staff_valid_mandates=mandates, staff_article_editable=article_editable, staff_journal_can=journal_can,
                staff_article_statuses=article_statuses, staff_permissions=PERMISSIONS,
                staff_journal_permissions=JOURNAL_PERMISSIONS, staff_manuscript_permissions=MANUSCRIPT_ACCESS_PERMISSIONS)


@staff_bp.route('/equipa', methods=['GET','POST'])
@login_required
def team():
    require('team.manage')
    if request.method == 'POST':
        validate_csrf()
        ident = request.form.get('id',type=int)
        member = db.get_or_404(TeamMember,ident) if ident else TeamMember()
        if member.removed_at:
            abort(409,description='Colaborador removido. O histórico não pode recuperar acesso.')
        previous_contact=member.contact_note or ''
        previous_status=member.status
        name, email = field('name',180,True), field('email',254,True).lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
            abort(400,description='E-mail inválido.')
        admin_id = request.form.get('admin_id',type=int)
        author_id = request.form.get('author_id',type=int)
        for model, key, value in ((AdminUser,'admin_id',admin_id),(Author,'author_id',author_id)):
            if value and (not db.session.get(model,value) or TeamMember.query.filter(getattr(TeamMember,key)==value,TeamMember.id!=member.id).first()):
                abort(400,description='Conta já associada ou inexistente.')
        if not session.get('admin_superuser') and (admin_id!=member.admin_id or author_id!=member.author_id):
            abort(403,description='A associação de contas exige o responsável principal.')
        status = field('status',30,True)
        if status not in MEMBER_STATES:
            abort(400)
        if status == 'active' and not member.accepted_at and request.form.get('acceptance_recorded') != 'on':
            abort(400,description='Registe a confirmação de aceite antes de activar o membro.')
        photo = field('photo',600)
        if photo and (urlparse(photo).scheme != 'https' or not urlparse(photo).netloc):
            abort(400,description='Use uma fotografia com endereço HTTPS.')
        orcid = field('orcid',19)
        if orcid:
            from journal_metadata import normalize_orcid
            try:
                orcid = normalize_orcid(orcid).rsplit('/',1)[-1]
            except ValueError:
                abort(400,description='ORCID inválido.')
        if admin_id:
            account=db.session.get(AdminUser,admin_id)
            if account.is_superadmin:
                abort(400,description='A conta principal não deve ser associada a um mandato de colaborador.')
            account.governance_managed=True
        member.name,member.email,member.admin_id,member.author_id,member.status = name,email,admin_id,author_id,status
        for name,limit in [('affiliation',300),('specialty',300),('bio',10000),('contact_note',10000)]:
            setattr(member,name,field(name,limit))
        group = field('group',40)
        if group not in {'portal','scientific','institutional','support'}:
            abort(400)
        member.group, member.photo, member.orcid = group,photo,orcid
        member.next_contact_at = parse_date(request.form.get('next_contact_at'))
        if request.form.get('acceptance_recorded') == 'on' and not member.accepted_at:
            member.accepted_at = utcnow()
        member.public_consent = request.form.get('public_consent') == 'on'
        member.public_visible = request.form.get('public_visible') == 'on'
        member.available = request.form.get('available') == 'on'
        changed=not ident or db.session.is_modified(member,include_collections=False)
        db.session.add(member)
        db.session.flush()
        if member.contact_note and (member.contact_note!=previous_contact or status!=previous_status):
            db.session.add(StaffContactLog(member_id=member.id,actor_id=session.get('admin_id'),status=status,note=member.contact_note))
        if changed:audit('member.saved','member',member.id,'Estado: '+status)
        db.session.commit()
        flash('Membro guardado. Nenhuma mensagem externa foi enviada.','success')
        return redirect(url_for('staff.team',edit=member.id))
    return render_template('admin/team.html',members=TeamMember.query.filter(TeamMember.removed_at.is_(None)).order_by(TeamMember.name).all(),
                           selected=db.session.get(TeamMember,request.args.get('edit',type=int)) if request.args.get('edit',type=int) else None,
                           admins=AdminUser.query.order_by(AdminUser.display_name).all(),authors=Author.query.order_by(Author.name).all(),
                           roles=TeamRole.query.order_by(TeamRole.name).all(),journals=Journal.query.order_by(Journal.title).all())


@staff_bp.post('/equipa/<int:ident>/mandatos')
@superadmin_required
def appointment(ident):
    validate_csrf()
    member = db.get_or_404(TeamMember,ident)
    if member.removed_at:abort(409)
    role = db.get_or_404(TeamRole,request.form.get('role_id',type=int))
    start,end = parse_date(request.form.get('starts_on'),True),parse_date(request.form.get('ends_on'))
    if end and end < start:
        abort(400,description='O fim deve ser posterior ao início.')
    try:
        hours=float(request.form.get('weekly_hours') or 0)
        if not 0 <= hours <= 168:
            raise ValueError()
    except ValueError:
        abort(400)
    journal_id=request.form.get('journal_id',type=int)
    substitute_id=request.form.get('substitute_id',type=int)
    if journal_id and not db.session.get(Journal,journal_id):
        abort(400)
    if substitute_id and (substitute_id==ident or not db.session.get(TeamMember,substitute_id)):
        abort(400)
    item=TeamAppointment(member=member,role=role,journal_id=journal_id,starts_on=start,ends_on=end,
                         weekly_hours=hours,area=field('area',180),conditions=field('conditions',10000),substitute_id=substitute_id)
    db.session.add(item)
    audit('mandate.created','member',ident,role.name)
    db.session.commit()
    return redirect(url_for('staff.team',edit=ident))


@staff_bp.post('/mandatos/<int:ident>/terminar')
@superadmin_required
def end_appointment(ident):
    validate_csrf()
    item=db.get_or_404(TeamAppointment,ident)
    if not item.active:return redirect(url_for('staff.team',edit=item.member_id))
    item.active=False
    audit('mandate.ended','member',item.member_id,item.role.name)
    db.session.commit()
    return redirect(url_for('staff.team',edit=item.member_id))


@staff_bp.route('/funcoes',methods=['GET','POST'])
@superadmin_required
def roles():
    if request.method=='POST':
        validate_csrf()
        ident=request.form.get('id',type=int)
        role=db.get_or_404(TeamRole,ident) if ident else TeamRole(code=field('code',60,True))
        if not re.fullmatch(r'[a-z][a-z0-9_]{1,59}',role.code):
            abort(400)
        if not ident and TeamRole.query.filter_by(code=role.code).first():
            abort(409,description='Código já utilizado.')
        permissions=request.form.getlist('permissions')
        if not set(permissions)<=set(PERMISSIONS):
            abort(400)
        role.name=field('name',160,True)
        for name in ['purpose','duties','limits']:
            setattr(role,name,field(name,10000))
        preserved_unknown=set(role.permissions or [])-set(PERMISSIONS)
        role.permissions=sorted(set(permissions)|preserved_unknown)
        changed=not ident or db.session.is_modified(role,include_collections=False)
        db.session.add(role)
        db.session.flush()
        if changed:audit('role.saved','role',role.id,', '.join(role.permissions))
        db.session.commit()
        return redirect(url_for('staff.roles',edit=role.id))
    return render_template('admin/roles.html',roles=TeamRole.query.order_by(TeamRole.name).all(),permissions=PERMISSIONS,
                           selected=db.session.get(TeamRole,request.args.get('edit',type=int)) if request.args.get('edit',type=int) else None)


@staff_bp.route('/trabalho',methods=['GET','POST'])
@login_required
def workspace():
    member=current_member()
    manager=has_permission('tasks.manage')
    if request.method=='POST':
        validate_csrf()
        ident=request.form.get('id',type=int)
        if ident:
            task=db.get_or_404(StaffTask,ident)
            if not manager and (not active_member(member) or task.assignee_id!=member.id or not mandates(member)):
                abort(403)
            status=field('status',30,True)
            if status not in TASK_STATES:
                abort(400)
            previous_assignee=task.assignee
            changed=task.status!=status
            if manager and request.form.get('assignee_id',type=int):
                assignee=db.get_or_404(TeamMember,request.form.get('assignee_id',type=int))
                if not active_member(assignee) or not mandates(assignee):abort(400)
                changed=changed or task.assignee_id!=assignee.id
                task.assignee=assignee
            task.status=status
            comment=field('comment',10000)
            if comment and not changed and task.comments and task.comments[-1].actor_id==session.get('admin_id') and task.comments[-1].body==comment:
                comment=''
            if comment:
                db.session.add(TaskComment(task_id=task.id,actor_id=session.get('admin_id'),body=comment))
            if changed or comment:audit('task.updated','task',task.id,status+(' · Comentário adicionado' if comment else ''))
            if previous_assignee.id!=task.assignee_id and active_member(previous_assignee) and mandates(previous_assignee) and previous_assignee.admin_id:
                from internal_notices import emit
                emit(previous_assignee.admin_id,'Tarefa reatribuída: '+task.title,'Esta tarefa deixou de estar sob a sua responsabilidade.',resource=('task',task.id))
        else:
            require('tasks.manage')
            assignee=db.get_or_404(TeamMember,request.form.get('assignee_id',type=int))
            if not active_member(assignee) or not mandates(assignee):
                abort(400,description='Escolha um membro activo com mandato válido.')
            task=StaffTask(title=field('title',240,True),description=field('description',20000),assignee=assignee,
                           due_on=parse_date(request.form.get('due_on'),True),created_by=session.get('admin_id'))
            db.session.add(task)
            db.session.flush()
            audit('task.created','task',task.id)
        db.session.commit()
        return redirect(url_for('staff.workspace'))
    tasks=StaffTask.query
    if not manager:
        tasks=tasks.filter_by(assignee_id=member.id) if active_member(member) and mandates(member) else tasks.filter(db.false())
    assigned_articles=[]
    if active_member(member) and mandates(member) and has_permission('article.review',member=member):
        assigned_articles=(ArticleWorkflow.query.join(Article,Article.id==ArticleWorkflow.article_id)
            .filter(ArticleWorkflow.reviewer_id==member.id,ArticleWorkflow.stage=='review',
                    ArticleWorkflow.reviewed_at.is_(None))
            .order_by(ArticleWorkflow.article_id.desc())
            .all())
        assigned_articles=[flow for flow in assigned_articles
                           if article_scope(Article.query).filter_by(id=flow.article_id).first()]
    return render_template('admin/workspace.html',tasks=tasks.order_by(StaffTask.due_on.asc()).all(),manager=manager,
                           assigned_articles=assigned_articles,
                           members=[m for m in TeamMember.query.order_by(TeamMember.name) if active_member(m) and mandates(m)],
                           member=member,mandates=mandates(member))


@staff_bp.route('/documentos-equipa',methods=['GET','POST'])
@login_required
def documents():
    manager=has_permission('team.manage')
    member=current_member()
    if request.method=='POST':
        validate_csrf()
        require('team.manage')
        target=db.get_or_404(TeamMember,request.form.get('member_id',type=int))
        if target.removed_at:abort(409)
        item=StaffDocument(member=target,title=field('title',200,True),kind=field('kind',30,True),body=field('body',100000))
        if item.kind not in {'agreement','consent','conflict','minutes','other'}:
            abort(400)
        upload=request.files.get('file')
        if upload and upload.filename:
            from submission_uploads import validate_upload
            try:
                data=validate_upload(upload,'main','pdf,docx,txt')
            except ValueError as error:
                abort(400,description=str(error))
            item.filename,item.payload=data['original_name'],data['payload']
        if not item.body and not item.payload:
            abort(400)
        db.session.add(item)
        db.session.flush()
        audit('document.created','document',item.id)
        db.session.commit()
        return redirect(url_for('staff.documents'))
    history=session.get('admin_superuser') and request.args.get('history')=='1'
    query=StaffDocument.query.filter(StaffDocument.removed_at.is_not(None) if history else StaffDocument.removed_at.is_(None))
    if not manager:
        query=query.filter_by(member_id=member.id) if member and member.status not in {'suspended','ended','declined'} else query.filter(db.false())
    return render_template('admin/staff_documents.html',documents=query.order_by(StaffDocument.created_at.desc()).all(),manager=manager,
                           members=TeamMember.query.filter(TeamMember.removed_at.is_(None)).order_by(TeamMember.name).all() if manager else [],member=member)


def own_document(ident):
    item=StaffDocument.query.filter_by(id=ident).with_for_update().populate_existing().first_or_404() if request.method=='POST' else db.get_or_404(StaffDocument,ident)
    member=current_member()
    if item.removed_at and (request.method!='GET' or not session.get('admin_superuser')):abort(410,description='Documento eliminado; não permite novos aceites.')
    if not has_permission('team.manage') and not (member and member.status not in {'suspended','ended','declined'} and member.id==item.member_id):
        abort(404)
    return item


@staff_bp.get('/documentos-equipa/<int:ident>/ficheiro')
@login_required
def document_file(ident):
    item=own_document(ident)
    if not item.payload:
        abort(404)
    return send_file(io.BytesIO(item.payload),as_attachment=True,download_name=item.filename,mimetype='application/octet-stream',max_age=0)


@staff_bp.post('/documentos-equipa/<int:ident>/aceitar')
@login_required
def accept_document(ident):
    validate_csrf()
    item=own_document(ident)
    member=current_member()
    if not member or member.id!=item.member_id or member.status in {'suspended','ended','declined'}:
        abort(403)
    if request.form.get('confirm')!='on':
        abort(400)
    if not item.accepted_at:
        item.accepted_at,item.accepted_by=utcnow(),session.get('admin_id')
        if item.kind=='agreement' and not member.accepted_at:
            member.accepted_at=item.accepted_at
        audit('document.accepted','document',ident)
        db.session.commit()
    return redirect(url_for('staff.documents'))


@staff_bp.route('/notificacoes',methods=['GET','POST'])
@login_required
def notifications():
    from internal_notices import active_inbox, mutate
    if request.method=='POST':
        validate_csrf()
        mutate(request.form.get('action','read'),request.form.get('id',type=int))
        return redirect(url_for('staff.notifications'),code=303)
    page=active_inbox().order_by(StaffNotice.created_at.desc(),StaffNotice.id.desc()).paginate(page=request.args.get('page',1,type=int),per_page=30,error_out=False)
    return render_template('admin/staff_notices.html',notices=page.items,pagination=page)


@staff_bp.get('/notificacoes/<int:ident>/abrir')
@login_required
def open_notice(ident):
    from internal_notices import active_inbox, resource_url
    item=active_inbox().filter_by(id=ident).first_or_404()
    target=resource_url(item)
    if not target:
        flash('O recurso foi eliminado ou já não tem acesso a ele.','warning')
        return redirect(url_for('staff.notifications'))
    return redirect(target)


@staff_bp.get('/api/notificacoes')
@login_required
def notice_summary():
    from flask import jsonify
    from internal_notices import summary
    return jsonify(summary())


@staff_bp.get('/relatorios-equipa')
@login_required
def reports():
    require('reports.read')
    # A report grant is institutional: do not expose confidential manuscript contents.
    return render_template('admin/staff_reports.html',saved_reports=AuditReport.query.filter(AuditReport.removed_at.is_(None)).order_by(AuditReport.id.desc()).all(),members=TeamMember.query.filter(TeamMember.removed_at.is_(None)).all(),tasks=StaffTask.query.all(),
                           reviews=StaffPeerReview.query.all(),audits=GovernanceAudit.query.order_by(GovernanceAudit.created_at.desc()).limit(200).all(),
                           today=date.today(),active_member=active_member)


@staff_bp.route('/pareceres',methods=['GET','POST'])
@login_required
def reviews():
    from submission_models import Manuscript
    member=current_member()
    if request.method=='POST':
        validate_csrf()
        manuscript=db.get_or_404(Manuscript,request.form.get('manuscript_id',type=int))
        from submissions import lock_record
        lock_record(manuscript)
        if not manuscript_access(manuscript,'manuscript.assign'):
            abort(403)
        if manuscript.status not in {'screening','review','revised','reevaluation'}:
            abort(409,description='A submissão não está em fase de avaliação.')
        reviewer=db.get_or_404(TeamMember,request.form.get('reviewer_id',type=int))
        if not reviewer.admin_id or not reviewer.available or not has_permission('manuscript.review',manuscript.journal_id,member=reviewer) or conflicts(reviewer,manuscript):
            abort(400,description='Revisor indisponível, sem mandato ou com autoria nesta submissão.')
        if StaffPeerReview.query.filter_by(manuscript_id=manuscript.id,reviewer_id=reviewer.id,version_number=manuscript.current_version).first():
            abort(409,description='Revisor já convidado para esta versão.')
        due=parse_date(request.form.get('due_on'),True)
        if due<date.today():
            abort(400,description='O prazo deve ser actual ou futuro.')
        item=StaffPeerReview(manuscript_id=manuscript.id,reviewer=reviewer,version_number=manuscript.current_version,
                             assigned_by=session.get('admin_id'),due_on=due)
        db.session.add(item)
        db.session.flush()
        audit('review.assigned','review',item.id)
        db.session.commit()
        return redirect(url_for('staff.reviews',manuscript_id=manuscript.id))
    ident=request.args.get('manuscript_id',type=int)
    selected=db.get_or_404(Manuscript,ident) if ident else None
    can_assign=bool(selected and manuscript_access(selected,'manuscript.assign'))
    manager=bool(selected and (can_assign or manuscript_access(selected,'manuscript.edit')
                              or manuscript_access(selected,'manuscript.decide')))
    if selected and not manager:
        abort(403)
    if not manager and not has_any_permission('manuscript.review'):
        abort(403)
    rows=StaffPeerReview.query
    if manager:
        rows=rows.filter_by(manuscript_id=ident)
    else:
        rows=rows.filter_by(reviewer_id=member.id) if active_member(member) and any('manuscript.review' in a.role.permissions for a in mandates(member)) else rows.filter(db.false())
    records=rows.order_by(StaffPeerReview.due_on).all()
    if not manager:
        records=[r for r in records if not r.manuscript.removed_at and has_permission('manuscript.review',r.manuscript.journal_id)]
    return render_template('admin/staff_reviews.html',reviews=records,selected=selected,manager=manager,can_assign=can_assign,
                           reviewers=[m for m in eligible('manuscript.review',selected.journal_id) if m.admin_id and not conflicts(m,selected)] if can_assign else [])


def reviewer_record(ident):
    item=StaffPeerReview.query.filter_by(id=ident).with_for_update().first_or_404() if request.method=='POST' else db.get_or_404(StaffPeerReview,ident)
    if request.method=='POST':
        from submissions import lock_record
        lock_record(item.manuscript)
    if item.manuscript.removed_at:abort(410,description='Submissão eliminada. Não permite novas acções editoriais.')
    member=current_member()
    if not member or member.id!=item.reviewer_id or not has_permission('manuscript.review',item.manuscript.journal_id):
        abort(404)
    return item


@staff_bp.route('/pareceres/<int:ident>',methods=['GET','POST'])
@login_required
def review_detail(ident):
    item=reviewer_record(ident)
    stale=item.version_number!=item.manuscript.current_version
    if request.method=='POST':
        validate_csrf()
        if stale or item.manuscript.status not in {'screening','review','revised','reevaluation'}:
            abort(409,description='Esta versão já não está em avaliação.')
        action=request.form.get('action')
        if action in {'accept','decline','conflict'} and (item.status=='invited' or (action=='conflict' and item.status=='accepted')):
            if action=='accept':
                if conflicts(item.reviewer,item.manuscript) or request.form.get('no_conflict')!='on':
                    abort(400,description='Declare a ausência de conflitos para aceitar.')
                item.status='accepted'
            else:
                item.status='conflict' if action=='conflict' else 'declined'
                item.conflict_declared=action=='conflict'
                item.conflict_note=field('conflict_note',10000)
        elif action=='submit' and item.status=='accepted' and not conflicts(item.reviewer,item.manuscript):
            item.report=field('report',50000,True)
            item.recommendation=field('recommendation',30,True)
            if item.recommendation not in {'accept','minor_revision','major_revision','reject'} or len(item.report)<50:
                abort(400,description='Informe uma recomendação e um parecer com pelo menos 50 caracteres.')
            item.status,item.submitted_at='submitted',utcnow()
            editor=TeamMember.query.filter_by(admin_id=item.manuscript.editor_id).first() if item.manuscript.editor_id else None
        else:
            abort(409)
        audit('review.'+action,'review',ident)
        db.session.commit()
        return redirect(url_for('staff.review_detail',ident=ident))
    from submission_models import ManuscriptFile, ManuscriptVersion
    files=[]
    if item.status=='accepted' and not stale and not conflicts(item.reviewer,item.manuscript):
        files=ManuscriptFile.query.join(ManuscriptVersion).filter(ManuscriptVersion.manuscript_id==item.manuscript_id,
             ManuscriptVersion.number==item.version_number,ManuscriptFile.kind.in_(['main','figure','table'])).all()
    return render_template('admin/staff_review_detail.html',review=item,files=files,stale=stale)


@staff_bp.get('/pareceres/<int:ident>/ficheiros/<int:file_id>')
@login_required
def review_file(ident,file_id):
    item=reviewer_record(ident)
    from submission_models import ManuscriptFile
    file=db.get_or_404(ManuscriptFile,file_id)
    if (item.status!='accepted' or item.version_number!=item.manuscript.current_version or conflicts(item.reviewer,item.manuscript)
        or item.manuscript.status not in {'screening','review','revised','reevaluation'}
        or file.version.manuscript_id!=item.manuscript_id or file.version.number!=item.version_number or file.kind not in {'main','figure','table'}):
        abort(404)
    return send_file(io.BytesIO(file.payload),as_attachment=True,download_name=file.original_name,mimetype='application/octet-stream',max_age=0)


def article_scope(query):
    if any(has_permission(p) for p in ('article.edit','article.publish','article.approve','article.delete')):
        return query
    member=current_member()
    if not member or not active_member(member) or not mandates(member):
        return query.filter(db.false())
    clauses=[]
    if has_permission('article.write') and member.author_id:
        clauses.append(Article.author_id==member.author_id)
    if has_permission('article.review'):
        clauses.append(Article.id.in_(db.select(ArticleWorkflow.article_id).where(ArticleWorkflow.reviewer_id==member.id)))
    return query.filter(or_(*clauses) if clauses else db.false())


def independent_article_reviewer(member, article, owner_id):
    return bool(member and member.id != owner_id and member.author_id != article.author_id)


def article_edit_access(article):
    if has_permission('article.edit'):
        return
    member=current_member()
    if not has_permission('article.write') or not member or not member.author_id:
        abort(403)
    if article.id and article.author_id!=member.author_id:
        abort(404)
    if article.id and article.status in {'approved','scheduled','published'}:
        abort(409,description='Peça ao editor para reabrir o artigo antes de o alterar.')


def article_editable(article):
    if has_permission('article.edit'):
        return True
    member=current_member()
    return bool(has_permission('article.write') and member and member.author_id
        and (not article.id or article.author_id==member.author_id)
        and article.status not in {'approved','scheduled','published'})


def article_statuses(article):
    # Approval belongs to the workflow; publication has its own route.
    # Approval and publication are workflow transitions, not form status changes.
    # Offering these values to superusers causes a 409 for unapproved articles.
    return ['draft','review'] if article_editable(article) else []


def article_save_guard(article,status,author_id):
    article_edit_access(article)
    if not has_permission('article.edit') and author_id!=current_member().author_id:
        abort(403)
    workflow=db.session.get(ArticleWorkflow,article.id) if article.id else None
    if workflow and author_id != article.author_id:
        owner=TeamMember.query.filter_by(author_id=author_id).first()
        if not owner or owner.removed_at:
            abort(409,description='Associe o novo autor a um colaborador antes de alterar a autoria.')
        if status in {'approved','published','scheduled'}:
            abort(409,description='Alterar a autoria exige nova revisão. Guarde como rascunho.')
        workflow.owner=owner
        workflow.reviewer=workflow.editor=None
        workflow.reviewed_at=workflow.approved_at=None
    if status in {'approved','published','scheduled'}:
        # Legacy content retains the original workflow until attached to a managed workflow.
        if workflow or current_member():
            if not workflow or not workflow.approved_at or workflow.stage not in {'approved','scheduled','published'}:
                abort(409,description='Conclua a revisão e a aprovação no fluxo editorial.')
        require('article.publish' if status in {'published','scheduled'} else 'article.approve')
    elif workflow:
        if not has_permission('article.write') and not has_permission('article.edit'):
            abort(403)
        workflow.stage='draft' if status=='draft' else 'submitted'
        workflow.reviewed_at=workflow.approved_at=None
        workflow.editor=None
    if workflow and status in {'approved','published','scheduled'}:
        changes=any(request.form.get(key,'').strip()!=str(getattr(article,key) or '').strip() for key in ('title','body','summary','references','keywords','doi','image','cover_video'))
        if changes or author_id!=article.author_id or request.form.get('category_id',type=int)!=article.category_id or request.files.get('image_file') or request.files.get('cover_video_file'):
            abort(409,description='Alterações ao conteúdo aprovado exigem nova revisão. Guarde como rascunho.')
        workflow.stage=status


def article_saved(article):
    member=current_member()
    workflow=db.session.get(ArticleWorkflow,article.id)
    if not workflow:
        owner=TeamMember.query.filter_by(author_id=article.author_id).first()
        if owner:
            db.session.add(ArticleWorkflow(article_id=article.id,owner_id=owner.id,stage='submitted' if article.status=='review' else article.status))
    audit('article.saved','article',article.id,article.status)


@staff_bp.route('/fluxo-artigos/<int:ident>',methods=['GET','POST'])
@login_required
def article_workflow(ident):
    article=Article.query.filter_by(id=ident).with_for_update().populate_existing().first_or_404() if request.method=='POST' else db.get_or_404(Article,ident)
    if not article_scope(Article.query).filter_by(id=ident).first():
        abort(404)
    item=ArticleWorkflow.query.filter_by(article_id=ident).with_for_update().first() if request.method=='POST' else db.session.get(ArticleWorkflow,ident)
    if not item:
        if not has_permission('article.edit') and not (has_permission('article.write') and current_member() and current_member().author_id==article.author_id):
            abort(409,description='O editor deve iniciar o fluxo deste artigo.')
        owner=TeamMember.query.filter_by(author_id=article.author_id).first()
        if not owner:
            abort(409,description='Associe primeiro o autor a um membro da equipa.')
        item=ArticleWorkflow(article_id=ident,owner_id=owner.id,owner=owner,
                             stage=article.status if article.status in ARTICLE_STAGES else 'submitted')
        if request.method=='POST':
            db.session.add(item)
    if request.method=='POST':
        validate_csrf()
        action=request.form.get('action')
        action_permission={'assign':'article.edit','reviewed':'article.review','changes':'article.review','approve':'article.approve','publish':'article.publish','schedule':'article.publish','reopen':'article.edit'}
        if action in action_permission:require(action_permission[action])
        member=current_member()
        if action=='submit' and item.stage in {'draft','changes'}:
            if not has_permission('article.edit') and (not member or member.id!=item.owner_id or not has_permission('article.write')):
                abort(403)
            item.stage,article.status='submitted','review'
        elif action=='assign' and item.stage in {'draft','submitted','changes','review'}:
            require('article.edit')
            reviewer=db.get_or_404(TeamMember,request.form.get('reviewer_id',type=int))
            if not reviewer.admin_id or not reviewer.admin or not reviewer.admin.active or not reviewer.available or not independent_article_reviewer(reviewer,article,item.owner_id) or not has_permission('article.review',member=reviewer):
                abort(400,description='Escolha um revisor independente com conta administrativa activa e mandato válido.')
            if item.reviewer_id==reviewer.id and item.stage=='review' and not item.reviewed_at:return redirect(url_for('staff.article_workflow',ident=ident))
            item.reviewer,item.stage,article.status=reviewer,'review','review'
            item.editor=None
            item.approved_at=item.reviewed_at=None
        elif action in {'reviewed','changes'} and item.stage=='review':
            if not member or member.id!=item.reviewer_id or not has_permission('article.review') or not independent_article_reviewer(member,article,item.owner_id):
                abort(403)
            note=field('note',20000,True)
            if item.reviewed_at:
                previous=PortalReview.query.filter_by(article_id=ident,reviewer_id=member.id,action='reviewed').order_by(PortalReview.id.desc()).first()
                if action=='reviewed' and previous and previous.report==note:
                    return redirect(url_for('staff.article_workflow',ident=ident))
                abort(409,description='A revisão já foi concluída. Reabra o fluxo para alterar o parecer.')
            db.session.add(PortalReview(article_id=ident,reviewer_id=member.id,action=action,report=note))
            if action=='reviewed':
                item.reviewed_at=utcnow()
            else:
                item.stage,article.status='changes','draft'
                item.reviewed_at=item.approved_at=None
        elif action=='approve' and item.stage=='review' and item.reviewed_at:
            require('article.approve')
            if member and (member.id in {item.owner_id,item.reviewer_id} or member.author_id==article.author_id):
                abort(403,description='A aprovação exige um responsável diferente do autor e do revisor.')
            if not independent_article_reviewer(item.reviewer,article,item.owner_id):
                abort(409,description='A associação do revisor ao autor mudou. Atribua uma revisão independente.')
            if len(article.body or '')<50:
                abort(400)
            item.editor_id=member.id if member else None
            item.stage,article.status,item.approved_at='approved','approved',utcnow()
        elif action in {'publish','schedule'} and item.stage in {'approved','scheduled','published'} and item.approved_at:
            require('article.publish')
            from admin import parse_datetime
            try:
                scheduled=parse_datetime(request.form.get('scheduled_at')) if action=='schedule' else None
            except (ValueError,TypeError):
                abort(400,description='Data de publicação inválida.')
            if scheduled and scheduled.tzinfo:
                scheduled=scheduled.astimezone(timezone.utc).replace(tzinfo=None)
            if action=='schedule' and (not scheduled or scheduled<=utcnow()):
                abort(400,description='Informe uma data futura de publicação.')
            if (not scheduled and item.stage=='published' and article.status=='published') or (scheduled and item.stage=='scheduled' and article.scheduled_at==scheduled):
                return redirect(url_for('staff.article_workflow',ident=ident))
            item.stage=article.status='scheduled' if scheduled else 'published'
            article.scheduled_at=scheduled
            if not scheduled and not article.published_at:
                article.published_at=utcnow()
        elif action=='reopen':
            require('article.edit')
            item.stage,article.status='draft','draft'
            item.approved_at=item.reviewed_at=None
            item.editor=None
            article.scheduled_at=None
        else:
            abort(409,description='Transição editorial indisponível.')
        audit('article.'+action,'article',ident,field('note',20000)[:1000])
        db.session.commit()
        return redirect(url_for('staff.article_workflow',ident=ident))
    # GET does not persist a newly initialised workflow.
    return render_template('admin/article_workflow.html',article=article,workflow=item,
                           reviewers=[m for m in eligible('article.review') if m.admin_id and m.admin and m.admin.active and m.available and independent_article_reviewer(m,article,item.owner_id)],
                           member=current_member(),reviewer_independent=independent_article_reviewer(item.reviewer,article,item.owner_id),
                           reviews=PortalReview.query.filter_by(article_id=ident).order_by(PortalReview.id).all())


@public_team_bp.get('/equipa')
def public_team():
    members=[m for m in TeamMember.query.filter_by(status='active',public_consent=True,public_visible=True).order_by(TeamMember.name)
             if active_member(m) and mandates(m)]
    return render_template('team.html',members=members,mandates=mandates)


from governance_models import TaskComment

def install_staff_cli(app):
    @app.cli.command('notificar-prazos-equipa')
    def reminders():
        """Create internal reminders once per due date; does not send external messages."""
        today=date.today()
        count=0
        for task in StaffTask.query.filter(StaffTask.due_on<=today,~StaffTask.status.in_(['done','cancelled'])):
            key=f'task:{task.id}:{task.due_on}'
            if active_member(task.assignee) and mandates(task.assignee) and task.assignee.admin_id and not StaffNotice.query.filter_by(source_key=key).first():
                db.session.add(StaffNotice(admin_id=task.assignee.admin_id,source_key=key,subject='Prazo da tarefa: '+task.title,body=str(task.due_on),resource_type='task',resource_id=task.id))
                count+=1
        for item in TeamAppointment.query.filter(TeamAppointment.active.is_(True),TeamAppointment.ends_on<=today):
            key=f'mandate:{item.id}:{item.ends_on}'
            if item.member.admin_id and item.member.admin.active and not item.member.removed_at and not StaffNotice.query.filter_by(source_key=key).first():
                db.session.add(StaffNotice(admin_id=item.member.admin_id,source_key=key,subject='Fim do mandato: '+item.role.name,body=str(item.ends_on),resource_type='member',resource_id=item.member_id))
                count+=1
        for review in StaffPeerReview.query.filter(StaffPeerReview.due_on<=today,StaffPeerReview.status.in_(['invited','accepted'])):
            key=f'review:{review.id}:{review.due_on}'
            if not review.manuscript.removed_at and has_permission('manuscript.review',review.manuscript.journal_id,member=review.reviewer) and review.reviewer.admin_id and not StaffNotice.query.filter_by(source_key=key).first():
                db.session.add(StaffNotice(admin_id=review.reviewer.admin_id,source_key=key,subject='Prazo do parecer: '+review.manuscript.code,body=str(review.due_on),resource_type='manuscript',resource_id=review.manuscript_id))
                count+=1
        db.session.commit()
        print(f'{count} notificações internas criadas.')


def journal_can(journal_id=None, publishing=False, viewing=False):
    from submission_models import Manuscript
    manuscript=Manuscript.query.filter_by(publication_id=journal_id).first() if journal_id else None
    if manuscript:
        if publishing:
            return (manuscript_access(manuscript,'journal.publish')
                    and manuscript.status in {'production','published'})
        return (manuscript_access(manuscript,'manuscript.production')
                or (viewing and manuscript_access(manuscript,'journal.publish')
                    and manuscript.status in {'production','published'}))
    return (has_permission('journal.publish' if publishing else 'journal.manage',journal_id)
            or (viewing and has_permission('journal.publish',journal_id)))


def journal_access(journal_id=None, publishing=False, viewing=False):
    if not journal_can(journal_id,publishing,viewing):
        abort(403,description='A sua função ou o âmbito do mandato não permite esta acção.')


def journal_scope(query):
    ids=[j.id for j in Journal.query.all() if journal_can(j.id,viewing=True)]
    return query.filter(Journal.id.in_(ids))


@staff_bp.route('/remover/<kind>/<int:ident>',methods=['GET','POST'])
@superadmin_required
def remove_record(kind,ident):
    from submission_models import Manuscript
    models={'manuscript':Manuscript,'member':TeamMember,'document':StaffDocument,'report':AuditReport}
    if kind not in models:abort(404)
    query=models[kind].query.filter_by(id=ident)
    item=query.with_for_update().first_or_404() if request.method=='POST' else query.first_or_404()
    # Never remove a membership attached to the founder's identity.
    # Ordinary collaborators can be removed without touching the founder account.
    if kind == 'member' and ((item.admin_id is not None and item.admin_id == session.get('admin_id')) or (item.admin and item.admin.is_superadmin)):
        abort(403,description='Não pode remover a conta do fundador.')
    name=item.name if kind=='member' else item.title
    if kind == 'member' and item.removed_at and request.method == 'GET':
        flash('Este colaborador já foi removido. O histórico permanece disponível.','info')
        return redirect(url_for('staff.team'))
    consequences={
        'manuscript':'Retira a submissão dos fluxos activos e impede novas acções editoriais. Versões, pareceres, decisões, artigos publicados, DOI e ficheiros são preservados.',
        'member':'Revoga todos os mandatos e o acesso administrativo, inclusive sessões abertas. Cancela o convite de colaboração. A conta pública, autoria e histórico são preservados. Responsabilidades pendentes podem ser reatribuídas.',
        'document':'Retira o documento das listas activas e impede novos aceites. Texto, anexo, aceite anterior, datas e esta versão permanecem no histórico do fundador.',
        'report':'Retira este relatório guardado da lista activa. Os eventos de auditoria de origem permanecem intactos.'}
    if request.method=='POST':
        validate_csrf()
        if request.form.get('confirm')!='yes':abort(400)
        if not item.removed_at:
            item.removed_at=utcnow()
            if kind=='member':
                item.status='ended';item.available=False;item.public_visible=False
                for mandate in item.appointments:mandate.active=False
                if item.admin and not item.admin.is_superadmin:
                    item.admin.active=False;item.admin.governance_managed=True
                    item.admin.security_version+=1
            audit(kind+'.removed',kind,ident,name)
            db.session.commit()
        flash('Remoção registada. O histórico foi preservado.','success')
        destination=url_for('staff.responsibilities',ident=ident) if kind=='member' else url_for('staff.documents') if kind=='document' else url_for('staff.reports') if kind=='report' else url_for('admin.submissions_list')
        return redirect(destination,code=303)
    return render_template('admin/remove_confirmation.html',item_name=name,kind=kind,ident=ident,consequence=consequences[kind])


@staff_bp.get('/historico-remocoes')
@superadmin_required
def removed_history():
    from submission_models import Manuscript
    return render_template('admin/removed_history.html',manuscripts=Manuscript.query.filter(Manuscript.removed_at.is_not(None)).all(),
        members=TeamMember.query.filter(TeamMember.removed_at.is_not(None)).all(),
        documents=StaffDocument.query.filter(StaffDocument.removed_at.is_not(None)).all(),
        saved_reports=AuditReport.query.filter(AuditReport.removed_at.is_not(None)).all())


@staff_bp.get('/historico-submissoes/<int:ident>')
@superadmin_required
def archived_manuscript(ident):
    from submission_models import Manuscript
    m=db.get_or_404(Manuscript,ident)
    return render_template('admin/archived_manuscript.html',manuscript=m,reviews=StaffPeerReview.query.filter_by(manuscript_id=ident).all())


@staff_bp.post('/relatorios-equipa/guardar')
@login_required
def save_report():
    validate_csrf();require('reports.read')
    item=AuditReport(title=field('title',200,True),created_by=session.get('admin_id'),snapshot=[dict(id=a.id,date=a.created_at.isoformat(),actor=a.actor_name,action=a.action,entity=a.entity,entity_id=a.entity_id,detail=a.detail) for a in GovernanceAudit.query.order_by(GovernanceAudit.id.desc()).limit(1000)])
    db.session.add(item);db.session.flush();audit('report.created','report',item.id);db.session.commit()
    return redirect(url_for('staff.report_detail',ident=item.id),code=303)


@staff_bp.get('/relatorios-equipa/<int:ident>')
@login_required
def report_detail(ident):
    require('reports.read');item=db.get_or_404(AuditReport,ident)
    if item.removed_at and not session.get('admin_superuser'):abort(410)
    return render_template('admin/report_detail.html',report=item)


@staff_bp.route('/equipa/<int:ident>/responsabilidades',methods=['GET','POST'])
@superadmin_required
def responsibilities(ident):
    from submission_models import Manuscript
    member=db.get_or_404(TeamMember,ident)
    tasks=StaffTask.query.filter(StaffTask.assignee_id==ident,StaffTask.status.notin_(['done','cancelled'])).all()
    manuscripts=Manuscript.query.filter(Manuscript.editor_id==member.admin_id,Manuscript.removed_at.is_(None),Manuscript.status.notin_(['published','rejected'])).all() if member.admin_id else []
    flows=ArticleWorkflow.query.filter(or_(ArticleWorkflow.owner_id==ident,ArticleWorkflow.reviewer_id==ident,ArticleWorkflow.editor_id==ident),ArticleWorkflow.stage!='published').all()
    reviews=StaffPeerReview.query.join(StaffPeerReview.manuscript).filter(StaffPeerReview.reviewer_id==ident,StaffPeerReview.status.in_(['invited','accepted']),Manuscript.removed_at.is_(None)).all()
    if request.method=='POST':
        validate_csrf();target=db.get_or_404(TeamMember,request.form.get('target_id',type=int))
        if not active_member(target) or not mandates(target) or not target.available:abort(400)
        kind=request.form.get('kind');rid=request.form.get('resource_id',type=int)
        item=next((t for t in (tasks if kind=='task' else manuscripts if kind=='editor' else reviews if kind=='review' else flows) if (t.article_id if kind in {'portal_reviewer','portal_editor'} else t.id)==rid),None)
        if not item:abort(404)
        if kind=='task':item.assignee_id=target.id
        elif kind=='editor':
            if not target.admin_id or not has_permission('manuscript.edit',item.journal_id,member=target) or conflicts(target,item):abort(400)
            item.editor_id=target.admin_id
        elif kind=='review':
            if not target.admin_id or not has_permission('manuscript.review',item.manuscript.journal_id,member=target) or conflicts(target,item.manuscript):abort(400)
            if StaffPeerReview.query.filter_by(manuscript_id=item.manuscript_id,reviewer_id=target.id,version_number=item.version_number).first():abort(409)
            item.status='cancelled'
            new=StaffPeerReview(manuscript_id=item.manuscript_id,reviewer_id=target.id,version_number=item.version_number,assigned_by=session.get('admin_id'),due_on=max(item.due_on,date.today()))
            db.session.add(new);db.session.flush();audit('review.assigned','review',new.id)
        elif kind in {'portal_reviewer','portal_editor'}:
            # Serialize with timed publication and refresh the state after locking.
            article=Article.query.filter_by(id=item.article_id).with_for_update().populate_existing().first_or_404()
            item=ArticleWorkflow.query.filter_by(article_id=item.article_id).with_for_update().populate_existing().first_or_404()
            if article.status=='published' or item.stage=='published':abort(409)
            permission='article.review' if kind=='portal_reviewer' else 'article.approve'
            if not target.admin_id or not target.admin or not target.admin.active or not has_permission(permission,member=target) or not independent_article_reviewer(target,article,item.owner_id):abort(400)
            if kind=='portal_reviewer':
                if item.editor_id==target.id:abort(400)
                if item.reviewer_id!=target.id:
                    item.reviewer=target
                    item.reviewed_at=item.approved_at=None
                    item.editor=None
                    item.stage=item.article.status='review'
                    item.article.scheduled_at=None
            else:
                if item.reviewer_id==target.id:abort(400)
                item.editor=target
        else:abort(400)
        entity='task' if kind=='task' else 'manuscript' if kind=='editor' else 'article' if kind in {'portal_reviewer','portal_editor'} else 'review'
        audit('responsibility.reassigned',entity,rid,'Membro '+str(ident)+' → '+str(target.id));db.session.commit()
        return redirect(url_for('staff.responsibilities',ident=ident),code=303)
    return render_template('admin/responsibilities.html',member=member,tasks=tasks,manuscripts=manuscripts,flows=flows,reviews=reviews,
        candidates=[m for m in TeamMember.query.order_by(TeamMember.name) if m.id!=ident and active_member(m) and mandates(m) and m.available])


@staff_bp.app_context_processor
def notification_context():
    from internal_notices import active_inbox
    if not session.get('admin_authenticated') or not request.path.startswith('/admin'):
        return dict(notice_unread=0,notice_recent=[])
    query=active_inbox()
    return dict(notice_unread=query.filter(StaffNotice.read_at.is_(None)).count(),notice_recent=query.order_by(StaffNotice.created_at.desc(),StaffNotice.id.desc()).limit(5).all())



