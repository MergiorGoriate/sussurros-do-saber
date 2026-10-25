"""Portable accent-insensitive public metadata searches."""
import unittest

from sqlalchemy import create_engine, literal, select
from sqlalchemy.dialects import postgresql

from scientific_search import metadata_match, search_term


class MetadataMatchTests(unittest.TestCase):
    def test_portuguese_accents_case_and_null_fields(self):
        engine = create_engine('sqlite://')
        cases = [
            ('investigacao', 'INVESTIGAÇÃO', True),
            ('INVESTIGAÇÃO', 'investigacao', True),
            ('ciencia', 'Ciência', True),
            ('saude', 'SAÚDE', True),
            ('orgaos', 'Órgãos', True),
            ('biologia', 'Ciência', False),
            ('%', 'Ciência', False),
            ('_', 'Ciência', False),
            ('100%', '100% ciência', True),
            ("' OR 1=1 --", 'Ciência', False),
        ]
        with engine.connect() as connection:
            for query, value, expected in cases:
                with self.subTest(query=query, value=value):
                    expression = metadata_match(query, literal(None), literal(value))
                    self.assertEqual(bool(connection.execute(select(expression)).scalar()), expected)
        engine.dispose()

    def test_identifiers_keep_existing_normalisation(self):
        self.assertEqual(search_term('HTTPS://DOI.ORG/10.1234/Test'), '10.1234/test')
        self.assertEqual(search_term('https://orcid.org/0000-0002-1825-0097'),
                         '0000-0002-1825-0097')
        self.assertEqual(len(search_term('a' * 200)), 120)

    def test_postgresql_uses_bound_parameters_and_portable_functions(self):
        statement = select(metadata_match("investigação%", literal('Investigação')))
        compiled = statement.compile(dialect=postgresql.dialect())
        self.assertIn('replace(', str(compiled))
        self.assertNotIn('investigação', str(compiled))
        self.assertIn('investigacao/%', compiled.params.values())


if __name__ == '__main__':
    unittest.main()
