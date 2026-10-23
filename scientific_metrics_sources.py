"""Fixed-host DOI lookups; no keys or raw supplier payloads are exposed or persisted."""
import math
import os
import re
import time
from urllib.parse import quote, unquote
import requests

SOURCES = {'crossref':'Crossref', 'openalex':'OpenAlex', 'opencitations':'OpenCitations', 'altmetric':'Altmetric'}


def normalize_doi(value):
    value = re.sub(r'^(?:https?://(?:www\.)?(?:dx\.)?doi\.org/|doi\s*:\s*)', '', (value or '').strip(), flags=re.I)
    value = unquote(value).lower()
    return value if len(value)<=180 and re.fullmatch(r'10\.\d{4,9}/[^\s<>"?#]+',value) else ''


def number(value):
    # Do not coerce absent, negative, fractional, boolean or malformed values to zero.
    if isinstance(value, bool):return None
    if isinstance(value,int) and 0<=value<=2**53-1:return value
    if isinstance(value,str) and re.fullmatch(r'\d{1,15}',value):return int(value)
    return None


def lookup(source, doi):
    doi=normalize_doi(doi)
    if not doi:return {'state':'no_doi'}
    headers={'Accept':'application/json','User-Agent':'SussurrosScientificMetrics/1.0'}
    params={}
    if source=='crossref':
        url='https://api.crossref.org/works/'+quote(doi,safe='')
        if os.getenv('CROSSREF_MAILTO'):params['mailto']=os.environ['CROSSREF_MAILTO']
    elif source=='openalex':
        url='https://api.openalex.org/works/https://doi.org/'+quote(doi,safe='')
        if os.getenv('OPENALEX_API_KEY'):params['api_key']=os.environ['OPENALEX_API_KEY']
    elif source=='opencitations':
        url='https://api.opencitations.net/index/v2/citation-count/doi:'+quote(doi,safe='')
        if os.getenv('OPENCITATIONS_TOKEN'):headers['authorization']=os.environ['OPENCITATIONS_TOKEN']
    elif source=='altmetric':
        if (not os.getenv('ALTMETRIC_API_KEY') or os.getenv('ALTMETRIC_LICENSE_APPROVED')!='true'):
            return {'state':'requires_license'}
        # Vendor specifies an unencoded DOI path; requests handles safe URL escaping.
        url='https://api.altmetric.com/v1/doi/'+doi
        params['key']=os.environ['ALTMETRIC_API_KEY']
    else:raise ValueError('Unknown scientific source')
    try:
        response=requests.get(url,params=params,headers=headers,timeout=(5,15),allow_redirects=False,stream=True)
        try:
            if response.status_code==404:return {'state':'not_found'}
            if response.status_code==429:
                raw=response.headers.get('Retry-After','')
                retry=int(raw) if raw.isdigit() and len(raw)<10 else 86400
                return {'state':'rate_limited','retry_seconds':max(60,min(31536000,retry))}
            if response.status_code!=200:return {'state':'unavailable'}
            payload=bytearray();deadline=time.monotonic()+30
            for chunk in response.iter_content(8192):
                payload.extend(chunk)
                if len(payload)>1024*1024 or time.monotonic()>deadline:return {'state':'unavailable'}
            import json
            data=json.loads(payload)
        finally:response.close()
        result={'state':'ok','citations':None,'mentions':None,'attention_score':None}
        if source=='crossref':
            data=data['message']
            if normalize_doi(data.get('DOI'))!=doi:return {'state':'mismatch'}
            result['citations']=number(data.get('is-referenced-by-count'))
        elif source=='openalex':
            if normalize_doi(data.get('doi'))!=doi:return {'state':'mismatch'}
            result['citations']=number(data.get('cited_by_count'))
        elif source=='opencitations':
            if not isinstance(data,list) or len(data)!=1:return {'state':'not_found'}
            result['citations']=number(data[0].get('count'))
        else:
            if normalize_doi(data.get('doi'))!=doi:return {'state':'mismatch'}
            result['mentions']=number(data.get('cited_by_posts_count'))
            score=data.get('score')
            if not isinstance(score,bool) and isinstance(score,(int,float)) and math.isfinite(score) and 0<=score<=2**53-1:
                result['attention_score']=score
        if all(result[k] is None for k in ('citations','mentions','attention_score')):result['state']='unavailable'
        return result
    except (requests.RequestException,ValueError,KeyError,TypeError,AttributeError):
        return {'state':'unavailable'}


def bibliographic_candidates(journal):
    """Propose candidates only. An editor must verify the DOI in the existing editor."""
    from journal_metadata import journal_authors
    query=' '.join([journal.article_title or journal.title, ' '.join(a['name'] for a in journal_authors(journal)),
                    str(journal.publication_date.year) if journal.publication_date else ''])[:1000]
    try:
        with requests.get('https://api.crossref.org/works',params={'query.bibliographic':query,'rows':3},
                          headers={'Accept':'application/json','User-Agent':'SussurrosScientificMetrics/1.0'},
                          timeout=(5,15),allow_redirects=False,stream=True) as response:
            if response.status_code!=200:return []
            import json
            body=bytearray();deadline=time.monotonic()+30
            for chunk in response.iter_content(8192):
                body.extend(chunk)
                if len(body)>1024*1024 or time.monotonic()>deadline:return []
            items=json.loads(body)['message']['items']
        return [{'doi':normalize_doi(item.get('DOI')),'title':(item.get('title') or [''])[0],
                 'year':(item.get('published',{}).get('date-parts') or [[None]])[0][0],
                 'authors':[' '.join(str(a.get(k,'')) for k in ('given','family')) for a in item.get('author',[])[:30]]}
                for item in items[:3] if normalize_doi(item.get('DOI'))]
    except (requests.RequestException,ValueError,KeyError,TypeError,IndexError,AttributeError):return []
