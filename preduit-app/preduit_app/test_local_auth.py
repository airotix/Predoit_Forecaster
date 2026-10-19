"""Unit tests for local password hashing + session JWTs."""

from preduit_app import local_auth


def test_password_hash_and_verify():
    stored = local_auth.hash_password("s3cret-password")
    assert stored.startswith("pbkdf2_sha256$")
    assert local_auth.verify_password("s3cret-password", stored) is True
    assert local_auth.verify_password("wrong", stored) is False
    # malformed stored hash never raises, just fails
    assert local_auth.verify_password("x", "garbage") is False


def test_token_roundtrip():
    user = {"id": 7, "email": "a@b.com", "name": "Al", "role": "manager"}
    token = local_auth.issue_token(user)
    assert local_auth.is_local_token(token) is True

    authed = local_auth.validate_local_token(token)
    assert authed.email == "a@b.com"
    assert authed.roles == ("manager",)
    assert authed.primary_role == "manager"


def test_is_local_token_rejects_garbage():
    assert local_auth.is_local_token("not.a.jwt") is False
