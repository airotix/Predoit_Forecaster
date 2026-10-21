"""Phase 0 behaviour lock: the HTTP surface must not change during the migration.

Snapshot files live in tests/fixtures. When a change is intentional (for example
Phase 1 serving a route the frontend already calls), regenerate them with
    UPDATE_PHASE0_SNAPSHOTS=1 python -B -m unittest discover -s tests -p "test_phase0*.py"
and review the diff in the PR.
"""
import json
import os
import unittest

import api_server
import phase0_support as support

UPDATE = os.environ.get('UPDATE_PHASE0_SNAPSHOTS') == '1'


def _check(testcase, name, actual):
    path = support.FIXTURES / name
    if UPDATE:
        path.write_text(json.dumps(actual, indent=1) + '\n', encoding='utf-8')
    expected = support.load_fixture(name)
    testcase.assertEqual(
        expected, actual,
        f'{name} differs from the committed snapshot. If intentional, regenerate with '
        'UPDATE_PHASE0_SNAPSHOTS=1 and review the diff.')


class RouteContractTests(unittest.TestCase):
    def setUp(self):
        self.routes = support.backend_routes(api_server.app)

    def test_backend_route_table_is_unchanged(self):
        _check(self, 'phase0_routes.json', sorted([m, p] for m, p in self.routes))

    def test_frontend_calls_that_the_backend_does_not_serve_are_tracked(self):
        """Every frontend call is served, or is listed as known-unserved.

        The known list is today's reality (old /seasons/{id}/... contract, auth and
        accuracy/backtest endpoints that only preduit-app has). It may only shrink.
        """
        unserved = sorted([m, p] for m, p in support.frontend_calls()
                          if not support.match((m, p), self.routes))
        _check(self, 'phase0_frontend_unserved.json', unserved)

    def test_core_frontend_calls_are_served(self):
        """Guard the calls that the live pages depend on, independent of the snapshot."""
        required = [
            ('GET', '/dashboard'), ('GET', '/products'), ('GET', '/projections'),
            ('GET', '/recommendations'), ('GET', '/budget'), ('GET', '/catalogue'),
            ('GET', '/purchase-orders'), ('POST', '/purchase-orders'),
            ('GET', '/seasons'), ('POST', '/joolan/fresh'), ('GET', '/pipeline/status'),
            ('POST', '/forecast/refresh'), ('GET', '/forecast/job'),
            ('GET', '/orders'), ('GET', '/seasonal-allocation'),
        ]
        missing = [c for c in required if not support.match(c, self.routes)]
        self.assertEqual([], missing)


if __name__ == '__main__':
    unittest.main()
