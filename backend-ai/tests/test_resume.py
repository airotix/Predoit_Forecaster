import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from joolan_client import Client, RateLimitError, SourceChangedError
from joolan_download import download_pair, reset_download


class PagedClient(Client):
    def __init__(self, fail=False):
        super().__init__('https://go.joolan.com', 'account', 'SECRET')
        self.fail = fail
        self.pages = []
        self.rows = {table: [dict(id=i, value=str(i)) for i in range(1, 6)]
                     for table in ('negoce_entetes', 'negoce_lignes')}

    def table_snapshot(self, table, log):
        return dict(expected=5, columns=['id', 'value'], order=['id'], primary=['id'],
                    upper=[5], where='id <= 5', paging='keyset')

    def count(self, table, where=''):
        return len(self.rows[table])

    def query(self, sql):
        table = next(t for t in self.rows if '`' + t + '`' in sql)
        cursor = re.search(r'`id` > (\d+)', sql)
        start = int(cursor[1]) if cursor else 0
        self.pages.append((table, start))
        if self.fail and table == 'negoce_lignes' and start == 2:
            raise RateLimitError('quota reached')
        limit = int(re.search(r'LIMIT (\d+)', sql)[1])
        return [row for row in self.rows[table] if row['id'] > start][:limit]


class ResumeTests(unittest.TestCase):
    def test_quota_resume_keeps_pages_and_does_not_repeat_completed_header_queries(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = PagedClient(fail=True)
            with self.assertRaises(RateLimitError):
                download_pair(first, tmp, 2)
            state_path = Path(tmp) / 'checkpoint.json'
            self.assertNotIn('SECRET', state_path.read_text())
            # Simulate uncommitted bytes from a crash after a completed page.
            line_path = Path(tmp) / 'negoce_lignes.jsonl'
            with line_path.open('ab') as stream:
                stream.write(b'partial garbage')
            second = PagedClient()
            spools = download_pair(second, tmp, 2)
            self.assertEqual(second.pages, [('negoce_lignes', 2), ('negoce_lignes', 4)])
            for path in spools.values():
                self.assertEqual([json.loads(line)['id'] for line in path.read_text().splitlines()], [1, 2, 3, 4, 5])
            reset_download(tmp)
            self.assertFalse(state_path.exists())

    def test_changed_bounded_population_invalidates_saved_cursor(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RateLimitError):
                download_pair(PagedClient(fail=True), tmp, 2)
            second = PagedClient()
            second.rows['negoce_entetes'].pop()
            with self.assertRaises(SourceChangedError):
                download_pair(second, tmp, 2)
            self.assertFalse((Path(tmp) / 'checkpoint.json').exists())

    def test_hourly_limit_response_is_actionable_and_does_not_echo_sql_or_key(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps({'result': 'error', 'error_message': 'usage exceeds hourly limit: SELECT SECRET'}).encode()
        opener = Mock()
        opener.open.return_value = response
        with patch('urllib.request.build_opener', return_value=opener):
            with self.assertRaises(RateLimitError) as error:
                Client('https://go.joolan.com', 'account', 'SECRET').query('SELECT 1')
        self.assertNotIn('SECRET', str(error.exception))
        self.assertNotIn('SELECT', str(error.exception))
        self.assertIn('reset', str(error.exception))
        opener.open.assert_called_once()

    def test_metadata_quota_is_not_swallowed_as_missing_primary_key(self):
        client = PagedClient()
        # Exercise the real metadata discovery method with mocked requests.
        client.query = Mock(side_effect=[[{'id': 1}], RateLimitError('hourly limit')])
        with self.assertRaises(RateLimitError):
            Client.table_snapshot(client, 'negoce_entetes', lambda message: None)
        self.assertEqual(client.query.call_count, 2)

    def test_successful_persistent_sync_can_run_again_with_fresh_join_database(self):
        import joolan
        import sqlite3
        from contextlib import closing
        def join(spools, scratch, *args):
            with closing(sqlite3.connect(Path(scratch) / 'join.sqlite')) as conn:
                conn.execute('CREATE TABLE joined(id INTEGER)')
            report = Path(scratch) / 'report.jsonl'
            report.write_text(json.dumps({'Order_Number': '001'}) + '\n')
            return report, [], {}
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(joolan, 'Client', side_effect=lambda *args: PagedClient()), patch.object(joolan, 'trade_document_spool', side_effect=join):
                for _ in range(2):
                    self.assertEqual(list(joolan.fetch_trade_rows('SECRET', checkpoint_dir=tmp)), [{'Order_Number': '001'}])
            self.assertFalse(list(Path(tmp).rglob('checkpoint.json')))
            self.assertFalse(list(Path(tmp).rglob('join.sqlite')))


if __name__ == '__main__':
    unittest.main()
