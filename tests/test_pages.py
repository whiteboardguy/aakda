"""LLM AUTO-GENERATED TEST
test_pages.py — Tests for page-render routes (/, /login, /register, /500, /c/{conv_id}).
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_cookies, make_conversation, make_user


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------


def test_login_page(client: TestClient):
    r = client.get("/login")
    assert r.status_code == 200


def test_register_page(client: TestClient):
    r = client.get("/register")
    assert r.status_code == 200


def test_500_page(client: TestClient):
    r = client.get("/500")
    assert r.status_code == 500


# ---------------------------------------------------------------------------
# Root — redirects when unauthenticated
# ---------------------------------------------------------------------------


def test_root_unauthenticated_redirects(client: TestClient):
    r = client.get("/")
    assert r.status_code == 302
    assert r.headers["location"] == "/login"


def test_root_authenticated(client: TestClient):
    make_user()
    auth_cookies(client)
    r = client.get("/")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# /c/{conv_id}
# ---------------------------------------------------------------------------


def test_conv_page_unauthenticated_redirects(client: TestClient):
    r = client.get(f"/c/{uuid.uuid4()}")
    assert r.status_code == 302
    assert r.headers["location"] == "/login"


def test_conv_page_own_conversation(client: TestClient):
    user = make_user()
    conv = make_conversation(user)
    auth_cookies(client)
    r = client.get(f"/c/{conv.uid}")
    assert r.status_code == 200


def test_conv_page_nonexistent_conversation(client: TestClient):
    make_user()
    auth_cookies(client)
    r = client.get(f"/c/{uuid.uuid4()}", follow_redirects=True)
    assert r.status_code == 404


def test_conv_page_other_users_conversation(client: TestClient):
    """A user cannot access another user's conversation."""
    owner = make_user(username="owner", email="owner@example.com")
    make_user(username="other", email="other@example.com")
    conv = make_conversation(owner)
    # Log in as 'other'
    auth_cookies(client, username="other", password="password123")
    r = client.get(f"/c/{conv.uid}", follow_redirects=True)
    assert r.status_code == 404
