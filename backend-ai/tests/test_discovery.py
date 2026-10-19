import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import discovery
from joolan_client import ExportError


class DiscoveryTests(unittest.TestCase):
    def test_schema_uses_metadata_only_preserves_names_and_closes_client(self):
        client = Mock()
        client.query.return_value = [
            dict(TABLE_NAME='stock', COLUMN_NAME='qte', DATA_TYPE='decimal', COLUMN_KEY='', IS_NULLABLE='YES'),
            dict(TABLE_NAME='stock', COLUMN_NAME='sku', DATA_TYPE='varchar', COLUMN_KEY='PRI', IS_NULLABLE='NO')]
        with patch.object(discovery, 'Client', return_value=client):
            result = discovery.discover_schema('SECRET', 'daytona-account')
        self.assertEqual(result['tables'][0]['columns'][0]['name'], 'qte')
        self.assertEqual(result['tables'][0]['columns'][1]['key'], 'PRI')
        self.assertFalse(result['tables'][0]['columns'][1]['nullable'])
        query = client.query.call_args.args[0]
        self.assertIn('information_schema.COLUMNS', query)
        self.assertNotIn('SELECT *', query)
        self.assertNotIn('SECRET', str(result))
        client.close.assert_called_once()

    def test_inaccessible_metadata_is_actionable_and_errors_hide_key(self):
        client = Mock()
        client.query.return_value = []
        with patch.object(discovery, 'Client', return_value=client):
            with self.assertRaisesRegex(ValueError, 'dictionary'):
                discovery.discover_schema('SECRET', 'account')
            client.query.side_effect = ExportError('Rejected SECRET')
            with self.assertRaisesRegex(ValueError, r'Rejected \[hidden\]'):
                discovery.discover_schema('SECRET', 'account')
        self.assertEqual(client.close.call_count, 2)

    def test_history_dates_counts_and_file_change_invalidate_cache(self):
        import config
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'history.csv'
            path.write_text('Date_Commande,Reference\n2024-01-02,001\n03/02/2024,002\nbad,003\n', encoding='utf-8')
            with patch.object(config, 'DATA_FILE_PATH', str(path)):
                profile = discovery.historical_profile()
                self.assertEqual(profile['rows'], 3)
                self.assertEqual(profile['invalidDateRows'], 1)
                self.assertEqual(profile['lastOrderDate'], '2024-02-03')
                self.assertEqual(len(profile['months']), 2)
                profile['months'].clear()
                self.assertEqual(len(discovery.historical_profile()['months']), 2)
                path.write_text('Date_Commande,Reference\n2025-01-02,001\n', encoding='utf-8')
                self.assertEqual(discovery.historical_profile()['lastOrderDate'], '2025-01-02')

    def test_schema_api_requires_credentials_and_preserves_order_snapshot(self):
        import api_server
        from fastapi.testclient import TestClient
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'api.db'
            with patch.object(api_server, 'get_connection', lambda: sqlite3.connect(path)), TestClient(api_server.app) as client:
                with patch.object(discovery, 'discover_schema', return_value={'tables': []}) as inspect:
                    response = client.post('/api/joolan/schema', json={'apiKey': ' ', 'enseigne': 'account'})
                    self.assertEqual(response.status_code, 400)
                    inspect.assert_not_called()
                    response = client.post('/api/joolan/schema', json={'apiKey': 'SECRET', 'enseigne': 'account'})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(client.get('/api/joolan/summary').json()['totalRows'], 0)


if __name__ == '__main__':
    unittest.main()
