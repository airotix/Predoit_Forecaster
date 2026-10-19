import sqlite3
import re
import unittest
from unittest.mock import patch

import joolan
from joolan_client import Client, ExportError, SourceChangedError, key_comparison


class LiveTableClient(Client):
    def __init__(self, mutation=None, primary=True):
        super().__init__('https://go.joolan.com', 'test', 'test-key')
        self.db = sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE orders(id INTEGER PRIMARY KEY, quantity INTEGER)')
        self.db.executemany('INSERT INTO orders VALUES(?,?)', [(1, 5), (2, 6), (3, 7)])
        self.calls = []
        self.mutation = mutation
        self.primary = primary
        self.pages = 0

    def query(self, sql):
        self.calls.append(sql)
        if 'information_schema' in sql:
            return [{'COLUMN_NAME': 'id'}] if self.primary else []
        if 'SELECT *' in sql and 'LIMIT 2' in sql:
            self.pages += 1
            if self.mutation and self.pages == 1:
                self.db.execute(self.mutation)
        cursor = self.db.execute(sql)
        return [dict(zip([column[0] for column in cursor.description], row)) for row in cursor]

    def close(self):
        self.db.close()


class LiveExportTests(unittest.TestCase):
    def test_projection_does_not_persist_unneeded_secret_fields(self):
        client=LiveTableClient()
        try:
            client.db.execute('ALTER TABLE orders ADD COLUMN MotPasse TEXT')
            client.db.execute("UPDATE orders SET MotPasse='fixture-secret'")
            meta=client.table_snapshot('orders',lambda m:None)
            meta['projection']=['id','quantity']
            result=list(client.table_rows('orders',2,lambda m:None,meta))
            self.assertEqual(len(result),3)
            self.assertTrue(all('MotPasse' not in r for r in result))
        finally:client.close()

    def test_document_filter_applies_to_probe_boundary_pages_and_counts(self):
        client = LiveTableClient()
        client.db.execute('ALTER TABLE orders ADD COLUMN Nature TEXT')
        client.db.execute("UPDATE orders SET Nature=CASE WHEN id=2 THEN 'FACTURE' ELSE 'COMMANDE' END")
        original = client.query
        def query(sql):
            # Translate MySQL's safe hex text literal for the SQLite fixture.
            translated = re.sub(r'CONVERT\(0x([0-9a-f]+) USING utf8mb4\)',
                                lambda m: "'" + bytes.fromhex(m[1]).decode().replace("'", "''") + "'", sql)
            return original(translated)
        client.query = query
        try:
            metadata = client.table_snapshot('orders', lambda message: None, 'COMMANDE')
            self.assertEqual(metadata['expected'], 2)
            self.assertEqual([r['id'] for r in client.table_rows('orders', 2, lambda message: None, metadata)], [1, 3])
            self.assertTrue(all('`Nature`' in sql for sql in client.calls if 'information_schema' not in sql))
        finally:
            client.close()

    def test_new_rows_above_start_boundary_wait_until_next_sync(self):
        client = LiveTableClient('INSERT INTO orders VALUES(4, 8)')
        try:
            metadata = client.table_snapshot('orders', lambda message: None)
            rows = list(client.table_rows('orders', 2, lambda message: None, metadata))
            self.assertEqual([r['id'] for r in rows], [1, 2, 3])
            self.assertEqual(metadata['exported'], 3)
            pages = [q for q in client.calls if ' WHERE ' in q and 'SELECT *' in q]
            self.assertTrue(all('OFFSET' not in q for q in pages))
            self.assertIn('`id` > 2', pages[-1])
            next_rows = list(client.table_rows('orders', 2, lambda message: None, {}))
            self.assertEqual([r['id'] for r in next_rows], [1, 2, 3, 4])
        finally:
            client.close()

    def test_deletion_inside_boundary_fails_instead_of_publishing_partial_data(self):
        client = LiveTableClient('DELETE FROM orders WHERE id=2')
        try:
            with self.assertRaises(SourceChangedError):
                list(client.table_rows('orders', 2, lambda message: None, {}))
        finally:
            client.close()

    def test_offset_fallback_still_rejects_growth(self):
        client = LiveTableClient('INSERT INTO orders VALUES(4, 8)', primary=False)
        try:
            with self.assertRaises(SourceChangedError):
                list(client.table_rows('orders', 2, lambda message: None, {}))
        finally:
            client.close()

    def test_composite_keys_do_not_interpolate_sql_from_string_values(self):
        predicate = key_comparison(['id', 'store'], [12, "A' OR 1=1 --"], '<=')
        self.assertIn('(`id`, `store`) <= (12, CONVERT(0x', predicate)
        self.assertNotIn('OR 1=1', predicate)

    def test_sync_retries_pair_and_does_not_yield_rows_from_failed_attempt(self):
        from unittest.mock import Mock
        import json
        from pathlib import Path
        client = Mock()
        client.cancelled.is_set.return_value = False
        client.table_snapshot.side_effect = lambda *args: {'expected': 1, 'where': '', 'paging': 'keyset'}
        def failed_page():
            yield {'version': 'partial-old'}
            raise SourceChangedError('changed')
        client.table_rows.side_effect = [failed_page(), iter([{'version': 'new'}]), iter([{'version': 'new'}])]
        client.count.return_value = 1
        def join(spools, scratch, *args):
            for path in spools.values():
                self.assertEqual(json.loads(path.read_text().strip()), {'version': 'new'})
            output = Path(scratch) / 'report.jsonl'
            output.write_text(json.dumps({'version': 'new'}) + '\n')
            return output, [], {}
        with patch.object(joolan, 'Client', return_value=client), patch.object(joolan, 'trade_document_spool', side_effect=join):
            self.assertEqual(list(joolan.fetch_trade_rows('SECRET')), [{'version': 'new'}])
        self.assertEqual(client.table_snapshot.call_count, 4)
        client.close.assert_called_once()

    def test_repeated_source_changes_stop_after_three_attempts(self):
        from unittest.mock import Mock
        client = Mock()
        client.table_snapshot.side_effect = SourceChangedError('changed SECRET')
        with patch.object(joolan, 'Client', return_value=client):
            with self.assertRaisesRegex(ValueError, 'three download attempts') as result:
                list(joolan.fetch_trade_rows('SECRET'))
        self.assertNotIn('SECRET', str(result.exception))
        self.assertEqual(client.table_snapshot.call_count, 3)
        client.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
