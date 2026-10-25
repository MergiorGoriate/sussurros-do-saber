"""Optional asynchronous silent slideshow from approved, immutable scientific slides."""
import io
import os
import secrets
import shutil
import subprocess
import tempfile
import hashlib
from pathlib import Path
from datetime import timedelta
from flask import abort, request, session, redirect, send_file
import click
from sqlalchemy import update
from models import db, utcnow
from dissemination_models import DisseminationMaterial
from dissemination_ai import GenerationError
from dissemination_service import asset_root, current_version, export_allowed, read_asset, event


class DisseminationVideo(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    material_id=db.Column(db.Integer,db.ForeignKey('dissemination_material.id'),nullable=False,index=True)
    version=db.Column(db.Integer,nullable=False)
    state=db.Column(db.String(20),nullable=False,default='queued')
    name=db.Column(db.String(64))
    sha256=db.Column(db.String(64))
    error=db.Column(db.Text,nullable=False,default='')
    approved_by=db.Column(db.Integer)
    approved_at=db.Column(db.DateTime)
    created_at=db.Column(db.DateTime,nullable=False,default=utcnow)
    started_at=db.Column(db.DateTime)


def process_one():
    executable=shutil.which(os.getenv('DISSEMINATION_FFMPEG','ffmpeg'))
    if not executable:
        raise GenerationError('FFmpeg não está instalado no trabalhador audiovisual.')
    # Process one video per invocation, with one FFmpeg thread and a shared filesystem lock.
    import fcntl
    lock=(asset_root()/'video-worker.lock').open('a')
    try:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        for old in DisseminationVideo.query.filter(DisseminationVideo.state=='processing',DisseminationVideo.started_at<utcnow()-timedelta(minutes=30)):
            old.state='failed';old.error='Trabalhador interrompido. Solicite uma nova composição.'
        db.session.commit()
        video=DisseminationVideo.query.filter_by(state='queued').order_by(DisseminationVideo.id).first()
        if not video:
            return False
        claimed=db.session.execute(update(DisseminationVideo).where(DisseminationVideo.id==video.id,DisseminationVideo.state=='queued').values(state='processing',started_at=utcnow()))
        db.session.commit()
        if claimed.rowcount!=1:
            return False
        material=db.session.get(DisseminationMaterial,video.material_id)
        try:
            if shutil.disk_usage(asset_root()).free<512*1024*1024:
                raise GenerationError('Espaço livre insuficiente para compor o vídeo com segurança.')
            if material.version!=video.version:
                raise GenerationError('A versão de origem mudou.')
            row=current_version(material);export_allowed(material,row)
            slides=[a for a in row.assets if a.get('role')=='slide']
            if not 1<=len(slides)<=5:
                raise GenerationError('O vídeo exige entre um e cinco slides aprovados.')
            with tempfile.TemporaryDirectory(prefix='sds-video-') as temp:
                root=Path(temp);manifest=[]
                for index,asset in enumerate(slides):
                    (root/f'slide-{index}.png').write_bytes(read_asset(asset))
                    manifest.extend([f"file 'slide-{index}.png'",'duration 6'])
                manifest.append(f"file 'slide-{len(slides)-1}.png'")
                (root/'slides.txt').write_text('\n'.join(manifest)+'\n')
                name=secrets.token_hex(24)+'.mp4';target=asset_root()/name
                try:
                    subprocess.run([executable,'-nostdin','-hide_banner','-loglevel','error','-y',
                        '-f','concat','-safe','1','-i','slides.txt','-t',str(len(slides)*6),
                        '-filter_threads','1','-vf','fps=24,scale=720:720:force_original_aspect_ratio=decrease,pad=720:720:(ow-iw)/2:(oh-ih)/2:color=white',
                        '-r','24','-c:v','libx264','-threads','1','-preset','fast','-crf','23',
                        '-pix_fmt','yuv420p','-an','-movflags','+faststart',str(target)],
                        cwd=root,check=True,timeout=180,capture_output=True)
                    if target.stat().st_size>40*1024*1024:
                        raise GenerationError('O vídeo excede o limite de 40 MB.')
                    export_allowed(material,row)
                    target.chmod(0o600);video.name=name;video.sha256=hashlib.sha256(target.read_bytes()).hexdigest()
                    video.state='review';event(material,'video_generated','Vídeo silencioso aguarda revisão audiovisual.')
                except Exception:
                    target.unlink(missing_ok=True)
                    raise
        except Exception as exc:
            video.state='failed';video.error=str(exc) if isinstance(exc,GenerationError) else 'Falha na composição do vídeo. Não foi efectuada publicação.'
            event(material,'video_failed',video.error)
        db.session.commit();return True
    finally:
        lock.close()


def install(app,blueprint,access,can):
    from admin import validate_csrf
    @blueprint.post('/<int:ident>/video')
    @access
    def video_action(ident):
        validate_csrf();material=db.get_or_404(DisseminationMaterial,ident)
        try:
            export_allowed(material,current_version(material))
            if request.form.get('action')=='generate':
                if not can('manage'):
                    abort(403)
                if DisseminationVideo.query.filter(DisseminationVideo.material_id==ident,DisseminationVideo.version==material.version,
                    DisseminationVideo.state.in_(['queued','processing','review','approved'])).first():
                    raise GenerationError('Já existe um vídeo desta versão.')
                db.session.add(DisseminationVideo(material_id=ident,version=material.version));event(material,'video_queued')
            else:
                if not can('approve'):
                    abort(403)
                video=DisseminationVideo.query.filter_by(id=int(request.form.get('video_id',0)),material_id=ident,version=material.version,state='review').with_for_update().first()
                if not video or request.form.get('reviewed')!='yes':
                    raise GenerationError('Reveja o vídeo completo antes da aprovação audiovisual.')
                if not video.name or hashlib.sha256((asset_root()/video.name).read_bytes()).hexdigest()!=video.sha256:
                    raise GenerationError('O ficheiro de vídeo foi alterado ou está indisponível.')
                video.state='approved';video.approved_by=session.get('admin_id');video.approved_at=utcnow()
                event(material,'video_approved')
            db.session.commit()
        except (GenerationError,ValueError) as exc:
            db.session.rollback();abort(409,description=str(exc))
        return redirect('/admin/divulgacao/'+str(ident))

    @blueprint.get('/<int:ident>/video/<int:video_id>')
    @access
    def video_file(ident,video_id):
        material=db.get_or_404(DisseminationMaterial,ident)
        video=DisseminationVideo.query.filter_by(id=video_id,material_id=ident,version=material.version).first_or_404()
        try:
            export_allowed(material,current_version(material))
        except GenerationError as exc:
            abort(409,description=str(exc))
        download=request.args.get('download')=='1'
        if download and (not can('publish') or video.state!='approved'):
            abort(403)
        if video.state not in {'review','approved'} or not video.name or not (asset_root()/video.name).is_file():
            abort(404)
        if hashlib.sha256((asset_root()/video.name).read_bytes()).hexdigest()!=video.sha256:
            abort(409,description='O ficheiro de vídeo foi alterado.')
        return send_file(asset_root()/video.name,mimetype='video/mp4',as_attachment=download,download_name=f'divulgacao-{ident}.mp4',conditional=True)

    @app.cli.command('processar-videos-divulgacao')
    def worker():
        click.echo('1 vídeo processado.' if process_one() else 'Nenhum vídeo processado.')
