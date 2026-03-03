"""LLM AUTO-GENERATED TEST
test_users.py — Tests for GET /users/fetch/display.
"""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import auth_cookies, make_user


def test_fetch_display_name_authenticated(client: TestClient):
    make_user(display_name="Alice Smith")
    auth_cookies(client)
    r = client.get("/users/fetch/display")
    assert r.status_code == 200
    assert "Alice Smith" in r.text


def test_fetch_display_name_unauthenticated(client: TestClient):
    r = client.get("/users/fetch/display")
    # require_auth returns a RedirectResponse for non-HX requests
    assert r.status_code in (302, 401)


def test_fetch_display_name_htmx_unauthenticated(client: TestClient):
    r = client.get("/users/fetch/display", headers={"HX-Request": "true"})
    assert r.status_code == 401
