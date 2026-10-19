"""
Azure Entra ID JWT validation for FastAPI.

When FORECASTER_AUTH_ENABLED is false (or FORECASTER_AUTH_DEV_BYPASS is true),
requests receive a synthetic dev admin user for local development.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from preduit_app import client_config as config

_bearer = HTTPBearer(auto_error=False)
_jwk_client: Optional[PyJWKClient] = None


@dataclass(frozen=True)
class AuthUser:
    sub: str
    email: str
    name: str
    roles: tuple[str, ...]

    @property
    def display_name(self) -> str:
        return self.name or self.email or self.sub

    @property
    def primary_role(self) -> str:
        from preduit_app.rbac import highest_role

        return highest_role(self.roles)


def _issuer() -> str:
    return f"https://login.microsoftonline.com/{config.AZURE_TENANT_ID}/v2.0"


def _jwks_client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        url = f"https://login.microsoftonline.com/{config.AZURE_TENANT_ID}/discovery/v2.0/keys"
        _jwk_client = PyJWKClient(url, cache_keys=True, lifespan=3600)
    return _jwk_client


def _dev_user() -> AuthUser:
    role = (
        config.AUTH_DEV_ROLE
        if config.AUTH_DEV_ROLE in ("worker", "manager", "admin", "owner")
        else "admin"
    )
    return AuthUser(
        sub="dev-user",
        email="dev@localhost",
        name="Dev User",
        roles=(role,),
    )


def _map_entra_roles(raw_roles: list[Any]) -> tuple[str, ...]:
    from preduit_app.rbac import ENTRA_ROLE_MAP

    mapped: list[str] = []
    for raw in raw_roles:
        key = str(raw)
        role = ENTRA_ROLE_MAP.get(key)
        if role and role not in mapped:
            mapped.append(role)
    return tuple(mapped)


def _validate_azure_token(token: str) -> AuthUser:
    if not config.AZURE_TENANT_ID or not config.AZURE_API_AUDIENCE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is enabled but Azure Entra settings are incomplete.",
        )

    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=config.AZURE_API_AUDIENCE,
            issuer=_issuer(),
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        ) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token.",
        ) from exc

    roles = _map_entra_roles(payload.get("roles") or [])
    if not roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No Preduit role assigned in Azure Entra.",
        )

    return AuthUser(
        sub=str(payload.get("sub", "")),
        email=str(payload.get("preferred_username") or payload.get("email") or ""),
        name=str(payload.get("name") or ""),
        roles=roles,
    )


def auth_is_active() -> bool:
    return config.AUTH_ENABLED and not config.AUTH_DEV_BYPASS


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    access_token: Optional[str] = Query(None, alias="access_token"),
) -> AuthUser:
    if not auth_is_active():
        return _dev_user()

    token = None
    if credentials is not None and credentials.credentials:
        token = credentials.credentials
    elif access_token:
        token = access_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _validate_token(token)


def _validate_token(token: str) -> AuthUser:
    """Route a bearer token to local (email/password) or Azure SSO validation."""
    from preduit_app.local_auth import is_local_token, validate_local_token

    if is_local_token(token):
        return validate_local_token(token)
    return _validate_azure_token(token)


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[AuthUser]:
    if not auth_is_active():
        return _dev_user()
    if credentials is None or not credentials.credentials:
        return None
    return _validate_token(credentials.credentials)
