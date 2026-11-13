"""Typo recall, precision, proximity and stable SQL pagination on both engines."""
import os
import unittest

from sqlalchemy import create_engine, literal, select, union_all
from sqlalchemy.dialects import postgresql

from smart_search import ranked_match, _typo_pattern


class SmartSearchTests(unittest.TestCase):
    database_url = 'sqlite://'

    def setUp(self):
        self.engine = create_engine(self.database_url)
        self.connection = self.engine.connect()

    def tearDown(self):
        self.connection.close()
        self.engine.dispose()

    def matches(self, query, *texts):
        match, score = ranked_match(query, *((literal(text), 900) for text in texts))
        return bool(self.connection.execute(select(match)).scalar())

    def test_typing_errors_and_accent_folding(self):
        for query, value in [
            ('biolgia', 'Biologia'), ('biolgoia', 'Biologia'),
            ('biollogia', 'Biologia'), ('biolofia', 'Biologia'),
            ('imunlogia', 'Imunologia'), ('neuroplaticidade', 'Neuroplasticidade'),
            ('cerebro', 'CÉREBRO'), ('saued', 'Saúde'),
        ]:
            with self.subTest(query=query):
                self.assertTrue(self.matches(query, value))

    def test_all_meaningful_words_can_be_separate_or_reversed(self):
        self.assertTrue(self.matches('cerebro e memoria', 'Memória e plasticidade do cérebro'))
        self.assertTrue(self.matches('cerebro memoria', 'Cérebro', 'A memória durante o sono'))
        self.assertTrue(self.matches('imunlogia cerebro', 'Imunologia e cérebro'))
        self.assertFalse(self.matches('cerebro memoria', 'Memória nas plantas'))
        self.assertFalse(self.matches('imunlogia cerebro', 'Imunologia dos insectos'))

    def test_short_terms_identifiers_and_metacharacters_are_not_fuzzed(self):
        for query, value in [
            ('rna', 'DNA'), ('12', '13'), ('biologia', 'Geologia'),
            ('10.12345/paper', '10.12345/papers'),
        ]:
            # Literal substring matches are preserved, including DOI prefixes.
            if query == '10.12345/paper':
                self.assertTrue(self.matches(query, value))
            else:
                self.assertFalse(self.matches(query, value))
        for query in ['%', '_', "' OR 1=1 --", '10.12345/paper2', '0000-0002-1825-0098']:
            self.assertFalse(self.matches(query, 'Ciência 10.12345/paper 0000-0002-1825-0097'))
        self.assertTrue(self.matches('100%', '100% ciência'))

    def test_irrelevant_long_words_are_not_matched_by_small_fragments(self):
        self.assertFalse(self.matches('antibiotico', 'antropologia e biologia'))
        self.assertFalse(self.matches('xyzabcde', 'Ciência e saúde'))
        self.assertFalse(self.matches('imunlogia', None, 'Ecologia'))

    def ranked_ids(self, query, rows, offset=0, limit=20):
        documents = union_all(*(select(literal(i).label('id'), literal(title).label('title'))
                                for i, title in rows)).subquery()
        match, score = ranked_match(query, (documents.c.title, 900))
        statement = select(documents.c.id).where(match).order_by(score.desc(), documents.c.id).offset(offset).limit(limit)
        return list(self.connection.execute(statement).scalars())

    def test_exact_and_close_titles_rank_above_typos_and_distant_words(self):
        rows = [(1, 'Memória do cérebro'), (2, 'Cérebro e memória'),
                (3, 'Cerebro memoria'), (4, 'Cérebro: estudo sobre sono, aprendizagem e memória'),
                (5, 'Cerebo e memória'), (6, 'Saúde das plantas')]
        ids = self.ranked_ids('cerebro memoria', rows)
        self.assertEqual(ids[0], 3)
        self.assertLess(ids.index(2), ids.index(4))
        self.assertLess(ids.index(2), ids.index(5))
        self.assertIn(1, ids)
        self.assertNotIn(6, ids)

    def test_database_paginates_after_ranking_without_candidate_cap(self):
        rows = [(i, 'Biolgia') for i in range(1, 41)] + [(100, 'Biologia')]
        self.assertEqual(self.ranked_ids('biologia', rows, limit=1), [100])
        first = self.ranked_ids('biologia', rows, limit=12)
        second = self.ranked_ids('biologia', rows, offset=12, limit=12)
        self.assertEqual(len(set(first + second)), 24)

    def test_parameters_are_bound_and_patterns_are_bounded(self):
        predicate, score = ranked_match('biolgia', (literal('Biologia'), 900))
        statement = select(score).where(predicate)
        compiled = statement.compile(dialect=postgresql.dialect())
        self.assertIn(' ~ ', str(compiled))
        self.assertNotIn('biolgia', str(compiled))
        self.assertNotIn('levenshtein', str(compiled))
        self.assertLess(len(_typo_pattern('a' * 32)), 6000)
        self.assertLess(len(_typo_pattern('a' * 120)), 150)


@unittest.skipUnless(os.getenv('SMART_SEARCH_TEST_DATABASE_URL'), 'Requires isolated PostgreSQL fixture')
class SmartSearchPostgresTests(SmartSearchTests):
    database_url = os.getenv('SMART_SEARCH_TEST_DATABASE_URL', 'sqlite://')


if __name__ == '__main__':
    unittest.main()
