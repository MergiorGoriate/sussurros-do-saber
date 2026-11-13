# Article search

The header form, `/artigos` and `/api/artigos` use the same database-side
matching and relevance ordering. Category and ID filters still apply, and only
public articles are eligible. No schema migration or additional service is needed.

Search ignores case and Portuguese accents. Alphabetic words of 4–32 characters
allow one insertion, deletion, substitution or adjacent transposition per word:
`imunlogia` finds `imunologia`. All meaningful query words must be present, even
when separated, reversed or distributed across title, author and article content.
Portuguese and English stop words do not restrict multiword queries.

Exact phrases rank first, followed by weighted matches (especially titles and
authors). Nearby words in the requested order receive an additional bonus.
Publication date and article ID break ties. Ranking precedes pagination; there
is no arbitrary candidate limit. English searches also inspect individual fields
from the published translation version, never unpublished revision text.

DOI/ORCID and queries containing literal wildcard/quote/slash characters retain
literal substring matching. Short words and numbers are not typo-corrected.
Queries are limited to 120 characters. Queries with more than eight meaningful
words retain literal phrase search. This is lexical proximity, not semantic
synonym matching.

Run `python -m unittest discover -s tests -p 'test_smart_search.py' -v` and
`python -m unittest discover -s tests -p 'test_scientific_search.py' -v`.
Set `SMART_SEARCH_TEST_DATABASE_URL` to an isolated PostgreSQL database to run
the engine-specific matching checks. CI also runs route integration on PostgreSQL
18 and browser tests through the header form at 320px and 1440px.

Matching scans searchable fields, as the previous substring implementation did.
Measure latency against the production catalogue before considering a dedicated
search index for substantially larger collections.
