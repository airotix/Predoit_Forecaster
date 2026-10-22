"""Phase 2: file locations are explicit, and moving the code does not move the data.

Covers the single path anchor (paths.py), the FORECASTER_HOME override, worker processes that
start by module name, and code hashes that do not depend on where the source files sit.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import automatic_forecast
import code_fingerprint
import fresh_routes
import main
import paths

BACKEND = Path(__file__).resolve().parents[1]
LEGACY_SCRIPTS = ('check_', 'verify_', 'build_', 'audit_', 'benchmark_', 'repair_', 'test_db')

PROBE = """
import json
import database, history_store, fresh_joolan, server_credentials, api_server, ingestion, config, paths, main
print(json.dumps({
    'code': str(paths.CODE_DIR), 'home': str(paths.HOME),
    'db': str(database.DB_FILE), 'history': str(history_store.DEFAULT_PATH),
    'source': str(fresh_joolan.SOURCE_DB), 'env_file': str(server_credentials.ENV_FILE),
    'output': str(api_server.OUTPUT_PATH), 'append': str(ingestion._ingest_append_path()),
    'data_file': config.DATA_FILE_PATH, 'main_base': str(main.BASE_DIR),
}))
"""


def scrubbed_env(**extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('FORECASTER_', 'JOOLAN_'))}
    env.update(extra)
    return env


def copy_code(destination):
    for file in BACKEND.glob('*.py'):
        shutil.copy2(file, destination)


class AnchorTests(unittest.TestCase):
    def test_only_paths_module_looks_at_file_location(self):
        offenders = []
        for file in sorted(BACKEND.glob('*.py')):
            if file.name == 'paths.py' or file.name.startswith(LEGACY_SCRIPTS):
                continue
            if re.search(r'__file__', file.read_text(encoding='utf-8')):
                offenders.append(file.name)
        self.assertEqual([], offenders, 'use the paths module instead of __file__')

    def test_defaults_are_unchanged(self):
        self.assertEqual(BACKEND, paths.CODE_DIR)
        self.assertEqual(BACKEND, paths.HOME)
        self.assertEqual(BACKEND / 'data' / 'joolan_live.db', paths.LIVE_DB)
        self.assertEqual(BACKEND / 'data' / 'joolan_source.db', paths.SOURCE_DB)
        self.assertEqual(BACKEND / 'data' / 'history.db', paths.HISTORY_DB)
        self.assertEqual(BACKEND / 'data' / 'joolan_sync', paths.SYNC_DIR)
        self.assertEqual(BACKEND / 'output', paths.OUTPUT_DIR)
        self.assertEqual(BACKEND / '.env', paths.ENV_FILE)


class RelocationTests(unittest.TestCase):
    def probe(self, code_dir, **env):
        result = subprocess.run([sys.executable, '-B', '-c', PROBE], cwd=code_dir, env=scrubbed_env(**env),
                                capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise AssertionError(result.stderr[-2000:])
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_moved_code_defaults_to_its_own_folder_and_home_override_decouples_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, elsewhere = Path(tmp, 'code'), Path(tmp, 'elsewhere')
            code.mkdir()
            copy_code(code)
            plain = self.probe(code)
            self.assertEqual(str(code.resolve()), plain['code'])
            self.assertEqual(str(code.resolve()), plain['home'])
            self.assertEqual(str(code.resolve() / 'data' / 'joolan_live.db'), plain['db'])
            self.assertEqual(str(code.resolve()), plain['main_base'])

            moved = self.probe(code, FORECASTER_HOME=str(elsewhere))
            home = str(elsewhere.resolve())
            self.assertEqual(str(code.resolve()), moved['code'], 'code location is independent of the data home')
            self.assertEqual(home, moved['home'])
            for key in ('db', 'history', 'source', 'env_file', 'output', 'append', 'data_file'):
                self.assertTrue(moved[key].startswith(home), (key, moved[key]))
            self.assertEqual(home, moved['main_base'])

    def test_database_override_still_wins_for_the_serving_database_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, custom = Path(tmp, 'home'), Path(tmp, 'custom.db')
            moved = self.probe(BACKEND, FORECASTER_HOME=str(home), FORECASTER_DB_PATH=str(custom))
            self.assertEqual(str(custom.resolve()), moved['db'])
            self.assertTrue(moved['history'].startswith(str(home.resolve())))


class WorkerTests(unittest.TestCase):
    def test_commands_use_module_names_not_script_paths(self):
        for command in (automatic_forecast.worker_command('abc'), fresh_routes.worker_command('abc')):
            self.assertEqual(['-B', '-u', '-m'], command[1:4])
            self.assertFalse(any(part.endswith('.py') for part in command), command)
        self.assertEqual('automatic_worker', automatic_forecast.worker_command('x')[4])
        self.assertEqual('fresh_worker', fresh_routes.worker_command('x')[4])

    def test_launchers_start_workers_from_the_code_directory(self):
        with patch.object(automatic_forecast.subprocess, 'Popen') as popen, \
                patch.object(automatic_forecast.fresh, 'connect') as connect, \
                patch.object(automatic_forecast, 'ensure'), \
                patch.object(automatic_forecast, 'read', return_value={'pid': 1}):
            automatic_forecast.launch('job1')
        args, kwargs = popen.call_args
        self.assertEqual(automatic_forecast.worker_command('job1'), args[0])
        self.assertEqual(paths.CODE_DIR, kwargs['cwd'])
        with patch.object(fresh_routes.subprocess, 'Popen') as popen:
            fresh_routes.launch('run1', 'secret-key')
        args, kwargs = popen.call_args
        self.assertEqual(fresh_routes.worker_command('run1'), args[0])
        self.assertEqual(paths.CODE_DIR, kwargs['cwd'])

    def test_workers_start_from_a_relocated_copy_and_write_only_to_the_data_home(self):
        """A child process must import cleanly and honour FORECASTER_HOME, wherever the code sits."""
        with tempfile.TemporaryDirectory() as tmp:
            code, home = Path(tmp, 'code'), Path(tmp, 'home')
            (home / 'data').mkdir(parents=True)
            code.mkdir()
            copy_code(code)
            env = scrubbed_env(FORECASTER_HOME=str(home))
            cases = ((automatic_forecast.worker_command('nojob'), ''),
                     (fresh_routes.worker_command('nojob'), json.dumps({'apiKey': 'unused'}) + '\n'))
            for command, stdin in cases:
                with self.subTest(worker=command[4]):
                    result = subprocess.run(command, cwd=code, env=env, input=stdin, capture_output=True,
                                            text=True, timeout=120)
                    self.assertEqual(0, result.returncode, result.stderr[-1500:])
                    self.assertNotIn('ModuleNotFoundError', result.stderr)
                    self.assertNotIn('ImportError', result.stderr)
            self.assertTrue((home / 'data' / 'joolan_source.db').exists(), 'workers wrote to the data home')
            self.assertFalse((code / 'data').exists(), 'nothing is written next to the code')

    def test_real_launch_starts_a_worker_that_uses_the_data_home(self):
        """fresh_routes.launch spawns a detached child (no console on Windows); prove it started and ran."""
        import time
        children = []
        real_popen = subprocess.Popen
        def start_child(*args, **kwargs):
            child = real_popen(*args, **kwargs)
            children.append(child)
            return child
        with tempfile.TemporaryDirectory() as home:
            Path(home, 'data').mkdir()
            with patch.dict(os.environ, {'FORECASTER_HOME': home}), patch.object(fresh_routes.subprocess, 'Popen', side_effect=start_child):
                fresh_routes.launch('nojob', 'unused-key')
            marker = Path(home, 'data', 'joolan_source.db')
            deadline = time.time() + 30
            while not marker.exists() and time.time() < deadline:
                time.sleep(0.25)
            self.assertTrue(marker.exists(), 'the detached worker never reached its database')
            # A fixed sleep races the actual worker exit on Windows and leaks a DB handle.
            for child in children:
                self.assertEqual(0, child.wait(timeout=30))


class FingerprintTests(unittest.TestCase):
    def test_code_hash_matches_hashing_the_files_directly(self):
        names = ('forecasting', 'article_forecast')
        expected = hashlib.sha256(b''.join((BACKEND / f'{n}.py').read_bytes() for n in names)).hexdigest()
        self.assertEqual(expected, code_fingerprint.code_hash(names))
        self.assertEqual({f'{n}.py': hashlib.sha256((BACKEND / f'{n}.py').read_bytes()).hexdigest() for n in names},
                         code_fingerprint.file_hashes(names))

    def test_every_lineage_module_resolves(self):
        for name in main.CODE_MODULES:
            self.assertTrue((BACKEND / f'{name}.py').is_file(), name)
        code_fingerprint.code_hash(main.CODE_MODULES)

    def test_hash_is_the_same_when_the_code_sits_elsewhere(self):
        script = ("import code_fingerprint, main; print(code_fingerprint.code_hash(main.CODE_MODULES))")
        with tempfile.TemporaryDirectory() as tmp:
            copy_code(Path(tmp))
            moved = subprocess.run([sys.executable, '-B', '-c', script], cwd=tmp, env=scrubbed_env(),
                                   capture_output=True, text=True, timeout=180)
        self.assertEqual(0, moved.returncode, moved.stderr[-1500:])
        self.assertEqual(code_fingerprint.code_hash(main.CODE_MODULES), moved.stdout.strip().splitlines()[-1])


if __name__ == '__main__':
    unittest.main()
