"""Shared helpers for the Phase 0 behaviour-lock tests (see docs/MIGRATION_PLAN.md)."""
import json
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
FRONTEND_SRC = BACKEND_DIR.parent / 'frontend' / 'src'
FIXTURES = Path(__file__).resolve().parent / 'fixtures'
NON_API = ('/docs', '/redoc', '/openapi.json')

CLIENT_CALL = re.compile(r'apiClient\.(get|post|put|patch|delete)\s*(?:<.*?>)?\(\s*([`\'"])([^`\'"]*)\2')
BASE_CALL = re.compile(r'\$\{[^}`]*(?:API_BASE|API_URL|\bbase\b)[^}`]*\}((?:/(?:[^`\'"?\s$]|\$\{[^}]*\})*)+)')


def normalise(path):
    path = path.split('?')[0]
    path = re.sub(r'\$\{[^}]*\}', '{}', path)
    path = re.sub(r'\{[^}]*\}', '{}', path)
    return path.rstrip('/') or '/'


def backend_routes(app):
    """(METHOD, '/api/x/{}') for every API route registered on the app."""
    found = set()
    for route in app.routes:
        for method in getattr(route, 'methods', None) or ():
            if method in ('HEAD', 'OPTIONS'):
                continue
            path = route.path
            if path in NON_API or path.startswith('/docs'):
                continue
            found.add((method, path))
    return found


def frontend_calls():
    """Endpoints the frontend calls: {(METHOD|'ANY', path)} with path relative to /api."""
    calls = set()
    for source in sorted(FRONTEND_SRC.rglob('*.ts*')):
        if '.test.' in source.name:
            continue
        text = source.read_text(encoding='utf-8')
        for method, _, path in CLIENT_CALL.findall(text):
            calls.add((method.upper(), normalise(path)))
        for path in BASE_CALL.findall(text):
            calls.add(('ANY', normalise(path)))
    # Dynamic suffixes such as `/joolan${path}` are resolved by their callers; skip the stub.
    return {c for c in calls if '{}' not in c[1].replace('/{}', '')}


def match(call, routes):
    method, path = call
    for route_method, route_path in routes:
        if normalise(route_path) != '/api' + path:
            continue
        if method == 'ANY' or method == route_method:
            return True
    return False


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


# ---------------------------------------------------------------- golden master
def synthetic_orders(path):
    """Write a deterministic multi-article order history CSV (no RNG: pure arithmetic)."""
    import pandas as pd
    from m1_data_preparation import EXPECTED_COLUMNS
    rows = []
    articles = [('REF1', ('BLK', 'RED'), ('S', 'M', 'L'), 'Tops'),
                ('REF2', ('BLU',), ('M', 'L'), 'Bottoms'),
                ('REF3', ('BLK', 'WHT'), ('S', 'M'), 'Tops')]
    for number, month in enumerate(pd.period_range('2022-01', periods=36, freq='M')):
        for a, (ref, colours, sizes, family) in enumerate(articles):
            if ref == 'REF3' and number < 12:
                continue
            for c, colour in enumerate(colours):
                for s, size in enumerate(sizes):
                    for customer in (0, 1):
                        qty = 2 + (number * (a + 2) + c * 3 + s * 5 + customer * 7) % 9 + (4 if month.month in (3, 4, 9, 10) else 0)
                        row = {k: 0 if k.endswith(('_qte', '_ht')) or k in ('Prix', 'STOCK') else '' for k in EXPECTED_COLUMNS}
                        row.update(Client=f'C{customer}', Nom=f'Customer {customer}', Reference=ref, Couleur=colour, Taille=size,
                                   Reference_CDE=f'O{number}-{ref}-{colour}-{size}-{customer}',
                                   Date_Commande=f'{month}-05', Critere=f'Hiver({month.year})',
                                   CDE_qte=qty, LIV_qte=qty, RELIQUAT_qte=0, STOCK=3 + s, CDE_four_qte=1,
                                   Prix=20 + a * 5, Selling_Price=20 + a * 5, Purchase_Cost=8 + a * 2,
                                   Famille=family, Rayon='R', Saison='S')
                        rows.append(row)
    pd.DataFrame(rows).to_csv(path, index=False)
    return len(rows)


GOLDEN_ENDPOINTS = (
    '/api/pipeline/status', '/api/filter-options', '/api/dashboard', '/api/products',
    '/api/projections', '/api/recommendations', '/api/articles', '/api/customers',
    '/api/validation', '/api/budget', '/api/export?format=json',
)


def scrub(value, volatile):
    """Drop run-specific fields (timestamps, ids, paths) so snapshots compare behaviour only."""
    if isinstance(value, dict):
        return {k: scrub(v, volatile) for k, v in sorted(value.items()) if k not in volatile}
    if isinstance(value, list):
        return [scrub(v, volatile) for v in value]
    if isinstance(value, float):
        return round(value, 4)
    return value


def run_golden_pipeline(directory):
    """Run the real pipeline on the synthetic history, then read the API. Returns {endpoint: (status, body)}."""
    import os
    import sqlite3
    from unittest.mock import patch
    import database
    import main
    import api_server
    from fastapi.testclient import TestClient
    base = Path(directory)
    path, csv_path = base / 'golden.db', base / 'orders.csv'
    synthetic_orders(csv_path)
    with patch.dict(os.environ, {'FORECASTER_DISABLE_CATBOOST': '1'}):
        with patch.object(database, 'DB_FILE', path), \
                patch.object(database, 'get_connection', lambda: sqlite3.connect(path)), \
                patch.object(main, 'BASE_DIR', base):
            main._run_phase1(str(csv_path))
    out = {}
    with patch.object(api_server, 'get_connection', lambda: sqlite3.connect(path)):
        with TestClient(api_server.app) as client:
            # Startup re-asserts the fresh-only policy, so relax it afterwards (as test_reliability
            # does). The fresh-Joolan serving gate itself is covered by test_fresh_joolan.
            conn = sqlite3.connect(path)
            conn.execute("DELETE FROM joolan_state WHERE key='source_policy'")
            conn.execute("UPDATE joolan_state SET value='legacy' WHERE key='forecast_source'")
            conn.commit()
            conn.close()
            for endpoint in GOLDEN_ENDPOINTS:
                response = client.get(endpoint)
                body = response.json() if 'json' in response.headers.get('content-type', '') else response.text
                out[endpoint] = (response.status_code, body)
    return out
