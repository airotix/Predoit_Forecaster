"""Unit tests for RBAC role hierarchy and auth helpers."""

import pytest
from fastapi import HTTPException

from preduit_app.auth import AuthUser, auth_is_active
from preduit_app.rbac import (
    ENTRA_ROLE_MAP,
    highest_role,
    require_role,
    user_has_min_role,
)


def test_entra_role_map():
    assert ENTRA_ROLE_MAP["Preduit.Owner"] == "owner"
    assert ENTRA_ROLE_MAP["Preduit.Admin"] == "admin"
    assert ENTRA_ROLE_MAP["Preduit.Manager"] == "manager"
    assert ENTRA_ROLE_MAP["Preduit.Worker"] == "worker"
    # Legacy app-role name still maps to worker for migration.
    assert ENTRA_ROLE_MAP["Preduit.User"] == "worker"


def test_highest_role():
    assert highest_role(("worker",)) == "worker"
    assert highest_role(("manager", "worker")) == "manager"
    # owner and admin share the top level.
    assert highest_role(("owner",)) == "owner"
    user = AuthUser(sub="1", email="a@b.com", name="A", roles=("manager", "worker"))
    assert user.primary_role == "manager"


def test_user_has_min_role_hierarchy():
    owner = AuthUser(sub="0", email="", name="", roles=("owner",))
    admin = AuthUser(sub="1", email="", name="", roles=("admin",))
    manager = AuthUser(sub="2", email="", name="", roles=("manager",))
    worker = AuthUser(sub="3", email="", name="", roles=("worker",))

    # owner == admin at the top level.
    assert user_has_min_role(owner, "admin")
    assert user_has_min_role(admin, "owner")
    assert user_has_min_role(admin, "worker")
    assert user_has_min_role(admin, "admin")
    assert user_has_min_role(manager, "worker")
    assert user_has_min_role(manager, "manager")
    assert not user_has_min_role(manager, "admin")
    assert user_has_min_role(worker, "worker")
    assert not user_has_min_role(worker, "manager")
    assert not user_has_min_role(worker, "admin")


@pytest.mark.asyncio
async def test_require_role_rejects_insufficient():
    dep = require_role("admin")
    worker = AuthUser(sub="1", email="", name="", roles=("worker",))

    with pytest.raises(HTTPException) as exc:
        await dep(user=worker)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_role_allows_sufficient():
    dep = require_role("manager")
    user = AuthUser(sub="1", email="", name="", roles=("admin",))
    result = await dep(user=user)
    assert result.sub == "1"


def test_auth_disabled_by_default_in_dev():
    assert auth_is_active() is False
