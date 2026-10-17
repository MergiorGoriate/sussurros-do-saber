"""Transactional, private recipient inbox. No external delivery or URL from input."""
import uuid
from flask import session, url_for
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from models import db, AdminUser, utcnow, Article
from governance_models import StaffNotice, TeamMember, StaffTask, StaffDocument, AuditReport, StaffPeerReview


EVENT_LABELS={
 'member.saved':'Colaboração actualizada','member.invited':'Convite de colaboração registado',
 'member.removed':'Colaborador removido','mandate.created':'Novo mandato','mandate.ended':'Mandato terminado',
 'task.created':'Nova tarefa atribuída','task.updated':'Tarefa actualizada','responsibility.reassigned':'Responsabilidade reatribuída',
 'document.created':'Documento disponibilizado','document.accepted':'Aceite registado','document.removed':'Documento eliminado',
 'report.created':'Relatório disponibilizado','report.removed':'Relatório eliminado',
 'review.assigned':'Convite para parecer','review.accept':'Parecer aceite','review.decline':'Convite recusado','review.conflict':'Conflito declarado','review.submit':'Parecer entregue',
 'manuscript.submitted':'Nova submissão','manuscript.revised':'Nova versão submetida','manuscript.editor_assigned':'Editor atribuído',
 'manuscript.decision':'Decisão editorial registada','manuscript.published':'Artigo científico publicado','manuscript.prepared_for_publication':'Produção editorial iniciada',
 'manuscript.publication_hidden':'Publicação ocultada','manuscript.internal_note':'Nota editorial registada','manuscript.removed':'Submissão eliminada',
 'article.submit':'Artigo submetido para revisão','article.assign':'Revisor atribuído','article.reviewed':'Revisão concluída','article.changes':'Correcções solicitadas',
 'article.approve':'Artigo aprovado','article.publish':'Artigo publicado','article.schedule':'Publicação programada','article.saved':'Artigo guardado','article.reopen':'Artigo reaberto como rascunho'}


def emit(admin_id, subject, body='', *, researcher_id=None, key=None, resource=None):
    # Atomic uniqueness also protects concurrency. Deletion retains the source key.
    values=dict(admin_id=admin_id, researcher_id=researcher_id, subject=subject[:240], body=body[:10000],
                source_key=((key or uuid.uuid4().hex)[:140]+(':researcher:'+str(researcher_id) if researcher_id is not None else ':admin:'+str(admin_id)))[:180], created_at=utcnow(),
                resource_type=resource[0] if resource else None, resource_id=resource[1] if resource else None)
    insert = postgres_insert if db.engine.dialect.name == 'postgresql' else sqlite_insert
    db.session.execute(insert(StaffNotice).values(**values).on_conflict_do_nothing(index_elements=['source_key']))


def founders():
    ids=[a.id for a in AdminUser.query.filter_by(active=True,is_superadmin=True)]
    # Environment-authenticated founder uses the existing null administrator identity.
    return ids+[None]


def recipients(permission, journal_id=None):
    from governance import has_permission
    return set(founders()+[m.admin_id for m in TeamMember.query if m.admin_id and has_permission(permission,journal_id,member=m)])


def dispatch(action, entity, ident, detail='', key=None):
    """Called within the operation transaction; never on failed operations."""
    from governance import active_member, mandates, has_permission, conflicts
    from submission_models import Manuscript
    event_key=key or uuid.uuid4().hex
    targets=set(); resource=(entity,ident); subject=action; body=detail
    if entity=='member':
        member=db.session.get(TeamMember,ident)
        if member and member.admin_id: targets.add(member.admin_id)
        targets.update(recipients('team.manage'));subject='Actualização da colaboração'
        body=EVENT_LABELS.get(action,action)+' · '+detail
    elif entity=='role':
        for m in TeamMember.query:
            if m.admin_id and any(a.active and a.role_id==ident for a in m.appointments):targets.add(m.admin_id)
        resource=('member',None);subject='Função actualizada';body='Consulte as permissões efectivas na sua área de trabalho.'
    elif entity=='task':
        task=db.session.get(StaffTask,ident)
        if not task:return
        if active_member(task.assignee) and mandates(task.assignee):targets.add(task.assignee.admin_id)
        if task.created_by in recipients('tasks.manage'):targets.add(task.created_by)
        targets.update(recipients('tasks.manage'));subject='Tarefa: '+task.title;body=EVENT_LABELS.get(action,action)+' · '+detail
    elif entity=='document':
        doc=db.session.get(StaffDocument,ident)
        if not doc:return
        targets.add(doc.member.admin_id) if doc.member.admin_id else None
        if action in {'document.accepted','document.removed'}:targets.update(recipients('team.manage'))
        subject='Documento: '+doc.title;body=EVENT_LABELS.get(action,action)+' · '+('O histórico de aceite foi preservado.' if doc.removed_at else detail)
    elif entity=='report':
        report=db.session.get(AuditReport,ident)
        targets.update(recipients('reports.read'));subject='Relatório: '+report.title;body=EVENT_LABELS.get(action,action)
    elif entity in {'manuscript','review'}:
        if action.startswith('publication.'):return
        review=db.session.get(StaffPeerReview,ident) if entity=='review' else None
        manuscript=review.manuscript if review else db.session.get(Manuscript,ident)
        if not manuscript:return
        resource=('manuscript',manuscript.id);subject='Submissão '+(manuscript.code or '#'+str(manuscript.id))
        body=EVENT_LABELS.get(action,action)+' · '+manuscript.status # Never copy confidential notes into a general inbox.
        targets.update(founders())
        for m in TeamMember.query:
            if not m.admin_id or conflicts(m,manuscript):continue
            if has_permission('manuscript.assign',manuscript.journal_id,member=m) or has_permission('manuscript.decide',manuscript.journal_id,member=m) or (manuscript.editor_id==m.admin_id and has_permission('manuscript.edit',manuscript.journal_id,member=m)):
                targets.add(m.admin_id)
            if action in {'manuscript.submitted','manuscript.revised','manuscript.decision','manuscript.published','manuscript.removed'} and has_permission('manuscript.read',manuscript.journal_id,member=m):targets.add(m.admin_id)
        if action in {'manuscript.decision','manuscript.published','manuscript.removed'}:
            for peer in StaffPeerReview.query.filter_by(manuscript_id=manuscript.id,version_number=manuscript.current_version):
                if peer.status in {'accepted','submitted'} and peer.reviewer.admin_id and has_permission('manuscript.review',manuscript.journal_id,member=peer.reviewer):targets.add(peer.reviewer.admin_id)
        if manuscript.status in {'accepted','production','published'}:
            targets.update(recipients('manuscript.production',manuscript.journal_id))
        if manuscript.status in {'production','published'}:
            targets.update(recipients('journal.publish',manuscript.journal_id))
        if review and active_member(review.reviewer) and has_permission('manuscript.review',manuscript.journal_id,member=review.reviewer):
            targets.add(review.reviewer.admin_id)
        if action in {'manuscript.submitted','manuscript.revised','manuscript.decision','manuscript.published','manuscript.prepared_for_publication','manuscript.publication_hidden','manuscript.removed'}:
            emit(None,subject,body,researcher_id=manuscript.owner_id,key=event_key+':researcher:'+str(manuscript.owner_id),resource=resource)
    elif entity=='article':
        article=db.session.get(Article,ident)
        if not article:return
        from governance_models import ArticleWorkflow
        flow=db.session.get(ArticleWorkflow,ident)
        subject='Artigo: '+article.title;body=EVENT_LABELS.get(action,action)+' · '+detail
        if flow:
            for member in [flow.owner,flow.reviewer,flow.editor]:
                if member and member.admin_id and active_member(member) and mandates(member):targets.add(member.admin_id)
        permission='article.publish' if action=='article.approve' else 'article.approve' if action=='article.reviewed' else None
        if action=='article.submit' or (action=='article.saved' and flow and flow.stage=='submitted'):
            permission='article.edit'
        if permission:targets.update(recipients(permission))
    else:return
    for target in targets:
        emit(target,subject,body,key=event_key+':admin:'+str(target),resource=resource)


def inbox(*, public=False):
    if public:
        return StaffNotice.query.filter_by(researcher_id=session.get('researcher_id'),admin_id=None)
    ident=session.get('admin_id')
    return StaffNotice.query.filter_by(admin_id=ident,researcher_id=None)


def active_inbox(*, public=False):
    query=inbox(public=public).filter(StaffNotice.removed_at.is_(None))
    if public:
        from reader_accounts import ReaderJournal
        from models import Journal
        visible=db.select(ReaderJournal.journal_id).join(Journal).where(ReaderJournal.owner_id==session.get('researcher_id'),ReaderJournal.following.is_(True),Journal.published.is_(True))
        query=query.filter(db.or_(StaffNotice.resource_type.is_(None),StaffNotice.resource_type!='reader_journal',StaffNotice.resource_id.in_(visible)))
    return query


def resource_url(item, *, public=False):
    """Revalidate current permissions on opening; no stale notification grants access."""
    from governance import has_permission, manuscript_access, article_scope, current_member, active_member, mandates
    from submission_models import Manuscript
    kind,ident=item.resource_type,item.resource_id
    if kind=='manuscript':
        m=db.session.get(Manuscript,ident)
        if not m or m.removed_at:return None
        if public:return url_for('submissions.detail',ident=m.id) if m.owner_id==session.get('researcher_id') else None
        if manuscript_access(m):return url_for('admin.submission_detail',ident=m.id)
        from governance import journal_can
        if m.publication_id and journal_can(m.publication_id,viewing=True):return url_for('journal_preview',journal_id=m.publication_id)
        member=current_member()
        if member and has_permission('manuscript.review',m.journal_id):
            review=StaffPeerReview.query.filter_by(manuscript_id=m.id,reviewer_id=member.id).order_by(StaffPeerReview.id.desc()).first()
            if review:return url_for('staff.review_detail',ident=review.id)
    if kind=='reader_journal' and public:
        from models import Journal
        from reader_accounts import ReaderJournal
        journal=db.session.get(Journal,ident)
        watching=ReaderJournal.query.filter_by(owner_id=session.get('researcher_id'),journal_id=ident,following=True).first()
        if journal and journal.published and watching:return url_for('journal_detail',slug=journal.slug)
    if public:return None
    if kind=='member':
        if ident and has_permission('team.manage'):return url_for('staff.team',edit=ident)
        return url_for('staff.workspace')
    if kind=='task':
        t=db.session.get(StaffTask,ident);member=current_member()
        if t and (has_permission('tasks.manage') or (active_member(member) and mandates(member) and t.assignee_id==member.id)):
            return url_for('staff.workspace')+'#tarefa-'+str(t.id)
    if kind=='document':
        d=db.session.get(StaffDocument,ident);member=current_member()
        if d and not d.removed_at and (has_permission('team.manage') or (member and member.id==d.member_id and member.status not in {'suspended','ended','declined'})):
            return url_for('staff.documents')+'#documento-'+str(d.id)
    if kind=='report' and has_permission('reports.read'):
        r=db.session.get(AuditReport,ident)
        if r and not r.removed_at:return url_for('staff.report_detail',ident=r.id)
    if kind=='article' and article_scope(Article.query).filter_by(id=ident).first():return url_for('staff.article_workflow',ident=ident)
    return None


def mutate(action, ident=None, *, public=False):
    from flask import abort
    query=inbox(public=public)
    if action=='read_all':
        query.filter(StaffNotice.removed_at.is_(None),StaffNotice.read_at.is_(None)).update({'read_at':utcnow()},synchronize_session='fetch')
    else:
        item=query.filter_by(id=ident).with_for_update().first_or_404()
        if action=='delete':
            if not item.removed_at:item.removed_at=utcnow()
        elif action=='read':
            if not item.read_at and not item.removed_at:item.read_at=utcnow()
        else:abort(400)
    db.session.commit()


def summary(*,public=False):
    if public:
        from reader_accounts import sync_internal_updates
        from submissions import researcher
        sync_internal_updates(researcher())
    query=active_inbox(public=public)
    endpoint='submissions.open_internal_notice' if public else 'staff.open_notice'
    return dict(unread=query.filter(StaffNotice.read_at.is_(None)).count(),items=[dict(id=n.id,title=n.subject,description=n.body,date=n.created_at.strftime('%d/%m/%Y %H:%M')+' UTC',unread=not bool(n.read_at),url=url_for(endpoint,ident=n.id) if n.resource_type else None) for n in query.order_by(StaffNotice.created_at.desc(),StaffNotice.id.desc()).limit(5)])

