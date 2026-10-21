"""Bearer-token validation: local sessions (local_auth) and Azure Entra ID JWTs.

When authentication is not active every request is treated as a synthetic dev user, so
nothing changes for local use.
"""
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

import access_settings as settings
import local_auth
from rbac import ENTRA_ROLE_MAP, VALID_ROLES, highest_role


class AuthError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass(frozen=True)
class AuthUser:
    sub: str
    email: str
    name: str
    roles: tuple

    @property
    def display_name(self):
        return self.name or self.email or self.sub

    @property
    def primary_role(self):
        return highest_role(self.roles)


_jwk_client = None


def dev_user():
    role = settings.AUTH_DEV_ROLE if settings.AUTH_DEV_ROLE in VALID_ROLES else 'admin'
    return AuthUser(sub='dev-user', email='dev@localhost', name='Dev User', roles=(role,))


def _jwks():
    global _jwk_client
    if _jwk_client is None:
        _jwk_client = PyJWKClient(
            f'https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}/discovery/v2.0/keys',
            cache_keys=True, lifespan=3600)
    return _jwk_client


def _validate_azure(token):
    if not settings.AZURE_TENANT_ID or not settings.AZURE_API_AUDIENCE:
        # SSO is optional: with password sign-in only, any non-local token is simply invalid.
        raise AuthError(401, 'Invalid access token.')
    try:
        key = _jwks().get_signing_key_from_jwt(token)
        payload = jwt.decode(token, key.key, algorithms=['RS256'], audience=settings.AZURE_API_AUDIENCE,
                             issuer=f'https://login.microsoftonline.com/{settings.AZURE_TENANT_ID}/v2.0',
                             options={'require': ['exp', 'sub']})
    except jwt.ExpiredSignatureError:
        raise AuthError(401, 'Token has expired.') from None
    except jwt.PyJWTError:
        raise AuthError(401, 'Invalid access token.') from None
    roles = []
    for raw in payload.get('roles') or []:
        mapped = ENTRA_ROLE_MAP.get(str(raw))
        if mapped and mapped not in roles:
            roles.append(mapped)
    if not roles:
        raise AuthError(403, 'No Preduit role assigned in Azure Entra.')
    return AuthUser(sub=str(payload.get('sub', '')), email=str(payload.get('preferred_username') or payload.get('email') or ''),
                    name=str(payload.get('name') or ''), roles=tuple(roles))


def _validate_local(token):
    try:
        payload, roles = local_auth.decode_local_token(token)
    except jwt.ExpiredSignatureError:
        raise AuthError(401, 'Session has expired. Please sign in again.') from None
    except jwt.PyJWTError:
        raise AuthError(401, 'Invalid session token.') from None
    return AuthUser(sub=str(payload.get('sub', '')), email=str(payload.get('email') or ''),
                    name=str(payload.get('name') or ''), roles=roles)


def validate_token(token):
    """Resolve a bearer token to an AuthUser or raise AuthError."""
    return _validate_local(token) if local_auth.is_local_token(token) else _validate_azure(token)
