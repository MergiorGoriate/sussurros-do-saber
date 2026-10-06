import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.restore_drill import restore_archive


class RestoreSafetyTests(unittest.TestCase):
    def test_refuses_application_database_before_any_restore(self):
        with tempfile.NamedTemporaryFile() as archive:
            with patch("scripts.restore_drill.shutil.which", return_value="pg_restore"), patch("scripts.restore_drill.subprocess.run") as run, patch("scripts.restore_drill.psycopg.connect") as connect:
                with self.assertRaises(ValueError):
                    restore_archive(Path(archive.name), "postgresql://localhost/production")
                run.assert_not_called()
                connect.assert_not_called()

    def test_invalid_archive_does_not_create_database(self):
        with tempfile.NamedTemporaryFile() as archive:
            with patch("scripts.restore_drill.shutil.which", return_value="pg_restore"), patch("scripts.restore_drill.subprocess.run", side_effect=ValueError("invalid archive")), patch("scripts.restore_drill.psycopg.connect") as connect:
                with self.assertRaises(ValueError):
                    restore_archive(Path(archive.name), "postgresql://localhost/postgres")
                connect.assert_not_called()
