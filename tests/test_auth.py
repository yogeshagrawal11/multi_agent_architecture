# Author: Yogesh Agrawal
"""Tests for JWT auth and password hashing."""
from fastapi.testclient import TestClient


def _client():
    import app.main as m
    return TestClient(m.app)


def test_password_roundtrip():
    from app.auth.passwords import hash_password, verify_password
    h = hash_password("password123")
    assert verify_password("password123", h)
    assert not verify_password("wrong", h)


def test_login_success_returns_jwt():
    r = _client().post("/auth/login", json={"username": "john", "password": "password123"})
    assert r.status_code == 200
    body = r.json()
    assert body["customer_id"] == "C1"
    assert body["role"] == "privileged"
    assert body["access_token"]


def test_login_wrong_password():
    r = _client().post("/auth/login", json={"username": "john", "password": "nope"})
    assert r.status_code == 401


def test_login_unknown_user():
    r = _client().post("/auth/login", json={"username": "ghost", "password": "x"})
    assert r.status_code == 401


def test_chat_requires_auth():
    r = _client().post("/api/chat", json={"message": "hi"})
    assert r.status_code == 403  # no bearer token


def test_token_identity_roundtrip():
    from app.auth.jwt_auth import _issue_token, get_current_identity
    from fastapi.security import HTTPAuthorizationCredentials
    tok = _issue_token("john", "C1", "privileged")
    ident = get_current_identity(HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok))
    assert ident.customer_id == "C1"
    assert ident.role == "privileged"
