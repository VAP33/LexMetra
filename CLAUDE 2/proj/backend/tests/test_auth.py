"""
Unit tests for auth.py hashing and JWT logic — no database required.
"""

import pytest

import auth


def test_password_hash_and_verify_roundtrip():
    hashed = auth.hash_password("correct-horse-battery-staple")
    assert auth.verify_password("correct-horse-battery-staple", hashed) is True
    assert auth.verify_password("wrong-password", hashed) is False


def test_password_hash_is_not_plaintext():
    hashed = auth.hash_password("mysecret123")
    assert hashed != "mysecret123"
    assert hashed.startswith("$2")  # bcrypt hash prefix


def test_jwt_roundtrip():
    token = auth.create_access_token("alice", "inspector")
    data = auth.decode_access_token(token)
    assert data.username == "alice"
    assert data.role == "inspector"


def test_jwt_tampered_token_is_rejected():
    token = auth.create_access_token("alice", "inspector")
    tampered = token[:-3] + ("aaa" if token[-3:] != "aaa" else "bbb")
    with pytest.raises(Exception):
        auth.decode_access_token(tampered)


def test_role_hierarchy_orders_correctly():
    assert auth.ROLE_HIERARCHY["inspector"] < auth.ROLE_HIERARCHY["reviewer"]
    assert auth.ROLE_HIERARCHY["reviewer"] < auth.ROLE_HIERARCHY["admin"]
