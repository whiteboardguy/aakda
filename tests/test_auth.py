"""LLM AUTO-GENERATED TEST
test_auth.py — Tests for POST /auth/users/signup, /login, /logout.
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_user


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------


def test_signup_success(client: TestClient):
    r = client.post(
        "/auth/users/signup",
        data={
            "username": "newuser",
            "display_name": "New User",
            "email": "new@example.com",
            "password": "password123",
        },
    )
    assert r.status_code == 200


def test_signup_duplicate_username(client: TestClient):
    make_user(username="dupeuser", email="original@example.com")
    r = client.post(
        "/auth/users/signup",
        data={
            "username": "dupeuser",
            "display_name": "Dupe",
            "email": "other@example.com",
            "password": "password123",
        },
    )
    assert r.status_code == 409


def test_signup_duplicate_email(client: TestClient):
    make_user(username="originaluser", email="dupe@example.com")
    r = client.post(
        "/auth/users/signup",
        data={
            "username": "differentuser",
            "display_name": "Dupe Email",
            "email": "dupe@example.com",
            "password": "password123",
        },
    )
    assert r.status_code == 409


def test_signup_missing_field(client: TestClient):
    # Missing password — should fail validation (422)
    r = client.post(
        "/auth/users/signup",
        data={
            "username": "nopassword",
            "display_name": "No Pass",
            "email": "nopass@example.com",
        },
    )
    assert r.status_code == 422


def test_signup_password_too_short(client: TestClient):
    r = client.post(
        "/auth/users/signup",
        data={
            "username": "shortpw",
            "display_name": "Short PW",
            "email": "short@example.com",
            "password": "abc",  # min_length=8
        },
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


def test_login_success(client: TestClient):
    make_user(username="loginuser", email="login@example.com", password="password123")
    r = client.post(
        "/auth/users/login",
        data={"username": "loginuser", "password": "password123"},
    )
    assert r.status_code == 200
    # A session cookie must be set on the client after login
    assert len(client.cookies) > 0


def test_login_wrong_password(client: TestClient):
    make_user(username="wrongpw", email="wrongpw@example.com", password="correctpass")
    r = client.post(
        "/auth/users/login",
        data={"username": "wrongpw", "password": "wrongpass"},
    )
    assert r.status_code == 401


def test_login_nonexistent_user(client: TestClient):
    r = client.post(
        "/auth/users/login",
        data={"username": "nobody", "password": "whatever"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


def test_logout(client: TestClient):
    make_user()
    client.post(
        "/auth/users/login",
        data={"username": "testuser", "password": "password123"},
    )
    r = client.post("/auth/users/logout")
    assert r.status_code == 200
