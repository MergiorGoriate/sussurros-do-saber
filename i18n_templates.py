"""Jinja source preprocessing, never HTML response rewriting or business-logic translation."""
import html
import json
import re
from jinja2.ext import Extension
from i18n_client import KEYS
from i18n_catalog import EN

PARTS = re.compile(r'(<!--[\s\S]*?-->|<script\b[\s\S]*?</script\s*>|<style\b[\s\S]*?</style\s*>|{%[\s\S]*?%}|{{[\s\S]*?}}|<[^>]+>)',re.I)
SOURCES = set(KEYS)
# Only template/client labels gate shared public discovery. The admin collector
# also adds dynamic profiles, courses and editorial text to SOURCES.
TEMPLATE_SOURCES = set(KEYS)


def record_source(value):
    SOURCES.add(value)
    TEMPLATE_SOURCES.add(value)


def ui_literal(value):
    return value in EN or bool(re.match(r'^[A-ZÀ-Ý]',value) and re.search(r'[À-ÿ\s]',value) and not any(x in value for x in ('/','<','>','_','{{')))


def translated_expression(chunk):
    if not chunk.startswith('{{'):
        return chunk
    inner=chunk[2:-2]
    if inner.strip() in {'label','message','error'}:
        return '{{ ui('+inner.strip()+') }}'
    def replace(match):
        prefix,quote,value=match.groups()
        if not ui_literal(value):
            return match.group()
        clean=value.strip();record_source(clean)
        leading=value[:len(value)-len(value.lstrip())];trailing=value[len(value.rstrip()):]
        translated='ui('+json.dumps(clean,ensure_ascii=False)+')'
        if leading or trailing:
            translated='('+json.dumps(leading)+' ~ '+translated+' ~ '+json.dumps(trailing)+')'
        return prefix+translated
    inner=re.sub(r'(^\s*|\belse\s+)([\'\"])([^\'\"]*)\2',replace,inner)
    return '{{'+inner+'}}'


def expression(text):
    clean=html.unescape(text.strip())
    if not clean or not re.search(r'[A-Za-zÀ-ÿ]',clean):
        return text
    record_source(clean)
    lead=text[:len(text)-len(text.lstrip())];tail=text[len(text.rstrip()):]
    return lead+'{{ ui('+json.dumps(clean,ensure_ascii=False)+') }}'+tail


class PublicTranslationExtension(Extension):
    def preprocess(self,source,name,filename=None):
        if not name or name.startswith(('admin/','emails/','i18n/')):
            return source
        output=[]
        for chunk in PARTS.split(source):
            if not chunk:
                continue
            if chunk.startswith('{%'):
                for _,value in re.findall(r'([\'\"])([^\'\"]+)\1',chunk):
                    if ui_literal(value):
                        record_source(value)
                output.append(chunk);continue
            if chunk.startswith('{{'):
                output.append(translated_expression(chunk));continue
            if chunk.startswith('<!--') or re.match(r'<(?:script|style)\b',chunk,re.I):
                output.append(chunk);continue
            if chunk.startswith('<'):
                def attribute(match):
                    key,quote,value=match.groups()
                    if '{{' in value or '{%' in value:
                        parts=re.split(r'({{[\s\S]*?}}|{%[\s\S]*?%})',value)
                        value=''.join(translated_expression(part) if part.startswith('{{') else part if part.startswith('{%') else expression(part) for part in parts)
                        return key+'='+quote+value+quote
                    return key+'='+quote+expression(value)+quote
                chunk=re.sub(r'\b(alt|title|placeholder|aria-label)=("|\')([^\n]*?)\2',attribute,chunk)
                def link(match):
                    key,quote,path=match.groups()
                    if path.startswith(('/admin','/api','/static','//')) or '{{' in path:
                        return match.group()
                    return key+'='+quote+'{{ localized_path('+json.dumps(path)+') }}'+quote
                chunk=re.sub(r'\b(href|action)=("|\')(/[^"\']*)\2',link,chunk)
                output.append(chunk)
            else:
                output.append(expression(chunk))
        return ''.join(output)


