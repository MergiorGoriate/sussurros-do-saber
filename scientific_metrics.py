"""Public scientific metrics and scoped editorial reports; no portal analytics."""
import csv
import io
import os
import time
from datetime import date, timedelta
from functools import wraps
import click
from flask import Blueprint, abort, current_app, render_template, request, Response, url_for
from sqlalchemy import select, update, delete
from sqlalchemy.orm import load_only
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.exc import IntegrityError
from admin import login_required, protect_admin_responses, csv_safe_cell
from extensions import limiter
from governance import has_any_permission, journal_scope
from journal_metadata import journal_authors
from models import db, Journal, utcnow
from scientific_metrics_collection import scientific
from scientific_metrics_models import ScientificMetricDay, ScientificMetricSource, ScientificMetricStart, ScientificMetricReceipt, ScientificMetricProvider
from scientific_metrics_sources import SOURCES, normalize_doi, lookup

metrics_bp=Blueprint('scientific_metrics',__name__)
STATES={'ok':'Disponível','unavailable':'Dados indisponíveis','not_found':'Sem registo na fonte','no_doi':'DOI válido não disponível',
        'mismatch':'Identificador não corresponde','rate_limited':'Limite da API atingido','requires_license':'Depende de licença/configuração','pending':'Por actualizar'}


def published_query():
    return Journal.query.options(load_only(Journal.id,Journal.title,Journal.article_title,Journal.doi,Journal.current_issue,Journal.publication_date,Journal.authors_data,Journal.authors_orcid)).filter(Journal.published.is_(True), Journal.content_markdown.isnot(None), db.func.trim(Journal.content_markdown)!='')


def allowed_admin():
    return has_any_permission('journal.manage') or has_any_permission('journal.publish') or has_any_permission('manuscript.production')


def metrics_admin(view):
    @wraps(view)
    @login_required
    def wrapped(*args,**kwargs):
        if not allowed_admin():abort(403)
        return view(*args,**kwargs)
    return wrapped


def filters():
    today=utcnow().date()
    raw=request.args.get('period','30')
    if raw not in {'7','30','90','365','custom'}:abort(400)
    try:
        if raw=='custom':
            end=date.fromisoformat(request.args.get('to',today.isoformat()))
            start=date.fromisoformat(request.args.get('from',(end-timedelta(days=29)).isoformat()))
        else:
            end=today;start=end-timedelta(days=int(raw)-1)
    except (ValueError,TypeError):abort(400)
    if start>end or (end-start).days>365 or end>today:abort(400)
    values={'start':start,'end':end,'period':raw,'year':request.args.get('year',''),
            'issue':request.args.get('issue','').strip(),'article':request.args.get('article',''),
            'author':request.args.get('author','').strip(),'journal':request.args.get('journal','').strip(),'source':request.args.get('source','crossref')}
    if len(values['journal'])>190 or len(values['issue'])>120 or len(values['author'])>180 or values['source'] not in SOURCES or values['source']=='altmetric':abort(400)
    for key in ('year','article'):
        value=values[key]
        if value and (not value.isascii() or not value.isdigit() or len(value)>10):abort(400)
    if values['year'] and not 1800<=int(values['year'])<=2200:abort(400)
    return values


def selected(items,options):
    result=[]
    for item in items:
        if options.get('journal') and item.title!=options['journal']:continue
        if options['issue'] and item.current_issue!=options['issue']:continue
        if options['article'] and item.id!=int(options['article']):continue
        if options['year'] and (not item.publication_date or item.publication_date.year!=int(options['year'])):continue
        if options['author'] and not any(options['author'].casefold() in ((a['name']+' '+a['orcid']).casefold()) for a in journal_authors(item)):continue
        result.append(item)
    return result


def source_values(items,public=False):
    ids=[j.id for j in items]
    rows=ScientificMetricSource.query.filter(ScientificMetricSource.journal_id.in_(ids)).all() if ids else []
    result={}
    dois={j.id:normalize_doi(j.doi) for j in items}
    for row in rows:
        if row.doi!=dois[row.journal_id]:continue
        if row.source=='altmetric' and (os.getenv('ALTMETRIC_LICENSE_APPROVED')!='true' or (public and os.getenv('ALTMETRIC_PUBLIC_DISPLAY_APPROVED')!='true')):continue
        result[(row.journal_id,row.source)]=row
    return result


def report(items,options,public=False):
    ids=[j.id for j in items];start=options['start'];end=options['end']
    days=ScientificMetricDay.query.filter(ScientificMetricDay.journal_id.in_(ids),ScientificMetricDay.day>=start,ScientificMetricDay.day<=end).all() if ids else []
    coverage={r.journal_id:r.started_at for r in ScientificMetricStart.query.filter(ScientificMetricStart.journal_id.in_(ids))} if ids else {}
    sources=source_values(items,public)
    per={j.id:{'item':j,'title':j.article_title or j.title,'views':0,'downloads':0,'coverage':coverage.get(j.id),'citations':None,'mentions':None,'score':None,'source_row':None} for j in items}
    totals_by_day={};countries={}
    for row in days:
        per[row.journal_id]['views']+=row.views;per[row.journal_id]['downloads']+=row.downloads
        bucket=totals_by_day.setdefault(row.day,{'views':0,'downloads':0});bucket['views']+=row.views;bucket['downloads']+=row.downloads
        countries[row.country]=countries.get(row.country,0)+row.views
    for ident,row in per.items():
        if not row['coverage'] or row['coverage'].date()>end:row['views']=row['downloads']=None
        source=sources.get((ident,options['source']));alt=sources.get((ident,'altmetric'))
        row['source_row']=source
        # Old successful results are retained for provenance, not silently counted as current.
        if source and source.state=='ok' and source.measured_at and source.measured_at>=utcnow()-timedelta(days=7):row['citations']=source.citations
        if alt and alt.state=='ok' and alt.measured_at and alt.measured_at>=utcnow()-timedelta(days=7):row['mentions'],row['score']=alt.mentions,alt.attention_score
    rows=list(per.values())
    def known_sum(key):
        values=[r[key] for r in rows if r[key] is not None]
        return sum(values) if values else None
    # Never sum counts from different citation databases or duplicate the same DOI.
    seen_c=set();seen_m=set();citation_values=[];mention_values=[]
    for row in rows:
        doi=normalize_doi(row['item'].doi)
        if row['citations'] is not None and doi not in seen_c:seen_c.add(doi);citation_values.append(row['citations'])
        if row['mentions'] is not None and doi not in seen_m:seen_m.add(doi);mention_values.append(row['mentions'])
    earliest=min((v.date() for v in coverage.values()),default=None)
    series=[]
    for offset in range((end-start).days+1):
        day=start+timedelta(days=offset);bucket=totals_by_day.get(day,{'views':0,'downloads':0})
        series.append({'day':day.isoformat(),'views':bucket['views'] if earliest and day>=earliest else None,'downloads':bucket['downloads'] if earliest and day>=earliest else None})
    geography=[{'country':c,'views':n} for c,n in countries.items() if c!='ZZ' and n>=5]
    geography.sort(key=lambda r:r['views'],reverse=True)
    return dict(rows=rows,total=len(rows),views=known_sum('views'),downloads=known_sum('downloads'),
                citations=sum(citation_values) if citation_values else None,mentions=sum(mention_values) if mention_values else None,
                citation_coverage=len(citation_values),mention_coverage=len(mention_values),series=series,geography=geography,
                fresh_after=utcnow()-timedelta(days=7),coverage_start=earliest,views_known=sum(r['views'] is not None for r in rows),sources=sources,
                top_views=sorted([r for r in rows if r['views'] is not None],key=lambda r:r['views'],reverse=True)[:5],
                top_downloads=sorted([r for r in rows if r['downloads'] is not None],key=lambda r:r['downloads'],reverse=True)[:5],
                top_citations=sorted([r for r in rows if r['citations'] is not None],key=lambda r:r['citations'],reverse=True)[:5])


def article_metrics(journal):
    options={'start':utcnow().date()-timedelta(days=29),'end':utcnow().date(),'source':'crossref'}
    try:return report([journal],options,public=True),options
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning('Scientific metrics unavailable; scientific content remains public.')
        return None,options


@metrics_bp.after_request
def private_metrics(response):
    response.headers['Cache-Control']='private, no-store'
    if request.path.startswith('/admin/'):return protect_admin_responses(response)
    return response


@metrics_bp.get('/admin/revistas/metricas')
@metrics_admin
@limiter.limit('60 per minute')
def dashboard():
    options=filters();available=journal_scope(published_query()).order_by(Journal.id).all()
    items=selected(available,options)
    data=report(items,options)
    from request_values import pagination_page
    page=pagination_page()
    export_args={key:options[key] for key in ('period','year','issue','article','author','source','journal')}
    export_args.update({'from':options['start'],'to':options['end']})
    return render_template('admin/scientific_metrics.html',table_rows=data['rows'][(page-1)*50:page*50],page=page,pages=max(1,(len(data['rows'])+49)//50),export_args=export_args,export_url=url_for('scientific_metrics.export',**export_args),data=data,options=options,available=available,
                           issues=sorted({j.current_issue for j in available if j.current_issue}),sources=SOURCES,states=STATES)


@metrics_bp.get('/admin/revistas/metricas/exportar.csv')
@metrics_admin
@limiter.limit('10 per minute')
def export():
    options=filters();items=selected(journal_scope(published_query()).order_by(Journal.id).all(),options)
    data=report(items,options);output=io.StringIO();writer=csv.writer(output)
    writer.writerow(['artigo_id','titulo','edicao','doi','inicio_periodo_UTC','fim_periodo_UTC','recolha_desde_UTC','visualizacoes','downloads_PDF',
                     'fonte_citacoes','citacoes_actualmente_disponiveis','estado_fonte','ultima_consulta_UTC','ultima_medicao_UTC','mencoes_Altmetric','pontuacao_Altmetric_nao_arredondada'])
    for row in data['rows']:
        j=row['item'];src=row['source_row']
        writer.writerow([csv_safe_cell(str(v)) if v is not None else 'Dados indisponíveis' for v in [j.id,row['title'],j.current_issue,j.doi,
            options['start'],options['end'],row['coverage'],row['views'],row['downloads'],SOURCES[options['source']],row['citations'],
            STATES.get(src.state,'Dados indisponíveis') if src else 'Por actualizar',src.checked_at if src else None,src.measured_at if src else None,
            row['mentions'] if os.getenv('ALTMETRIC_EXPORT_APPROVED')=='true' else 'Exportação Altmetric não autorizada',
            row['score'] if os.getenv('ALTMETRIC_EXPORT_APPROVED')=='true' else 'Exportação Altmetric não autorizada']])
    return Response('\ufeff'+output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=metricas-cientificas.csv'})


@metrics_bp.get('/revistas/<slug>/metricas')
@limiter.limit('60 per minute')
def public_article(slug):
    journal=published_query().filter_by(slug=slug).first_or_404();options=filters()
    options['article']=str(journal.id);options['issue']=options['year']=options['author']=''
    return render_template('scientific_metrics.html',journal=journal,data=report([journal],options,True),options=options,sources=SOURCES,states=STATES)


@metrics_bp.get('/metricas-cientificas')
@limiter.limit('60 per minute')
def public_summary():
    options=filters();available=published_query().order_by(Journal.id).all();items=selected(available,options)
    return render_template('scientific_metrics.html',journal=None,data=report(items,options,True),options=options,
        available=available,issues=sorted({j.current_issue for j in available if j.current_issue}),sources=SOURCES,states=STATES)


def register_cli(app):
    @app.cli.command('metricas-cientificas-corresponder')
    @click.option('--artigo',required=True,type=int)
    def candidates(artigo):
        """Return bibliographic candidates without changing DOI or citation counts."""
        import json
        from scientific_metrics_sources import bibliographic_candidates
        journal=published_query().filter_by(id=artigo).first()
        if not journal:raise click.ClickException('Artigo científico publicado não encontrado.')
        click.echo('Candidatos apenas: confirme título, autores, ano e versão no editor existente.')
        click.echo(json.dumps(bibliographic_candidates(journal),ensure_ascii=False))

    @app.cli.command('metricas-cientificas-actualizar')
    @click.option('--source',type=click.Choice(list(SOURCES)),multiple=True)
    @click.option('--limit',default=50,type=click.IntRange(1,500))
    def refresh(source,limit):
        """Refresh DOI snapshots off-request, at most once/day per article and supplier."""
        sources=source or ('crossref','openalex','opencitations')
        items=published_query().order_by(Journal.id).all()
        for provider in sources:
            now=utcnow()
            gate=db.session.get(ScientificMetricProvider,provider)
            if gate is None:
                gate=ScientificMetricProvider(source=provider,next_attempt=now)
                db.session.add(gate)
                try:db.session.commit()
                except IntegrityError:db.session.rollback();continue
            lease=db.session.execute(update(ScientificMetricProvider).where(ScientificMetricProvider.source==provider,
                ScientificMetricProvider.next_attempt<=now).values(next_attempt=now+timedelta(seconds=limit*60+300)).returning(ScientificMetricProvider.source)).scalar_one_or_none()
            db.session.commit()
            if lease is None:
                click.echo(f'{provider}: aguarda disponibilidade/limite do fornecedor');continue
            done=0
            backoff=60
            for j in items:
                doi=normalize_doi(j.doi)
                if not doi:continue
                now=utcnow();row=ScientificMetricSource.query.filter_by(journal_id=j.id,source=provider).first()
                if row is None:
                    row=ScientificMetricSource(journal_id=j.id,source=provider,doi=doi)
                    db.session.add(row)
                    try:db.session.commit()
                    except IntegrityError:db.session.rollback();continue
                if row.doi!=doi:
                    row.doi=doi;row.citations=row.mentions=row.attention_score=None;row.measured_at=None;row.next_attempt=None;db.session.commit()
                # An atomic lease also prevents two schedulers refreshing the same item.
                leased=db.session.execute(update(ScientificMetricSource).where(ScientificMetricSource.id==row.id,
                    db.or_(ScientificMetricSource.next_attempt.is_(None),ScientificMetricSource.next_attempt<=now))
                    .values(next_attempt=now+timedelta(days=1)).returning(ScientificMetricSource.id)).scalar_one_or_none()
                db.session.commit()
                if leased is None:continue
                outcome=lookup(provider,doi)
                row.state=outcome['state'];row.checked_at=now
                if row.state=='ok':
                    row.citations=outcome['citations'];row.mentions=outcome['mentions'];row.attention_score=outcome['attention_score'];row.measured_at=now
                db.session.commit();done+=1
                click.echo(f'{provider}: artigo {j.id}: {row.state}')
                if row.state=='rate_limited':backoff=outcome.get('retry_seconds',86400);break
                if done>=limit:break
                time.sleep(1)
            db.session.execute(update(ScientificMetricProvider).where(ScientificMetricProvider.source==provider).values(next_attempt=utcnow()+timedelta(seconds=backoff)));db.session.commit()
        db.session.execute(delete(ScientificMetricReceipt).where(ScientificMetricReceipt.day<utcnow().date()-timedelta(days=2)));db.session.commit()


@metrics_bp.errorhandler(SQLAlchemyError)
def unavailable(error):
    db.session.rollback()
    return render_template('metrics/unavailable.html'),503


def catalogue_metrics():
    options={'start':utcnow().date()-timedelta(days=29),'end':utcnow().date(),'source':'crossref',
             'issue':request.args.get('edicao',''),'year':'','article':'','author':'','journal':''}
    if len(options['issue'])>120:abort(400)
    try:
        available=published_query().all()
        return report(selected(available,options),options,True), sorted({j.current_issue for j in available if j.current_issue})
    except SQLAlchemyError:
        db.session.rollback()
        return None,[]
