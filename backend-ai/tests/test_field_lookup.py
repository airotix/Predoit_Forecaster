import unittest

from joolan_client import field, _field_key


class FieldLookupTests(unittest.TestCase):
    def tearDown(self):
        _field_key.cache_clear()

    def test_shared_schema_reads_each_rows_values_including_zero_and_null(self):
        for value in (12, 0, None, ''):
            self.assertEqual(field({'PRODUIT': 'P', 'Quantite': value}, 'quantite'), value)
        self.assertIsNone(field({'PRODUIT': 'P'}, 'Quantite'))

    def test_duplicate_case_names_preserve_first_match_and_column_order(self):
        self.assertIsNone(field({'quantite': None, 'Quantite': 9}, 'Quantite'))
        self.assertEqual(field({'Quantite': 9, 'quantite': None}, 'Quantite'), 9)

    def test_schema_changes_do_not_reuse_an_invalid_column(self):
        self.assertEqual(field({'QUANTITE': 3}, 'Quantite'), 3)
        self.assertEqual(field({'quantite': 4}, 'Quantite'), 4)
        self.assertIsNone(field({'OTHER': 5}, 'Quantite'))
        self.assertEqual(field({'Straße': 6}, 'STRASSE'), 6)
