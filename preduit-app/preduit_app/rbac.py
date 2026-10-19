"""
Role-based access control for Preduit API.

Hierarchy: owner = admin (top) > manager > worker (view-only, lowest)

- owner  : business owner — full access (same level as admin)
- admin  : system / IT admin — full access
- manager: view + overrides, locks, season config, budget, approvals
- worker : view-only — dashboards, products, projections; no writes
"""

from __future__ import annotations

from typing import Callable

from fastapi import Depends, HTTPException, status

from preduit_app.auth import AuthUser, get_current_user

ENTRA_ROLE_MAP = {
    "Preduit.Owner": "owner",
    "Preduit.Admin": "admin",
    "Preduit.Manager": "manager",
    "Preduit.Worker": "worker",
    # Legacy app-role name kept for smooth migration from the 3-role model.
    "Preduit.User": "worker",
}

# owner and admin share the top privilege level (3).
ROLE_LEVEL = {
    "worker": 1,
    "manager": 2,
    "admin": 3,
    "owner": 3,
}


def highest_role(roles: tuple[str, ...]) -> str:
    best = "worker"
    best_level = 0
    for role in roles:
        level = ROLE_LEVEL.get(role, 0)
        if level > best_level:
            best = role
            best_level = level
    return best


def role_level(role: str) -> int:
    return ROLE_LEVEL.get(role, 0)


def user_has_min_role(user: AuthUser, min_role: str) -> bool:
    required = role_level(min_role)
    return any(role_level(r) >= required for r in user.roles) or role_level(user.primary_role) >= required


def require_role(min_role: str) -> Callable[..., AuthUser]:
    """FastAPI dependency: require at least min_role (owner=admin > manager > worker)."""

    async def _dependency(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if not user_has_min_role(user, min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {min_role} role or higher.",
            )
        return user

    return _dependency
