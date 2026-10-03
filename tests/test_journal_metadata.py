import unittest
from types import SimpleNamespace
from journal_metadata import journal_authors, normalize_orcid, validate_authors


class JournalMetadataTests(unittest.TestCase):
    def test_existing_author_lines_keep_names_and_safe_orcid_links(self):
        journal = SimpleNamespace(authors_data="", authors_orcid="Autora Antiga — https://orcid.org/0000-0002-1825-0097\nAutor Dois | 0000-0001-5109-3700\nNome sem ORCID\nhttps://orcid.org/0000-0002-1825-0097")
        rows = journal_authors(journal)
        self.assertEqual([row["name"] for row in rows], ["Autora Antiga", "Autor Dois", "Nome sem ORCID", ""])
        self.assertEqual(rows[0]["orcid"], "https://orcid.org/0000-0002-1825-0097")
        self.assertTrue(rows[3]["orcid"])
        self.assertFalse(rows[2]["orcid"])

    def test_only_orcid_and_only_name_are_supported(self):
        rows = validate_authors([{"name": "", "orcid": "0000-0002-1825-0097", "description": ""},
                                {"name": "Autora", "orcid": "", "description": "Biologia"}])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["name"], "")
        self.assertTrue(rows[0]["orcid"])
        self.assertEqual(rows[1]["description"], "Biologia")

    def test_unsafe_orcid_and_excessive_description_are_rejected(self):
        for value in ("javascript:alert(1)", "https://orcid.org.evil.test/0000-0002-1825-0097",
                      "https://evil.test/0000-0002-1825-0097", "https://orcid.org/invalid"):
            with self.assertRaises(ValueError):
                normalize_orcid(value)
        with self.assertRaises(ValueError):
            validate_authors([{"name": "Autora", "orcid": "", "description": "x" * 4001}])

    def test_invalid_saved_json_falls_back_to_existing_authors(self):
        journal = SimpleNamespace(authors_data="invalid", authors_orcid="Autora Antiga")
        self.assertEqual(journal_authors(journal)[0]["name"], "Autora Antiga")

    def test_existing_journal_schema_is_extended_without_losing_rows(self):
        from sqlalchemy import create_engine, inspect, text
        from unittest.mock import Mock, patch
        from app import ensure_journal_columns
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE journal (id INTEGER PRIMARY KEY, title VARCHAR(180))"))
            connection.execute(text("INSERT INTO journal (id, title) VALUES (1, 'Revista existente')"))
        with patch("app.db", SimpleNamespace(engine=engine, session=Mock())):
            ensure_journal_columns()
            ensure_journal_columns()
        self.assertTrue({"authors_data", "submission_history", "acknowledgements", "funding", "license_info"}.issubset(
            {column["name"] for column in inspect(engine).get_columns("journal")}))
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("SELECT title FROM journal WHERE id=1")).scalar(), "Revista existente")
        engine.dispose()
