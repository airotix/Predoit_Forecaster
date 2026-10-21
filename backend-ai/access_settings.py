"""Access-control settings (authentication, roles, browser origins).

Read from the environment when the module is imported. Defaults keep today's behaviour:
authentication off, local-only access, localhost:3000 browser origins.
"""
import os

DEFAULT_ORIGINS = ('http://localhost:3000', 'http://127.0.0.1:3000')


def _flag(name, default):
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in ('1', 'true', 'yes', 'on')


def _text(name, default=''):
    raw = os.environ.get(name)
    return raw.strip() if raw and raw.strip() else default


def _number(name, default):
    try:
        return int(_text(name, str(default)))
    except ValueError:
        return default


def _origins():
    raw = _text('FORECASTER_CORS_ORIGINS')
    listed = [o.strip().rstrip('/') for o in raw.split(',') if o.strip()]
    return tuple(listed) or DEFAULT_ORIGINS


CORS_ORIGINS = _origins()

# FORECASTER_AUTH_ENABLED=true is sufficient to turn authentication on. The dev bypass
# only matters when set explicitly (it defaults to "on" only while auth is disabled).
AUTH_ENABLED = _flag('FORECASTER_AUTH_ENABLED', False)
AUTH_DEV_BYPASS = _flag('FORECASTER_AUTH_DEV_BYPASS', not AUTH_ENABLED)
AUTH_DEV_ROLE = _text('FORECASTER_AUTH_DEV_ROLE', 'admin')
AZURE_TENANT_ID = _text('FORECASTER_AZURE_TENANT_ID')
AZURE_CLIENT_ID = _text('FORECASTER_AZURE_CLIENT_ID')
AZURE_API_AUDIENCE = _text('FORECASTER_AZURE_API_AUDIENCE', AZURE_CLIENT_ID)
AUTH_LOCAL_SECRET = _text('FORECASTER_AUTH_SECRET')
AUTH_TOKEN_TTL_HOURS = _number('FORECASTER_AUTH_TOKEN_TTL_HOURS', 12)
AUTH_ALLOW_SIGNUP = _flag('FORECASTER_AUTH_ALLOW_SIGNUP', True)
SSO_ENABLED = bool(AZURE_TENANT_ID and AZURE_CLIENT_ID)

# Container deployments reach the API through a port mapping, so the client address is
# not loopback. Opt in explicitly; only do this with the port published to localhost.
ALLOW_NON_LOCAL = _flag('FORECASTER_ALLOW_NON_LOCAL', False)

BACKUP_KEEP = _number('FORECASTER_BACKUP_KEEP', 14)


def auth_is_active():
    return AUTH_ENABLED and not AUTH_DEV_BYPASS
