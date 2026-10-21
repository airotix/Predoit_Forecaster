"""Phase 0 behaviour lock: default data locations must not drift.

The earlier package split silently changed the default serving database from
data/joolan_live.db to data/forecast.db and moved the credentials .env, so the app
read the wrong files. These tests pin every default and the override rules. Each case
runs in a fresh interpreter with a scrubbed environment so import-time resolution is
what is actually tested.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

PROBE = """
import json
import database, history_store, fresh_joolan, server_credentials, api_server
print(json.dumps({
    'db': str(database.DB_FILE),
    'history': str(history_store.DEFAULT_PATH),
    'source': str(fresh_joolan.SOURCE_DB),
    'env_file': str(server_credentials.ENV_FILE),
    'output': str(api_server.OUTPUT_PATH),
}))
"""


def probe(**extra_env):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('FORECASTER_', 'JOOLAN_'))}
    env.update(extra_env)
    result = subprocess.run([sys.executable, '-B', '-c', PROBE], cwd=BACKEND, env=env,
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise AssertionError(result.stderr[-2000:])
    return json.loads(result.stdout.strip().splitlines()[-1])


class DefaultLocationTests(unittest.TestCase):
    def test_default_serving_database_is_joolan_live(self):
        self.assertEqual(str(BACKEND / 'data' / 'joolan_live.db'), probe()['db'])

    def test_other_default_locations(self):
        paths = probe()
        self.assertEqual(str(BACKEND / 'data' / 'history.db'), paths['history'])
        self.assertEqual(str(BACKEND / 'data' / 'joolan_source.db'), paths['source'])
        self.assertEqual(str(BACKEND / '.env'), paths['env_file'])
        self.assertEqual(str(BACKEND / 'output'), paths['output'])

    def test_database_path_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'custom.db'
            self.assertEqual(str(target.resolve()), probe(FORECASTER_DB_PATH=str(target))['db'])

    def test_unrelated_forecaster_variables_do_not_move_data(self):
        """A stray FORECASTER_* setting must not relocate the default databases."""
        paths = probe(FORECASTER_OUTPUT_DIR='elsewhere/', FORECASTER_API_PORT='4999')
        self.assertEqual(str(BACKEND / 'data' / 'joolan_live.db'), paths['db'])
        self.assertEqual(str(BACKEND / 'data' / 'history.db'), paths['history'])


if __name__ == '__main__':
    unittest.main()
