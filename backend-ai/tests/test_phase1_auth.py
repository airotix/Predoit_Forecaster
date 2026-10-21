"""Phase 1: authentication, roles, access gate, container access and backups.

Authentication is off by default, so these tests also pin that nothing changes then.
"""
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient
from starlette.requests import Request

import access_settings
import api_server
import auth_routes
import db_backup
import local_auth
import rbac

SECRET = 'unit-test-secret-unit-test-secret-1234'


def make_request(method, path, headers=None, query=''):
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({'type': 'http', 'method': method, 'path': path, 'query_string': query.encode(),
                    'headers': raw, 'server': ('localhost', 80), 'scheme': 'http', 'client': ('127.0.0.1', 1)})


def token_for(role, **extra):
    now = int(time.time())
    claims = {'iss': local_auth.LOCAL_TOKEN_ISSUER, 'sub': '9', 'email': f'{role}@x.io', 'name': role,
              'roles': [role], 'iat': now, 'exp': now + 600}
    claims.update(extra)
    return jwt.encode(claims, SECRET, algorithm='HS256')


class PolicyTests(unittest.TestCase):
    def test_public_routes(self):
        for method, path in (('GET', '/health'), ('GET', '/api/health'), ('GET', '/api/auth/config'),
                             ('POST', '/api/auth/login'), ('POST', '/api/auth/signup'), ('GET', '/docs')):
            self.assertIsNone(rbac.required_role(method, path), (method, path))

    def test_role_requirements(self):
        cases = {
            ('GET', '/api/dashboard'): 'worker', ('GET', '/api/products/size-history'): 'worker',
            ('GET', '/api/projections/R1/detail'): 'worker', ('GET', '/api/seasons/active'): 'worker',
            ('GET', '/api/pipeline/lineage'): 'worker', ('GET', '/api/joolan/summary'): 'worker',
            ('GET', '/api/events'): 'worker', ('GET', '/api/auth/me'): 'worker',
            ('GET', '/api/budget'): 'manager', ('GET', '/api/purchase-orders'): 'manager',
            ('PUT', '/api/purchase-orders/1'): 'manager', ('POST', '/api/seasons'): 'manager',
            ('PUT', '/api/catalogue/prices'): 'manager', ('GET', '/api/customers'): 'manager',
            ('PUT', '/api/recommendations/R/C'): 'manager', ('GET', '/api/joolan/fresh'): 'manager',
            ('POST', '/api/joolan/fresh'): 'admin', ('POST', '/api/automatic'): 'admin',
            ('POST', '/api/forecast/refresh'): 'admin', ('POST', '/api/history/build'): 'admin',
            ('POST', '/api/ingest/file'): 'admin', ('GET', '/api/ingest/status/abc'): 'admin',
            ('GET', '/api/auth/users'): 'admin', ('PUT', '/api/auth/users/role'): 'admin',
            ('POST', '/api/admin/db/backup'): 'admin', ('GET', '/api/admin/db/health'): 'admin',
        }
        for (method, path), role in cases.items():
            self.assertEqual(role, rbac.required_role(method, path), (method, path))

    def test_unlisted_routes_default_to_manager(self):
        self.assertEqual('manager', rbac.required_role('GET', '/api/something-new'))

    def test_every_registered_route_resolves_and_writes_are_never_worker(self):
        for route in api_server.app.routes:
            for method in getattr(route, 'methods', None) or ():
                role = rbac.required_role(method, route.path)
                if role is None:
                    continue
                self.assertIn(role, rbac.VALID_ROLES)
                if method in rbac.WRITE_METHODS:
                    self.assertNotEqual('worker', role, (method, route.path))

    def test_owner_equals_admin(self):
        self.assertTrue(rbac.has_min_role(('owner',), 'admin'))
        self.assertFalse(rbac.has_min_role(('manager',), 'admin'))


class AuthorizeTests(unittest.TestCase):
    def setUp(self):
        for name, value in (('AUTH_ENABLED', True), ('AUTH_DEV_BYPASS', False), ('AUTH_LOCAL_SECRET', SECRET)):
            patcher = patch.object(access_settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_inactive_authentication_defers_to_existing_rules(self):
        with patch.object(access_settings, 'AUTH_ENABLED', False):
            self.assertIsNone(auth_routes.authorize(make_request('GET', '/api/budget')))

    def test_missing_invalid_expired_and_foreign_tokens_are_rejected(self):
        self.assertEqual(401, auth_routes.authorize(make_request('GET', '/api/dashboard')).status_code)
        for token in ('garbage', token_for('admin', exp=int(time.time()) - 5),
                      jwt.encode({'iss': local_auth.LOCAL_TOKEN_ISSUER, 'sub': '1', 'roles': ['admin'],
                                  'exp': int(time.time()) + 60}, 'another-secret-another-secret-12345', algorithm='HS256')):
            response = auth_routes.authorize(make_request('GET', '/api/dashboard', {'Authorization': 'Bearer ' + token}))
            self.assertEqual(401, response.status_code)

    def test_roles_are_enforced(self):
        def check(role, method, path):
            return auth_routes.authorize(make_request(method, path, {'Authorization': 'Bearer ' + token_for(role)}))
        self.assertIs(True, check('worker', 'GET', '/api/dashboard'))
        self.assertEqual(403, check('worker', 'GET', '/api/budget').status_code)
        self.assertEqual(403, check('worker', 'PUT', '/api/budget/settings').status_code)
        self.assertIs(True, check('manager', 'PUT', '/api/budget/settings'))
        self.assertEqual(403, check('manager', 'POST', '/api/forecast/refresh').status_code)
        self.assertIs(True, check('admin', 'POST', '/api/forecast/refresh'))
        self.assertIs(True, check('owner', 'GET', '/api/auth/users'))

    def test_only_the_event_stream_accepts_a_query_token(self):
        token = token_for('worker')
        self.assertIs(True, auth_routes.authorize(make_request('GET', '/api/events', query='access_token=' + token)))
        self.assertEqual(401, auth_routes.authorize(make_request('GET', '/api/dashboard', query='access_token=' + token)).status_code)

    def test_preflight_and_public_routes_pass_without_a_token(self):
        self.assertIs(True, auth_routes.authorize(make_request('OPTIONS', '/api/budget')))
        self.assertIs(True, auth_routes.authorize(make_request('GET', '/api/auth/config')))


class ApiTests(unittest.TestCase):
    """The real app against a throw-away database."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'api.db'
        self.patches = [patch.object(api_server, 'get_connection', lambda: sqlite3.connect(self.path))]

    def client(self, **kwargs):
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        client = TestClient(api_server.app, **kwargs)
        client.__enter__()
        self.addCleanup(lambda: client.__exit__(None, None, None))
        return client

    def enable_auth(self, **extra):
        values = dict(AUTH_ENABLED=True, AUTH_DEV_BYPASS=False, AUTH_LOCAL_SECRET=SECRET, AUTH_ALLOW_SIGNUP=True)
        values.update(extra)
        for name, value in values.items():
            patcher = patch.object(access_settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def signup(self, client, email, password='correct horse'):
        response = client.post('/api/auth/signup', json={'email': email, 'password': password, 'name': email.split('@')[0]})
        return response

    def bearer(self, response):
        return {'Authorization': 'Bearer ' + response.json()['token']}

    # ---- authentication off: nothing changes
    def test_default_mode_needs_no_token_and_reports_dev_user(self):
        client = self.client()
        self.assertNotIn(client.get('/api/budget/options').status_code, (401, 403))
        config = client.get('/api/auth/config').json()
        self.assertEqual((False, False, True), (config['authEnabled'], config['authActive'], config['devMode']))
        me = client.get('/api/auth/me').json()
        self.assertEqual(('dev@localhost', 'admin'), (me['email'], me['role']))

    def test_remote_clients_stay_blocked_unless_explicitly_allowed(self):
        client = self.client(client=('203.0.113.9', 5000))
        self.assertEqual(403, client.get('/api/auth/config', headers={'host': 'localhost'}).status_code)
        patcher = patch.object(access_settings, 'ALLOW_NON_LOCAL', True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertEqual(200, client.get('/api/auth/config', headers={'host': 'localhost'}).status_code)
        self.assertEqual(403, client.get('/api/auth/config', headers={'host': 'evil.example'}).status_code,
                         'the Host header check still applies')

    def test_browser_origins_follow_configuration(self):
        client = self.client()
        self.assertEqual(403, client.get('/api/auth/config', headers={'origin': 'https://app.example.com'}).status_code)
        patcher = patch.object(access_settings, 'CORS_ORIGINS', ('https://app.example.com',))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertEqual(200, client.get('/api/auth/config', headers={'origin': 'https://app.example.com'}).status_code)
        self.assertEqual(403, client.get('/api/auth/config', headers={'origin': 'http://localhost:3000'}).status_code)

    # ---- authentication on
    def test_sign_up_log_in_and_roles_end_to_end(self):
        self.enable_auth()
        client = self.client(client=('203.0.113.9', 5000))
        self.assertEqual(401, client.get('/api/dashboard').status_code)
        self.assertTrue(client.get('/api/auth/config').json()['authActive'])

        first = self.signup(client, 'boss@example.com')
        self.assertEqual(200, first.status_code, first.text)
        self.assertEqual('owner', first.json()['user']['role'])
        second = self.signup(client, 'staff@example.com')
        self.assertEqual('worker', second.json()['user']['role'])

        worker, owner = self.bearer(second), self.bearer(first)
        self.assertNotIn(client.get('/api/dashboard', headers=worker).status_code, (401, 403))
        self.assertEqual(403, client.get('/api/budget', headers=worker).status_code)
        self.assertEqual(403, client.get('/api/auth/users', headers=worker).status_code)
        self.assertEqual('worker', client.get('/api/auth/me', headers=worker).json()['role'])

        users = client.get('/api/auth/users', headers=owner)
        self.assertEqual(200, users.status_code)
        self.assertEqual(['boss@example.com', 'staff@example.com'], [u['email'] for u in users.json()['users']])
        self.assertNotIn('password_hash', users.text)

        promoted = client.put('/api/auth/users/role', headers=owner, json={'email': 'staff@example.com', 'role': 'manager'})
        self.assertEqual('manager', promoted.json()['user']['role'])
        self.assertEqual(400, client.put('/api/auth/users/role', headers=owner,
                                         json={'email': 'boss@example.com', 'role': 'worker'}).status_code)
        self.assertEqual(422, client.put('/api/auth/users/role', headers=owner,
                                         json={'email': 'staff@example.com', 'role': 'root'}).status_code)
        self.assertEqual(404, client.put('/api/auth/users/role', headers=owner,
                                         json={'email': 'ghost@example.com', 'role': 'worker'}).status_code)

        login = client.post('/api/auth/login', json={'email': 'STAFF@example.com', 'password': 'correct horse'})
        self.assertEqual('manager', login.json()['user']['role'])
        self.assertNotIn(client.get('/api/budget/options', headers=self.bearer(login)).status_code, (401, 403))

    def test_sign_up_and_login_validation(self):
        self.enable_auth()
        client = self.client()
        self.assertEqual(422, self.signup(client, 'not-an-email').status_code)
        self.assertEqual(422, self.signup(client, 'a@b.co', password='short').status_code)
        self.assertEqual(200, self.signup(client, 'a@b.co').status_code)
        self.assertEqual(409, self.signup(client, 'A@B.co').status_code)
        self.assertEqual(401, client.post('/api/auth/login', json={'email': 'a@b.co', 'password': 'wrong password'}).status_code)
        self.assertEqual(401, client.post('/api/auth/login', json={'email': 'nobody@b.co', 'password': 'whatever1'}).status_code)

    def test_signup_can_be_disabled(self):
        self.enable_auth(AUTH_ALLOW_SIGNUP=False)
        self.assertEqual(403, self.signup(self.client(), 'a@b.co').status_code)

    def test_inactive_account_cannot_log_in(self):
        self.enable_auth()
        client = self.client()
        self.signup(client, 'a@b.co')
        conn = sqlite3.connect(self.path)
        conn.execute("UPDATE users SET status='disabled'")
        conn.commit()
        conn.close()
        self.assertEqual(403, client.post('/api/auth/login', json={'email': 'a@b.co', 'password': 'correct horse'}).status_code)

    def test_denials_still_carry_cors_headers(self):
        self.enable_auth()
        client = self.client()
        response = client.get('/api/dashboard', headers={'origin': 'http://localhost:3000'})
        self.assertEqual(401, response.status_code)
        self.assertEqual('http://localhost:3000', response.headers.get('access-control-allow-origin'))

    def test_users_survive_a_forecast_publish(self):
        import database
        self.enable_auth()
        client = self.client()
        self.signup(client, 'a@b.co')
        conn = sqlite3.connect(self.path)
        database._create_schema(conn)  # drops and recreates every forecast table
        conn.commit()
        self.assertEqual(1, conn.execute('SELECT COUNT(*) FROM users').fetchone()[0])
        conn.close()


class BackupTests(unittest.TestCase):
    def make_db(self, path, rows=3):
        conn = sqlite3.connect(path)
        conn.execute('CREATE TABLE t(x)')
        conn.executemany('INSERT INTO t VALUES(?)', [(i,) for i in range(rows)])
        conn.commit()
        conn.close()

    def test_backup_is_a_consistent_copy_and_old_ones_are_pruned(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, destination = Path(tmp) / 'live.db', Path(tmp) / 'backups'
            self.make_db(source)
            made = [db_backup.create_backup('serving', source, destination, keep=2) for _ in range(3)]
            self.assertTrue(all(m['integrityOk'] for m in made))
            kept = db_backup.list_backups(destination)
            self.assertEqual(2, len(kept))
            self.assertEqual({'serving'}, {k['database'] for k in kept})
            copy = sqlite3.connect(kept[0]['path'])
            self.assertEqual(3, copy.execute('SELECT COUNT(*) FROM t').fetchone()[0])
            copy.close()
            with self.assertRaises(FileNotFoundError):
                db_backup.create_backup('serving', Path(tmp) / 'missing.db', destination)

    def test_admin_endpoints_back_up_every_existing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, history = Path(tmp) / 'joolan_live.db', Path(tmp) / 'history.db'
            self.make_db(live)
            self.make_db(history)
            fake = {'serving': live, 'source': Path(tmp) / 'joolan_source.db', 'history': history}
            with patch.object(db_backup, 'databases', lambda: fake), \
                    patch.dict('os.environ', {'FORECASTER_BACKUP_DIR': str(Path(tmp) / 'out')}), \
                    patch.object(api_server, 'get_connection', lambda: sqlite3.connect(live)), \
                    TestClient(api_server.app) as client:
                health = client.get('/api/admin/db/health').json()['databases']
                self.assertTrue(health['serving']['integrityOk'])
                self.assertFalse(health['source']['exists'])
                result = client.post('/api/admin/db/backup').json()
                self.assertEqual({'serving', 'history'}, {b['database'] for b in result['backups']})
                self.assertEqual(['source'], [s['database'] for s in result['skipped']])
                self.assertEqual(2, len(client.get('/api/admin/db/backups').json()['backups']))


if __name__ == '__main__':
    unittest.main()
