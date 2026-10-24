"""Shared test fixtures.

`client` gives you the app, backed by a temporary database that is seeded with
the demo Admin and Editor Accounts. `client_as(role)` gives you a client that is
logged in as the seeded Account of that role, so access-control tests stay one
line:

    def test_editor_cannot_manage_users(client_as):
        assert client_as("editor").get("/admin/users").status_code in (302, 403)
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app import accounts, db, seed, settings
from app.main import create_app

# The emails come from app.seed, which scripts/seed_demo.py also uses. The real
# script reads passwords from the environment; in tests they are fixed and
# meaningless.
DEMO_USERS = {
    "admin": {"email": seed.ADMIN_EMAIL, "password": "test-admin-pw"},
    "editor": {"email": seed.EDITOR_EMAIL, "password": "test-editor-pw"},
}

TOKEN_FIELD = re.compile(r'name="csrf_token" value="([^"]+)"')


def csrf_from(response) -> str:
    """Pull the hidden CSRF token out of a rendered form."""
    match = TOKEN_FIELD.search(response.text)
    assert match, "page has no csrf_token field"
    return match.group(1)


@pytest.fixture
def database(tmp_path, monkeypatch):
    """A fresh database file, seeded with the demo Accounts."""
    monkeypatch.setattr(settings, "DATABASE_PATH", tmp_path / "test.db")
    db.init_db()
    seed.seed_accounts(DEMO_USERS["admin"]["password"],
                       DEMO_USERS["editor"]["password"])
    return settings.DATABASE_PATH


@pytest.fixture
def client(database) -> TestClient:
    return TestClient(create_app())


def log_in(c: TestClient, email: str, password: str):
    token = csrf_from(c.get("/login"))
    return c.post("/login", data={"email": email, "password": password,
                                  "csrf_token": token},
                  follow_redirects=False)


@pytest.fixture
def client_as(database):
    """Return a factory: client_as("editor") -> a logged-in TestClient."""

    def _login(role: str) -> TestClient:
        user = DEMO_USERS[role]
        c = TestClient(create_app())
        response = log_in(c, user["email"], user["password"])
        assert response.status_code in (200, 302, 303), (
            f"Login as {role} failed with {response.status_code}")
        return c

    return _login
