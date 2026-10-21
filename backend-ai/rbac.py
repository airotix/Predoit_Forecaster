"""Role model and the route policy that maps a request to the minimum role it needs.

Hierarchy: owner = admin (top) > manager > worker (view-only).
Route groups follow the frontend (USER_ROUTES / MANAGER_ROUTES in lib/auth/msalConfig.ts)
and the packaged API this replaces: data export, forecast and user management are
admin-only; everything not listed is manager-only so new routes are closed by default.
"""
ENTRA_ROLE_MAP = {
    'Preduit.Owner': 'owner',
    'Preduit.Admin': 'admin',
    'Preduit.Manager': 'manager',
    'Preduit.Worker': 'worker',
    # Legacy app-role name kept for smooth migration from the 3-role model.
    'Preduit.User': 'worker',
}
ROLE_LEVEL = {'worker': 1, 'manager': 2, 'admin': 3, 'owner': 3}
VALID_ROLES = tuple(ROLE_LEVEL)
WRITE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})

PUBLIC = frozenset({
    ('GET', '/health'), ('GET', '/api/health'), ('GET', '/api/auth/config'),
    ('POST', '/api/auth/login'), ('POST', '/api/auth/signup'),
})
PUBLIC_PREFIXES = ('/docs', '/redoc', '/openapi.json')

# (methods or None for all, path prefix, minimum role); the first match wins.
RULES = (
    (None, '/api/auth/me', 'worker'),
    (None, '/api/auth', 'admin'),
    (None, '/api/admin', 'admin'),
    (None, '/api/ingest', 'admin'),
    (WRITE_METHODS, '/api/joolan', 'admin'),
    (WRITE_METHODS, '/api/automatic', 'admin'),
    (WRITE_METHODS, '/api/history', 'admin'),
    (WRITE_METHODS, '/api/forecast', 'admin'),
    # Read-only views every signed-in role may open (dashboard, products, projection, shell status).
    (frozenset({'GET'}), '/api/dashboard', 'worker'),
    (frozenset({'GET'}), '/api/filter-options', 'worker'),
    (frozenset({'GET'}), '/api/articles', 'worker'),
    (frozenset({'GET'}), '/api/audit', 'worker'),
    (frozenset({'GET'}), '/api/products', 'worker'),
    (frozenset({'GET'}), '/api/projections', 'worker'),
    (frozenset({'GET'}), '/api/seasons', 'worker'),
    (frozenset({'GET'}), '/api/pipeline', 'worker'),
    (frozenset({'GET'}), '/api/joolan/summary', 'worker'),
    (frozenset({'GET'}), '/api/forecast/job', 'worker'),
    (frozenset({'GET'}), '/api/events', 'worker'),
)
DEFAULT_ROLE = 'manager'


def role_level(role):
    return ROLE_LEVEL.get(role, 0)


def highest_role(roles):
    best, best_level = 'worker', 0
    for role in roles:
        if role_level(role) > best_level:
            best, best_level = role, role_level(role)
    return best


def has_min_role(roles, minimum):
    return any(role_level(r) >= role_level(minimum) for r in roles)


def _under(path, prefix):
    return path == prefix or path.startswith(prefix + '/')


def required_role(method, path):
    """Minimum role for a request, or None when the route is public."""
    method = method.upper()
    path = path.rstrip('/') or '/'
    if (method, path) in PUBLIC or path.startswith(PUBLIC_PREFIXES):
        return None
    for methods, prefix, role in RULES:
        if (methods is None or method in methods) and _under(path, prefix):
            return role
    return DEFAULT_ROLE
