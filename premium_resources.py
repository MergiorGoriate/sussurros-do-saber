"""Private resource validation and catalogue rules, isolated from public articles."""
import hashlib
import io
import json
import posixpath
import re
import zipfile
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from xml.etree import ElementTree

import bleach
from flask import abort, request, session
from sqlalchemy import exists, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from models import db, utcnow
from premium_models import (PremiumContent, PremiumResource, PremiumPlan, PremiumFile,
                            PremiumCollectionItem, PremiumEvent, PremiumUsage)

TYPES = {'ebook':'Livro digital', 'document':'Documento educativo', 'slides':'Apresentação',
         'video':'Vídeo educativo', 'course':'Curso e formação', 'series':'Série educativa',
         'event':'Evento e seminário', 'collection':'Colecção de aprendizagem', 'interview':'Entrevista'}
STATES = {'draft':'Rascunho','published':'Publicado','scheduled':'Programado',
          'suspended':'Suspenso','archived':'Arquivado'}
FORMATS = {'pdf':'PDF','epub':'EPUB','docx':'Word','pptx':'PowerPoint','mp4':'MP4','webm':'WebM'}
MAPUTO = ZoneInfo('Africa/Maputo')


def detail(item):
    return db.session.get(PremiumResource, item.id) or PremiumResource(
        content_id=item.id, resource_type=item.kind, metadata_fields={}, state='published' if item.published else 'draft',
        plan_ids=[], download_allowed=False, featured=False, certificate_enabled=False)


def visible_clause():
    blocked = select(PremiumResource.content_id).where(PremiumResource.state != 'published')
    return ~PremiumContent.id.in_(blocked)


def require_access(item, *, allow_grace=True):
    from premium import subscription_for
    from submissions import researcher
    resource = detail(item)
    if not item.published or resource.state != 'published': abort(404)
    if item.open_access_required: return resource
    sub = subscription_for(researcher())
    from premium_members import can_access
    if not can_access(sub,item,resource,allow_grace=allow_grace):
        abort(403, description='Este recurso exige uma subscrição válida de um dos planos autorizados.')
    from premium_models import PremiumEnrollment
    enrollment=db.session.get(PremiumEnrollment,(sub.owner_id,item.id))
    if enrollment and (enrollment.state=='suspended' or enrollment.deadline and utcnow()>=enrollment.deadline):
        abort(403,description='O prazo deste curso terminou. Pode solicitar prorrogação ou reactivação na área de pedidos.')
    return resource


def reader():
    from submissions import researcher
    account = researcher()
    if not account or not account.active or not account.verified: abort(403)
    return account


def record_usage(item, action):
    from submissions import researcher
    account = researcher()
    if not account: return  # Anonymous catalogue browsing is not fabricated as member usage.
    now = utcnow()
    from premium import entitled, subscription_for
    from premium_models import PremiumAccessHistory
    if entitled(subscription_for(account)):
        history_insert=postgres_insert if db.engine.dialect.name == 'postgresql' else sqlite_insert
        db.session.execute(history_insert(PremiumAccessHistory).values(owner_id=account.id,content_id=item.id,first_access_at=now).on_conflict_do_nothing())
    values = dict(event_key=f'{account.id}:{item.id}:{action}:{now.date()}',content_id=item.id,
                  action=action,created_at=now)
    insert = postgres_insert if db.engine.dialect.name == 'postgresql' else sqlite_insert
    db.session.execute(insert(PremiumUsage).values(**values).on_conflict_do_nothing(index_elements=['event_key']))


def local_input(value):
    return value.replace(tzinfo=timezone.utc).astimezone(MAPUTO).strftime('%Y-%m-%dT%H:%M') if value else ''


def parse_local(value):
    try:
        result = datetime.fromisoformat(value)
        if result.tzinfo is not None: raise ValueError()
        return result.replace(tzinfo=MAPUTO).astimezone(timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError, OverflowError):
        raise ValueError('Indique uma data e hora válidas em Moçambique.') from None


def integer(value, low=1, high=2147483647):
    if not re.fullmatch(r'\d{1,10}', str(value)) or not low <= int(value) <= high:
        raise ValueError('Número fora dos limites permitidos.')
    return int(value)


def safe_url(value):
    if not value: return ''
    parsed = urlsplit(value)
    if len(value)>1000 or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Utilize uma ligação HTTPS válida, sem credenciais.')
    return value


def archive(payload):
    try:
        zipped = zipfile.ZipFile(io.BytesIO(payload))
        entries = zipped.infolist()
        if len(entries)>2000 or sum(e.file_size for e in entries)>100*1024*1024:
            raise ValueError()
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in entry.filename
                    or entry.flag_bits & 1 or entry.file_size>20*1024*1024
                    or entry.file_size>max(1024*1024,entry.compress_size*200)):
                raise ValueError()
        if zipped.testzip() is not None: raise ValueError()
        return zipped
    except (zipfile.BadZipFile, RuntimeError, ValueError, OSError):
        raise ValueError('Arquivo inválido, cifrado ou excessivamente comprimido.') from None


def epub_chapters(payload):
    with archive(payload) as zipped:
        if zipped.read('mimetype').strip() != b'application/epub+zip': raise ValueError('EPUB inválido.')
        def xml(name):
            data=zipped.read(name)
            if len(data)>2*1024*1024 or b'\x00' in data or re.search(br'<!\s*(?:DOCTYPE|ENTITY)',data,re.I): raise ValueError('XML não permitido no EPUB.')
            return ElementTree.fromstring(data)
        root=xml('META-INF/container.xml')
        node=next((e for e in root.iter() if e.tag.endswith('rootfile')),None)
        if node is None: raise ValueError('EPUB sem estrutura de leitura.')
        package=node.attrib.get('full-path','')
        if package not in zipped.namelist(): raise ValueError('EPUB sem pacote válido.')
        document=xml(package)
        manifest={e.attrib.get('id'):e.attrib.get('href','') for e in document.iter() if e.tag.endswith('}item')}
        chapters=[]
        for element in document.iter():
            if not element.tag.endswith('}itemref'):continue
            name=posixpath.normpath(posixpath.join(posixpath.dirname(package),manifest.get(element.attrib.get('idref'),'')))
            if name.startswith('../') or name not in zipped.namelist() or not name.lower().endswith(('.html','.xhtml','.htm')):
                raise ValueError('Capítulo inválido no EPUB.')
            text=zipped.read(name).decode('utf-8-sig')
            if len(text)>2*1024*1024:raise ValueError('Capítulo demasiado extenso.')
            # No scripts, forms, remote media, CSS or active links cross into the portal.
            from bs4 import BeautifulSoup
            soup=BeautifulSoup(text,'html.parser')
            for node in soup.select('script,style,iframe,object,embed,form,svg,math'):node.decompose()
            body=str(soup.body or soup)
            chapters.append(bleach.clean(body,tags=['p','h1','h2','h3','h4','h5','h6','ul','ol','li','blockquote','em','strong','br','hr','table','thead','tbody','tr','th','td','sup','sub'],attributes={},strip=True))
        if not chapters or len(chapters)>500:raise ValueError('EPUB sem capítulos suportados.')
        return chapters


def save_file(item, upload, role, replace_id=None):
    if not upload or not upload.filename:return None
    if role not in {'cover','attachment','video'}:raise ValueError('Tipo de ficheiro inválido.')
    limit=(40 if role=='video' else 25)*1024*1024
    payload=upload.stream.read(limit+1)
    if not payload or len(payload)>limit:raise ValueError('Ficheiro vazio ou acima do limite de '+str(limit//1024//1024)+' MB.')
    name=upload.filename.replace('\\','/').rsplit('/',1)[-1][:180]
    extension=name.rsplit('.',1)[-1].lower()
    if role=='cover':
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(io.BytesIO(payload)) as image:
                if image.width*image.height>20000000:raise ValueError()
                image.thumbnail((1600,1600));out=io.BytesIO();image.convert('RGB').save(out,'JPEG',quality=88)
                payload=out.getvalue();mime='image/jpeg';name='capa.jpg'
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError):
            raise ValueError('Capa inválida; utilize uma imagem até 20 megapíxeis.') from None
    elif role=='video':
        if extension=='mp4' and len(payload)>12 and payload[4:8]==b'ftyp':mime='video/mp4'
        elif extension=='webm' and payload.startswith(b'\x1aE\xdf\xa3'):mime='video/webm'
        else:raise ValueError('Utilize um vídeo MP4 ou WebM válido.')
    elif extension=='pdf':
        from pypdf import PdfReader
        try:
            if not payload.startswith(b'%PDF-'):raise ValueError()
            pdf=PdfReader(io.BytesIO(payload))
            if pdf.is_encrypted or not len(pdf.pages):raise ValueError()
            root=pdf.trailer['/Root']
            names=root.get('/Names')
            names=names.get_object() if names is not None else {}
            if '/OpenAction' in root or '/AA' in root or '/JavaScript' in names:raise ValueError()
            if any('/AA' in page for page in pdf.pages):raise ValueError()
        except Exception:
            raise ValueError('PDF inválido, cifrado ou com acções automáticas não permitidas.') from None
        mime='application/pdf'
    elif extension in {'epub','docx','pptx'}:
        try:
            with archive(payload) as zipped:
                names=zipped.namelist()
                if any('vbaproject' in n.lower() for n in names):raise ValueError()
                if extension!='epub' and ('[Content_Types].xml' not in names or not any(n.startswith('word/' if extension=='docx' else 'ppt/') for n in names)):raise ValueError()
            if extension=='epub':epub_chapters(payload)
        except (ValueError, KeyError, ElementTree.ParseError, UnicodeError):raise ValueError('Documento inválido ou com componentes não permitidos.') from None
        mime={'epub':'application/epub+zip','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation'}[extension]
    else:raise ValueError('Formatos aceites: PDF, EPUB, DOCX e PPTX.')
    if replace_id:
        previous=PremiumFile.query.filter_by(id=integer(replace_id),content_id=item.id,role=role).first()
        if not previous:raise ValueError('O ficheiro a substituir não pertence a este recurso.')
    else:
        previous=PremiumFile.query.filter_by(content_id=item.id,role=role).first() if role=='cover' else None
    if previous:
        previous.name,previous.mime,previous.size,previous.digest,previous.payload=name,mime,len(payload),hashlib.sha256(payload).hexdigest(),payload
        return previous
    row=PremiumFile(content_id=item.id,role=role,name=name,mime=mime,size=len(payload),digest=hashlib.sha256(payload).hexdigest(),payload=payload)
    db.session.add(row);return row


def save_details(item):
    """Called in the same transaction as the existing catalogue form."""
    if 'resource_type' not in request.form:return
    resource=detail(item)
    kind=request.form.get('resource_type','')
    state=request.form.get('resource_state','draft')
    if kind not in TYPES or state not in STATES:raise ValueError('Tipo ou estado do recurso inválido.')
    data={}
    for field,limit in [('subtitle',300),('author',300),('science_area',180),('language',80),('publisher',180),('year',4),('isbn',80),('doi',180),('license',1000),('instructor',300),('objectives',4000)]:
        value=request.form.get(field,'').strip()
        if len(value)>limit:raise ValueError('Campo demasiado extenso: '+field)
        data[field]=value
    if data['year']:integer(data['year'],1000,9999)
    for field in ('completion_days',):
        if field in request.form:
            raw=request.form.get(field,'').strip()
            if raw:data[field]=integer(raw,1,3650)
        elif field in resource.metadata_fields:data[field]=resource.metadata_fields[field]
    ids=[]
    for value in request.form.getlist('allowed_plan'):
        ident=integer(value)
        if not db.session.get(PremiumPlan,ident):raise ValueError('Plano inexistente.')
        if ident not in ids:ids.append(ident)
    if state in {'published','scheduled'} and request.form.get('rights_confirmed')!='on':
        raise ValueError('Confirme os direitos de utilização e distribuição antes de publicar.')
    data['rights_confirmed']=request.form.get('rights_confirmed')=='on'
    was_public=resource.state=='published'
    resource.resource_type,resource.metadata_fields,resource.state=kind,data,state
    resource.plan_ids=ids;resource.download_allowed=request.form.get('download_allowed')=='on'
    resource.featured=request.form.get('featured')=='on'
    resource.certificate_enabled=request.form.get('certificate_enabled')=='on' and kind=='course'
    resource.publish_at=parse_local(request.form.get('publish_at')) if state=='scheduled' else None
    if resource.publish_at and resource.publish_at<=utcnow():raise ValueError('Escolha uma data futura para a publicação programada.')
    item.published=state=='published'
    if item.published and not was_public:resource.notification_done=False;resource.notification_cursor=0
    db.session.add(resource)
    for role in ('cover','attachment','video'):save_file(item,request.files.get(role),role,request.form.get('replace_file_'+role))
    if kind=='collection':
        if request.form.get('collection_picker')=='on':
            values=[integer(v) for v in request.form.getlist('collection_member')]
            values.sort(key=lambda ident:integer(request.form.get('collection_order_'+str(ident),'1'),1,1000))
        else:
            raw=request.form.get('collection_items','').strip()
            values=[integer(v.strip()) for v in raw.split(',') if v.strip()]
        if len(values)>50 or len(set(values))!=len(values) or item.id in values:raise ValueError('Colecção inválida; utilize até 50 recursos diferentes.')
        for ident in values:
            child=db.session.get(PremiumContent,ident)
            if not child or detail(child).resource_type=='collection':raise ValueError('Escolha recursos existentes, sem incluir outras colecções.')
        PremiumCollectionItem.query.filter_by(collection_id=item.id).delete(synchronize_session=False)
        db.session.add_all([PremiumCollectionItem(collection_id=item.id,content_id=i,position=p) for p,i in enumerate(values,1)])
    if kind=='event':
        event=db.session.get(PremiumEvent,item.id) or PremiumEvent(content_id=item.id)
        event.starts_at=parse_local(request.form.get('event_start'))
        event.ends_at=parse_local(request.form.get('event_end'))
        if event.ends_at<=event.starts_at:raise ValueError('O evento deve terminar depois do início.')
        event.mode=request.form.get('event_mode','')
        if event.mode not in {'virtual','presencial','hybrid'}:raise ValueError('Modalidade inválida.')
        event.capacity=integer(request.form.get('capacity'),1,100000)
        event.speakers=request.form.get('speakers','').strip();event.venue=request.form.get('venue','').strip()
        if len(event.speakers)>1000 or len(event.venue)>500:raise ValueError('Descrição do evento demasiado extensa.')
        event.meeting_url=safe_url(request.form.get('meeting_url','').strip())
        from premium_models import PremiumRegistration
        occupied=PremiumRegistration.query.filter_by(content_id=item.id).filter(PremiumRegistration.state!='cancelled').count()
        if event.capacity<occupied:raise ValueError('A capacidade não pode ser inferior ao número de inscrições activas.')
        db.session.add(event)

