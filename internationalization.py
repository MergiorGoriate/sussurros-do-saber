"""Explicit locale URLs and additive public presentation; never rewrite manuscripts."""
import hashlib
import os
from urllib.parse import urlsplit, urlencode
from flask import (Blueprint, abort, before_render_template, current_app, g, has_request_context,
                   redirect, render_template, request, url_for)
from sqlalchemy import select
from models import db, Article, utcnow
from translation_models import InterfaceTranslation, ContentTranslation, TranslationVersion
from translation_service import published as load_published, stale
from i18n_catalog import EN
from i18n_templates import PublicTranslationExtension, TEMPLATE_SOURCES as INTERFACE_SOURCES
from i18n_client import KEYS as CLIENT_KEYS

ENGLISH_TEXT = frozenset(' '.join(value.split()) for value in EN.values() if isinstance(value, str))

language_bp=Blueprint('language',__name__)
LUSOPHONE={'MZ','PT','BR','AO','CV','GW','ST','TL','GQ'}
ANGLOPHONE={'GB','US','AU','NZ','CA','IE','ZA','BW','ZM','ZW','MW','KE','UG','TZ','GH','NG','GM','SL','LR','NA','SS','JM','TT','BB','BS','BZ','GY'}


def published(kind, ident):
    """Reuse a published translation only within the current public request."""
    if not has_request_context():
        return load_published(kind, ident)
    cache = g.setdefault('localized_publications', {})
    key = (kind, ident)
    if key not in cache:
        cache[key] = load_published(kind, ident)
    return cache[key]


def listing_parameters():
    """Keep content selectors, dropping tracking and empty/default parameters."""
    if request.endpoint != 'articles':
        return {}
    from request_values import pagination_page
    values = {key: request.args.get(key, '').strip() for key in ('q', 'categoria')}
    values = {key: value for key, value in values.items() if value}
    page = pagination_page()
    if page > 1:
        values['page'] = page
    return values


def listing_noindex():
    return request.endpoint == 'articles' and (
        any(key in listing_parameters() for key in ('q', 'categoria'))
        or bool(request.args.get('original')))


def interface_ready():
    if os.getenv('I18N_ENABLED', 'true') != 'true':
        return False
    if not hasattr(g,'interface_complete'):
        catalogue = interface_catalogue()
        available = {key for key, value in EN.items() if value}
        available.update(key for key, value in catalogue.items() if value)
        g.interface_complete = all(
            text in available or ' '.join(text.split()) in available
            for text in INTERFACE_SOURCES)
    return g.interface_complete


def path_alternates(path):
    endpoint,args=current_app.url_map.bind_to_environ(request.environ).match(path,method='GET')
    return alternate_links(endpoint,**args)


def translated_match(kind,query,source_column):
    return db.exists(db.select(TranslationVersion.id).join(ContentTranslation,
        db.and_(ContentTranslation.id==TranslationVersion.translation_id,
                ContentTranslation.published_version==TranslationVersion.number)).where(
        ContentTranslation.kind==kind,ContentTranslation.source_id==source_column,
        db.cast(TranslationVersion.content,db.Text).ilike('%'+query+'%')))


def alternate_links(endpoint, **values):
    from html import escape
    if not interface_ready():
        return ''
    if endpoint in {'article','journal_detail'}:
        from models import Journal
        kind='article' if endpoint=='article' else 'journal'
        model=Article if kind=='article' else Journal
        obj=model.query.filter_by(slug=values.get('slug')).first()
        if not content_page_ready(kind, obj):
            return ''
    from app import SITE_URL
    return ''.join('<xhtml:link rel="alternate" hreflang="'+code+'" href="'+escape(SITE_URL+url_for(endpoint,_language=locale,**values),quote=True)+'"/>'
        for code,locale in [('pt-MZ',None),('en','en'),('x-default',None)])


def sitemap_extras(static_paths):
    if not interface_ready():
        return ''
    from html import escape
    from models import Journal
    from app import SITE_URL
    entries=[]
    adapter=current_app.url_map.bind_to_environ(request.environ)
    for path in static_paths:
        endpoint,args=adapter.match(path,method='GET')
        if endpoint in current_app.extensions['localized_endpoints']:
            en=url_for(endpoint,_language='en',**args)
            entries.append('<url><loc>'+escape(SITE_URL+en)+'</loc>'+alternate_links(endpoint,**args)+'</url>')
    for item in ContentTranslation.query.filter(ContentTranslation.published_version.isnot(None),ContentTranslation.language=='en',ContentTranslation.kind.in_(['article','journal'])):
        obj=db.session.get(Article if item.kind=='article' else Journal,item.source_id)
        if not content_page_ready(item.kind, obj):
            continue
        endpoint='article' if item.kind=='article' else 'journal_detail'
        entries.append('<url><loc>'+escape(SITE_URL+url_for(endpoint,slug=obj.slug,_language='en'))+'</loc>'+alternate_links(endpoint,slug=obj.slug)+'</url>')
    return ''.join(entries)


def language():
    if os.getenv('I18N_ENABLED','true')!='true':
        return 'pt'
    return getattr(g,'language','pt') if has_request_context() else 'pt'


def preferred(headers,cookies):
    choice=cookies.get('sds_language')
    if choice in {'pt','en'}:
        return choice
    country=headers.get('CF-IPCountry','').upper() if os.getenv('TRUST_CLOUDFLARE_COUNTRY')=='true' else ''
    if country in LUSOPHONE:
        return 'pt'
    if country in ANGLOPHONE:
        return 'en'
    from werkzeug.datastructures import LanguageAccept
    from werkzeug.http import parse_accept_header
    return parse_accept_header(headers.get('Accept-Language',''),LanguageAccept).best_match(['pt','en'],default='pt')


def interface_catalogue():
    if not hasattr(g, 'interface_catalogue'):
        g.interface_catalogue = {row.source: row.english for row in
            InterfaceTranslation.query.filter_by(published=True)}
        g.interface_english = frozenset(' '.join(value.split())
            for value in g.interface_catalogue.values() if value)
    return g.interface_catalogue


def interface_translation(text):
    """Look up approved interface copy without marking the current page."""
    if not text or not text.strip():
        return text
    catalogue = interface_catalogue()
    normalized = ' '.join(text.split())
    result = catalogue.get(text) or catalogue.get(normalized) or EN.get(text) or EN.get(normalized)
    if result:
        return result
    if normalized in ENGLISH_TEXT or normalized in g.interface_english:
        return text
    return None


def content_page_ready(kind, obj):
    """Advertise only public content with a published English version and labels."""
    if obj is None or (obj.status != 'published' if kind == 'article' else not obj.published):
        return False
    if not published(kind, obj.id)[1]:
        return False
    labels = (obj.category,) if kind == 'article' else (obj.field, obj.frequency)
    return all(interface_translation(value) is not None for value in labels if value)


def ui(text):
    if language()!='en' or not text or not text.strip():
        return text
    translated = interface_translation(text)
    if translated is not None:
        return translated
    g.i18n_missing = True
    return text


def equivalent(endpoint,args,target):
    values={k:v for k,v in args.items() if k!='_language'}
    if target=='en' and endpoint=='article' and values.get('slug'):
        obj=Article.public_query().filter_by(slug=values['slug']).first()
        if not obj or not published('article',obj.id)[1]:
            return url_for('articles',_language='en',original=values['slug'])
    return url_for(endpoint,_language='en' if target=='en' else None,**values)


def localized_path(path):
    if language()!='en' or not path.startswith('/') or path.startswith('//'):
        return path
    parts=urlsplit(path)
    try:
        endpoint,args=current_app.url_map.bind_to_environ(request.environ).match(parts.path,method='GET')
        if endpoint not in current_app.extensions.get('localized_endpoints',set()):
            return path
        return equivalent(endpoint,args,'en')+('?' + parts.query if parts.query else '')+('#'+parts.fragment if parts.fragment else '')
    except Exception:
        return path


class Presentation:
    """Read-only view of a model. It is never attached to the ORM or persisted."""
    def __init__(self,original,content,**extra):
        self._original=original;self._content=dict(content,**extra)
    def __getattr__(self,key):
        return self._content[key] if key in self._content else getattr(self._original,key)


def article_view(obj, *, check_staleness=True):
    if language()!='en' or isinstance(obj,Presentation):
        return obj
    item,row=published('article',obj.id)
    if not row:
        return Presentation(obj,{},category=ui(obj.category),translation_available=False)
    return Presentation(obj,row.content,category=ui(obj.category),translation_available=True,translation_outdated=stale(item,row) if check_staleness else False)


def journal_view(obj, *, check_staleness=True):
    if language()!='en' or isinstance(obj,Presentation):
        return obj
    item,row=published('journal',obj.id)
    labels={key:ui(getattr(obj,key,'')) for key in ('field','frequency')}
    if not row:
        return Presentation(obj,labels,translation_available=False)
    return Presentation(obj,row.content,**labels,translation_available=True,translation_outdated=stale(item,row) if check_staleness else False)


@language_bp.get('/idioma/<locale>')
def choose(locale):
    if locale not in {'pt','en'}:
        abort(404)
    path=request.args.get('next','/')
    parts=urlsplit(path)
    if parts.scheme or parts.netloc or not parts.path.startswith('/') or parts.path.startswith('//') or '\\' in path or len(path)>2000:
        abort(400)
    try:
        endpoint,args=current_app.url_map.bind_to_environ(request.environ).match(parts.path,method='GET')
        target=equivalent(endpoint,args,locale) if endpoint in current_app.extensions['localized_endpoints'] else ('/en/' if locale=='en' else '/')
        if parts.query and '?' not in target:
            target+='?'+parts.query
        if parts.fragment:
            target+='#'+parts.fragment
    except Exception:
        target='/en/' if locale=='en' else '/'
    response=redirect(target,code=302)
    response.set_cookie('sds_language',locale,max_age=31536000,secure=request.is_secure,httponly=True,samesite='Lax')
    response.headers['Cache-Control']='private, no-store'
    return response


def install(app):
    app.register_blueprint(language_bp)
    app.jinja_env.add_extension(PublicTranslationExtension)
    app.jinja_env.globals.update(ui=ui,localized_path=localized_path,site_language=language)
    excluded={'favicon','static','feed','sitemap','robots','healthcheck','journal_download_pdf','journal_preview_pdf','article_legacy'}
    allowed=set()
    for rule in list(app.url_map.iter_rules()):
        if (rule.endpoint in excluded or rule.rule.startswith(('/admin','/api','/static','/idioma','/divulgacao'))
            or any(rule.endpoint.startswith(p) for p in ('google.','premium_admin.','premium_finance.','dissemination.','translation_admin.'))
            or any(x in rule.rule for x in ('.pdf','ficheiros','figuras','webhook','callback','/sessao'))):
            continue
        allowed.add(rule.endpoint)
        app.add_url_rule('/<any(en):_language>'+rule.rule,endpoint=rule.endpoint,
            view_func=app.view_functions[rule.endpoint],methods=rule.methods,defaults=rule.defaults)
    app.extensions['localized_endpoints']=allowed

    @app.url_value_preprocessor
    def select_locale(endpoint,values):
        selected=values.pop('_language',None) if values else None
        g.language=selected or ('en' if request.path.startswith('/en/') else 'pt')
        g.localized_publications = {}
        for key in ('interface_complete', 'interface_catalogue', 'interface_english', 'i18n_missing'):
            g.pop(key, None)
        if selected is None and not request.path.startswith('/admin') and (request.path.startswith('/api/') or request.method!='GET') and request.cookies.get('sds_language')=='en':
            g.language='en'

    @app.url_defaults
    def localize_url(endpoint,values):
        if has_request_context() and language()=='en' and endpoint in allowed and '_language' not in values:
            if endpoint=='article' and values.get('slug'):
                obj=Article.public_query().filter_by(slug=values['slug']).first()
                if not obj or not published('article',obj.id)[1]:
                    return
            values['_language']='en'

    @app.before_request
    def initial_locale():
        if os.getenv('I18N_ENABLED','true')!='true':
            if request.path.startswith('/en/'):
                abort(404)
            return
        manual=request.args.get('lang')
        if manual in {'pt','en'} and request.method=='GET' and request.endpoint in allowed:
            args=request.args.to_dict(flat=False);args.pop('lang',None)
            path=request.path+('?' + urlencode(args,doseq=True) if args else '')
            return redirect(url_for('language.choose',locale=manual,next=path),302)
        # A manual choice also covers old/unprefixed internal links. Browser
        # negotiation remains limited to home; an explicit /en URL stays stable.
        agent=request.headers.get('User-Agent','').lower()
        if request.method in {'GET','HEAD'} and not any(x in agent for x in ('bot','crawler','spider')):
            chosen=request.cookies.get('sds_language')=='en'
            if (request.endpoint in allowed and not request.path.startswith('/en/') and
                (chosen or (request.path=='/' and preferred(request.headers,request.cookies)=='en'))):
                target=equivalent(request.endpoint,request.view_args or {},'en')
                if request.query_string:
                    target+=('&' if '?' in target else '?')+request.query_string.decode('utf-8','replace')
                response=redirect(target,302)
                response.headers['Cache-Control']='private, no-store'
                response.vary.add('Cookie')
                return response

    def presentation(sender,template,context,**extra):
        if language()!='en' or request.path.startswith('/admin'):
            return
        from models import Author
        def author_view(author):
            return Presentation(author,{field:ui(getattr(author,field,'')) for field in
                ('role','headline','academic_background','bio','interests','projects','editorial_experience')})
        if isinstance(context.get('author'),Author):
            context['author']=author_view(context['author'])
        if isinstance(context.get('authors'),list):
            context['authors']=[author_view(author) if isinstance(author,Author) else author for author in context['authors']]
        for key in ('intervals','kinds','resource_types','file_formats','states','file_kinds',
                    'required_declarations','optional_declarations','premium_request_kinds',
                    'premium_request_states','billing_states'):
            if isinstance(context.get(key),dict):
                context[key]={code:ui(label) if isinstance(label,str) else label for code,label in context[key].items()}
        if isinstance(context.get('errors'),list):
            context['errors']=[ui(error) if isinstance(error,str) else error for error in context['errors']]
        if 'steps' in context:
            context['steps']=tuple(ui(label) for label in context['steps'])
        for key in ('author_fields','info_fields','scientific_fields'):
            if isinstance(context.get(key),dict):
                context[key]={code:(ui(details[0]),*details[1:]) for code,details in context[key].items()}
        # Learning resources are first-party interface copy, not user manuscripts.
        for key in ('resources','all_resources'):
            if isinstance(context.get(key),list) and all(isinstance(x,dict) for x in context[key]):
                context[key]=[dict(obj,**{field:ui(obj[field]) for field in
                    ('title','description','type','topic','level') if isinstance(obj.get(field),str)}) for obj in context[key]]
        if 'article' in context and isinstance(context['article'],Article):
            context['article']=article_view(context['article'])
        if 'articles' in context:
            context['articles']=[article_view(x, check_staleness=False) for x in context['articles']]
        if 'related' in context:
            context['related']=[article_view(x, check_staleness=False) for x in context['related']]
        if 'journals' in context:
            context['journals']=[journal_view(x, check_staleness=False) for x in context['journals']]
        if context.get('journal'):
            context['journal']=journal_view(context['journal'])
            if isinstance(context['journal'],Presentation) and 'article_title' in context:
                context['article_title']=context['journal'].article_title or context['article_title']
        if (template.name or '').startswith('premium/'):
            from premium_models import PremiumContent, PremiumPlan
            def plan_view(plan):
                return Presentation(plan,dict(name=ui(plan.name),description=ui(plan.description),
                    benefits=[ui(value) if isinstance(value,str) else value for value in (plan.benefits or [])]))
            if 'plans' in context:
                context['plans']=[plan_view(plan) for plan in context['plans']]
            if isinstance(context.get('plan'),PremiumPlan):
                context['plan']=plan_view(context['plan'])
            if isinstance(context.get('terms'),dict):
                context['terms']={key:ui(value) if isinstance(value,str) else value for key,value in context['terms'].items()}
            if context.get('results') and hasattr(context['results'],'items'):
                result=context['results']
                context['results']=Presentation(result,{'items':[Presentation(obj,dict(title=ui(obj.title),summary=ui(obj.summary),category=ui(obj.category)))
                    if isinstance(obj,PremiumContent) else obj for obj in result.items]})
    before_render_template.connect(presentation,app,weak=False)

    @app.context_processor
    def language_context():
        endpoint=request.endpoint
        args=request.view_args or {}
        parameters=listing_parameters()
        canonical_path=request.path + ('?' + urlencode(parameters) if parameters else '')
        equivalents={}
        if endpoint in allowed and interface_ready():
            equivalents={locale:equivalent(endpoint,args,locale) for locale in ('pt','en')}
            if parameters:
                equivalents={locale:path+'?'+urlencode(parameters) for locale,path in equivalents.items()}
            if endpoint in {'article', 'journal_detail'}:
                from models import Journal
                kind = 'article' if endpoint == 'article' else 'journal'
                model = Article if kind == 'article' else Journal
                obj = model.query.filter_by(slug=args.get('slug')).first()
                if not content_page_ready(kind, obj):
                    equivalents.pop('en', None)
        original=None
        if request.endpoint=='articles' and language()=='en' and request.args.get('original'):
            original=Article.public_query().filter_by(slug=request.args['original'][:260]).first()
        return dict(seo_canonical_path=canonical_path,listing_noindex=listing_noindex(),language=language(),language_equivalents=equivalents,i18n_enabled=os.getenv('I18N_ENABLED','true')=='true',translation_original=original,
                    client_translations={text:ui(text) for text in CLIENT_KEYS} if language()=='en' else {})

    @app.after_request
    def locale_headers(response):
        if request.path.startswith('/admin'):
            return response
        response.headers['Content-Language']='en' if language()=='en' else 'pt-MZ'
        if request.endpoint in allowed:
            response.vary.add('Cookie')
        if request.path=='/' or request.path.startswith(('/en/','/idioma/')):
            response.headers['Cache-Control']='private, no-store'
        if language()=='en' and getattr(g,'i18n_missing',False):
            response.headers['X-Robots-Tag']='noindex, follow'
        if language()=='en' and request.path.startswith('/api/') and response.is_json:
            value=response.get_json(silent=True)
            if isinstance(value,dict):
                for key in ('message','error'):
                    if isinstance(value.get(key),str):
                        value[key]=ui(value[key])
                response.set_data(app.json.dumps(value))
        return response


