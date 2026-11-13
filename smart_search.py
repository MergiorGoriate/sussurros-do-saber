"""Portable lexical search: bounded typo patterns and database-side ranking.

No external service, database extension or candidate cap is needed. All words
must match; exact identifiers remain literal. Ranking happens before pagination.
"""
from functools import lru_cache
import re
import sqlite3

from sqlalchemy import Boolean, and_, case, event, false, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement

from scientific_search import _FOLD, _searchable, metadata_match, search_term


_STOP_WORDS = frozenset('a o as os de da do das dos e em no na nos nas para por com '
                        'um uma uns umas the a an of and in on for to with'.split())
_WORD = r'[a-z0-9]'
_START, _END = r'(^|\W)', r'(\W|$)'


class _regex_match(FunctionElement):
    type = Boolean()
    inherit_cache = True


@compiles(_regex_match, 'sqlite')
def _sqlite_regex(element, compiler, **kwargs):
    return 'sds_search_regex(%s)' % compiler.process(element.clauses, **kwargs)


@compiles(_regex_match, 'postgresql')
def _postgresql_regex(element, compiler, **kwargs):
    column, pattern = element.clauses
    return 'COALESCE((%s ~ %s), false)' % (
        compiler.process(column, **kwargs), compiler.process(pattern, **kwargs))


@lru_cache(maxsize=256)
def _compiled_pattern(pattern):
    return re.compile(pattern)


@event.listens_for(Engine, 'connect')
def _register_regex(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        dbapi_connection.create_function('sds_search_regex', 2,
            lambda value, pattern: bool(value and _compiled_pattern(pattern).search(value)),
            deterministic=True)


def _words(term):
    # Punctuation in identifiers and SQL/LIKE metacharacters stays literal.
    if re.search(r"[%_'\"/\\]", term) or re.match(r'10\.\d{4,9}/', term):
        return ()
    if re.fullmatch(r'\d{4}-\d{4}-\d{4}-[\dx]+', term):
        return ()
    words = tuple(dict.fromkeys(word for word in re.findall(r'[^\W_]+', term)
                               if word not in _STOP_WORDS))
    # Long queries retain literal search instead of silently dropping words.
    return words if 0 < len(words) <= 8 else ()


def _exact_pattern(word):
    return _START + re.escape(word) + _END


@lru_cache(maxsize=256)
def _typo_pattern(word):
    """One insertion, omission, replacement or adjacent transposition per word.

    Short terms, numbers and very long words are not fuzzed. Alternatives use
    only escaped text and single-character classes, never user regex syntax.
    """
    exact = re.escape(word)
    if not (4 <= len(word) <= 32 and word.isascii() and word.isalpha()):
        return _exact_pattern(word)
    alternatives = {exact}
    for index in range(len(word)):
        left, right = re.escape(word[:index]), re.escape(word[index + 1:])
        alternatives.add(left + right)
        alternatives.add(left + _WORD + right)
        alternatives.add(left + _WORD + re.escape(word[index:]))
        if index + 1 < len(word):
            alternatives.add(left + re.escape(word[index + 1] + word[index])
                             + re.escape(word[index + 2:]))
    alternatives.add(exact + _WORD)
    return _START + '(' + '|'.join(sorted(alternatives)) + ')' + _END


def ranked_match(value, *fields):
    """Return a SQL predicate and relevance score for (column, weight) pairs."""
    term = search_term(value).translate(_FOLD)
    columns = [column for column, weight in fields]
    if not term or not columns:
        return false(), 0
    literal = metadata_match(term, *columns)
    score = case((literal, 10000), else_=0)
    for column, weight in fields:
        score += case((metadata_match(term, column), weight * 4), else_=0)
    words = _words(term)
    if not words:
        return literal, score
    matches = []
    for word in words:
        per_word = []
        for column, weight in fields:
            folded = _searchable(column)
            fuzzy = _regex_match(folded, _typo_pattern(word))
            exact = _regex_match(folded, _exact_pattern(word))
            per_word.append(fuzzy)
            score += case((exact, weight), (fuzzy, weight // 4), else_=0)
        matches.append(or_(*per_word))
    # Reward nearby words in the requested order, independently of recency.
    # Only the small title/metadata fields get proximity bonuses.
    if len(words) > 1:
        for gap, bonus in ((2, 3), (8, 1)):
            between = r'(\W+[a-z0-9]+){0,%d}\W+' % gap
            pattern = _START + between.join(re.escape(word) for word in words) + _END
            for column, weight in fields:
                if weight >= 400:
                    score += case((_regex_match(_searchable(column), pattern), weight * bonus), else_=0)
    return or_(literal, and_(*matches)), score


def article_search(value, *, english=False):
    """Search public article metadata, plus only its published EN version."""
    from models import Article, Author, Category
    fields = [(Article.title, 900), (Article.keywords, 400),
              (Author.name, 500), (Author.orcid, 900), (Article.doi, 900),
              (Category.name, 200), (Article.summary, 250), (Article.body, 40)]
    if english:
        from translation_models import ContentTranslation, TranslationVersion
        for key, weight in [('title', 900), ('keywords', 400), ('summary', 250), ('body', 40)]:
            translated = select(TranslationVersion.content[key].as_string()).join(
                ContentTranslation, and_(
                    ContentTranslation.id == TranslationVersion.translation_id,
                    ContentTranslation.published_version == TranslationVersion.number,
                )).where(
                    ContentTranslation.kind == 'article',
                    ContentTranslation.language == 'en',
                    ContentTranslation.source_id == Article.id,
                ).correlate(Article).scalar_subquery()
            fields.append((translated, weight))
    return ranked_match(value, *fields)
