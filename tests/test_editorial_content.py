import unittest
from editorial_content import prepare_guidelines


class EditorialContentTests(unittest.TestCase):
    def test_custom_headings_receive_unique_ids_and_types_target(self):
        html, target = prepare_guidelines("<h2>Introdução</h2><h2>Introdução</h2><h2>Tipos de manuscritos</h2>")
        self.assertEqual(target, "tipos")
        self.assertIn('id="introducao"', html)
        self.assertIn('id="introducao-2"', html)
        self.assertIn('id="tipos"', html)
