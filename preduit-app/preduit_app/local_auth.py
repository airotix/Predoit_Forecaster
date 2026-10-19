"""
Local email/password authentication for Preduit.

Complements the Azure Entra ID SSO path in `auth.py`. Passwords are hashed with
PBKDF2-HMAC-SHA256 (Python stdlib — no extra dependencies) and sessions are
issued as short-lived HS256 JWTs signed with FORECASTER_AUTH_SECRET.

Roles (highest to lowest): owner = admin (top) > manager > worker (view-only).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Optional

import jwt

from preduit_app import client_config as config

_logger = logging.getLogger("preduit.auth")

LOCAL_TOKEN_ISSUER = "preduit-local"
_PBKDF2_ALGORITHM = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 210_000
_VALID_ROLES = ("worker", "manager", "admin", "owner")

# Process-stable fallback secret for local dev when none is configured. It is
# regenerated on every restart (so tokens don't survive a restart) and always
# logs a warning — never rely on this in production.
_FALLBACK_SECRET = secrets.token_urlsafe(48)
_warned_fallback = False


def _signing_secret() -> str:
    global _warned_fallback
    if config.AUTH_LOCAL_SECRET:
        return config.AUTH_LOCAL_SECRET
    if not _warned_fallback:
        _logger.warning(
            "FORECASTER_AUTH_SECRET is not set — using an ephemeral dev secret. "
            "Local login tokens will be invalidated on restart. Set a strong secret "
            "before client handover."
        )
        _warned_fallback = True
    return _FALLBACK_SECRET


# ── Password hashing ──

def hash_password(password: str) -> str:
    """Return a PBKDF2 hash string: pbkdf2_sha256$iterations$salt_hex$hash_hex."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{_PBKDF2_ALGORITHM}${_PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verify a password against a stored PBKDF2 hash string."""
    try:
        algorithm, iterations_s, salt_hex, hash_hex = stored.split("$")
        if algorithm != _PBKDF2_ALGORITHM:
            return False
        iterations = int(iterations_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(dk, expected)


# ── JWT issue / validate ──

def issue_token(user: dict) -> str:
    """Issue a signed session JWT for a user record."""
    now = int(time.time())
    ttl_seconds = max(1, config.AUTH_TOKEN_TTL_HOURS) * 3600
    payload = {
        "iss": LOCAL_TOKEN_ISSUER,
        "sub": str(user["id"]),
        "email": user["email"],
        "name": user.get("name") or "",
        "roles": [user["role"]],
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, _signing_secret(), algorithm="HS256")


def is_local_token(token: str) -> bool:
    """Cheap unverified check for whether a token was issued by us (not Azure)."""
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return False
    return claims.get("iss") == LOCAL_TOKEN_ISSUER


def validate_local_token(token: str):
    """Validate a local session JWT and return an AuthUser. Raises HTTPException."""
    from fastapi import HTTPException, status
    from preduit_app.auth import AuthUser

    try:
        payload = jwt.decode(
            token,
            _signing_secret(),
            algorithms=["HS256"],
            issuer=LOCAL_TOKEN_ISSUER,
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired. Please sign in again.",
        ) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token.",
        ) from exc

    roles = tuple(r for r in (payload.get("roles") or []) if r in _VALID_ROLES)
    if not roles:
        roles = ("worker",)
    return AuthUser(
        sub=str(payload.get("sub", "")),
        email=str(payload.get("email") or ""),
        name=str(payload.get("name") or ""),
        roles=roles,
    )
