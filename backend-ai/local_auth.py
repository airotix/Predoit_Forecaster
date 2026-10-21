"""Local email/password accounts: PBKDF2 password hashing and short-lived HS256 session tokens.

Complements Azure Entra SSO in auth.py. Sessions are signed with FORECASTER_AUTH_SECRET.
"""
import hashlib
import hmac
import logging
import os
import secrets
import time

import jwt

import access_settings as settings
from rbac import VALID_ROLES

_logger = logging.getLogger('preduit.auth')

LOCAL_TOKEN_ISSUER = 'preduit-local'
_ALGORITHM = 'pbkdf2_sha256'
_ITERATIONS = 210_000

# Ephemeral fallback so local development works without configuration; tokens do not survive
# a restart and a warning is logged. Production must set FORECASTER_AUTH_SECRET.
_FALLBACK_SECRET = secrets.token_urlsafe(48)
_warned = False


def _signing_secret():
    global _warned
    if settings.AUTH_LOCAL_SECRET:
        return settings.AUTH_LOCAL_SECRET
    if not _warned:
        _logger.warning('FORECASTER_AUTH_SECRET is not set; using an ephemeral secret. '
                        'Local sessions end on restart. Set a strong secret before shared use.')
        _warned = True
    return _FALLBACK_SECRET


def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, _ITERATIONS)
    return f'{_ALGORITHM}${_ITERATIONS}${salt.hex()}${digest.hex()}'


def verify_password(password, stored):
    try:
        algorithm, iterations, salt_hex, hash_hex = stored.split('$')
        if algorithm != _ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest, bytes.fromhex(hash_hex))
    except (ValueError, AttributeError):
        return False


def issue_token(user):
    now = int(time.time())
    return jwt.encode({
        'iss': LOCAL_TOKEN_ISSUER, 'sub': str(user['id']), 'email': user['email'],
        'name': user.get('name') or '', 'roles': [user['role']],
        'iat': now, 'exp': now + max(1, settings.AUTH_TOKEN_TTL_HOURS) * 3600,
    }, _signing_secret(), algorithm='HS256')


def is_local_token(token):
    try:
        return jwt.decode(token, options={'verify_signature': False}).get('iss') == LOCAL_TOKEN_ISSUER
    except jwt.PyJWTError:
        return False


def decode_local_token(token):
    """Return verified claims. Raises jwt.ExpiredSignatureError / jwt.PyJWTError."""
    payload = jwt.decode(token, _signing_secret(), algorithms=['HS256'], issuer=LOCAL_TOKEN_ISSUER,
                         options={'require': ['exp', 'sub']})
    roles = tuple(r for r in (payload.get('roles') or []) if r in VALID_ROLES) or ('worker',)
    return payload, roles
