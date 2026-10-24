"""T01: log in, sign out, CSRF and the permission policy."""
import logging

import pytest

from app import accounts, db
from tests.conftest import DEMO_USERS, csrf_from, log_in

GENERIC = "email or password is incorrect"

# Every Admin-only route and action, as (method, path). Each later ticket adds
# its own rows; an Editor must get a 403 (or a redirect) on all of them.
ADMIN_ONLY_ROUTES: list[tuple[str, str]] = [
    # T02: Account management
    ("GET", "/admin/accounts"),
    ("GET", "/admin/accounts/new"),
    ("POST", "/admin/accounts"),
    ("POST", "/admin/accounts/1/role"),
    ("POST", "/admin/accounts/1/deactivate"),
    ("POST", "/admin/accounts/1/password"),
    # T03: Trips
    ("GET", "/admin/trips"),
    ("GET", "/admin/trips/new"),
    ("GET", "/admin/trips/1"),
    ("POST", "/admin/trips"),
    ("POST", "/admin/trips/1"),
    ("POST", "/admin/trips/1/delete"),
    # T04: Recap status machine
    ("POST", "/admin/recaps/1/publish"),
    ("POST", "/admin/recaps/1/unpublish"),
    ("POST", "/admin/recaps/1/send-back"),
    # T07: Pages
    ("GET", "/admin/pages"),
    ("GET", "/admin/pages/new"),
    ("GET", "/admin/pages/1"),
    ("POST", "/admin/pages"),
    ("POST", "/admin/pages/1"),
    ("POST", "/admin/pages/1/delete"),
    ("POST", "/admin/pages/1/publish"),
    ("POST", "/admin/pages/1/unpublish"),
    ("POST", "/admin/pages/preview"),
    ("POST", "/admin/pages/1/preview"),
    # T09: a Recap the Editor doesn't Own ({other} is a real Admin-owned Draft)
    ("POST", "/admin/recaps/{other}"),
    ("POST", "/admin/recaps/{other}/submit"),
    ("POST", "/admin/recaps/{other}/delete"),
]


@pytest.mark.parametrize("method,path", ADMIN_ONLY_ROUTES)
def test_editor_on_admin_only_routes(client_as, method, path):
    from tests.test_t03 import make_recap, make_trip, recap_form, recap_row
    admin = client_as("admin")
    trip_id = make_trip(admin)
    other = make_recap(admin, trip_id)
    before = dict(recap_row(other))

    c = client_as("editor")
    token = csrf_from(c.get("/admin"))
    form = recap_form(trip_id, title="Editor rewrite", slug="editor-rewrite")
    r = c.request(method, path.format(other=other),
                  data={"csrf_token": token, **form}, follow_redirects=False)

    # logged in but not allowed is a 403, never a redirect to a success page
    assert r.status_code == 403
    assert dict(recap_row(other)) == before


# ---- login / logout -------------------------------------------------------

@pytest.mark.parametrize("role", ["admin", "editor"])
def test_seeded_accounts_can_log_in(client_as, role):
    assert "<h1>Dashboard</h1>" in client_as(role).get("/admin").text


def test_wrong_password_and_unknown_email_look_identical(client):
    def attempt(email, password):
        r = log_in(client, email, password)
        assert r.status_code == 401
        return r.text

    wrong_pw = attempt(DEMO_USERS["admin"]["email"], "nope")
    unknown = attempt("nobody@example.test", "nope")
    assert GENERIC in wrong_pw.lower()
    assert GENERIC in unknown.lower()
    # a failed login must not log anyone in
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_password_is_stored_as_argon2_and_never_logged(client, caplog):
    with caplog.at_level(logging.DEBUG):
        log_in(client, DEMO_USERS["admin"]["email"], "wrong-password-xyz")
        log_in(client, DEMO_USERS["admin"]["email"],
               DEMO_USERS["admin"]["password"])
    with db.connect() as conn:
        stored = conn.execute("SELECT password_hash FROM account").fetchall()
    assert stored and all(r["password_hash"].startswith("$argon2") for r in stored)
    assert all(DEMO_USERS[k]["password"] not in r["password_hash"]
               for r in stored for k in DEMO_USERS)
    assert "wrong-password-xyz" not in caplog.text
    assert DEMO_USERS["admin"]["password"] not in caplog.text


def test_sign_out_ends_the_session(client_as):
    c = client_as("admin")
    token = csrf_from(c.get("/admin"))
    r = c.post("/logout", data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303
    after = c.get("/admin", follow_redirects=False)
    assert after.status_code == 303 and after.headers["location"] == "/login"


@pytest.mark.parametrize("path", ["/admin"])
def test_anonymous_console_requests_redirect_to_login(client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/login"


# ---- CSRF -----------------------------------------------------------------

def test_login_and_logout_forms_carry_a_token(client, client_as):
    assert 'name="csrf_token"' in client.get("/login").text
    assert 'name="csrf_token"' in client_as("admin").get("/admin").text


def test_post_without_or_with_wrong_token_is_403(client, client_as):
    creds = {"email": DEMO_USERS["admin"]["email"],
             "password": DEMO_USERS["admin"]["password"]}
    client.get("/login")
    assert client.post("/login", data=creds).status_code == 403
    assert client.post("/login", data={**creds, "csrf_token": "bad"}
                       ).status_code == 403
    c = client_as("admin")
    assert c.post("/logout", data={}).status_code == 403
    assert c.post("/logout", data={"csrf_token": "bad"}).status_code == 403
    assert c.get("/admin").status_code == 200  # still signed in


# ---- policy rereads the Account on every request --------------------------

def test_deactivation_takes_effect_at_once(client_as):
    c = client_as("editor")
    assert c.get("/admin").status_code == 200
    with db.connect() as conn:
        conn.execute("UPDATE account SET active = 0 WHERE role = 'editor'")
    r = c.get("/admin", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


# ---- review follow-ups ----------------------------------------------------

def test_seeding_twice_does_not_duplicate_accounts(database):
    from app import seed
    seed.seed_accounts("another-admin-pw", "another-editor-pw")
    seed.seed_accounts("another-admin-pw", "another-editor-pw")
    with db.connect() as conn:
        emails = [r["email"] for r in conn.execute("SELECT email FROM account")]
    assert sorted(emails) == sorted([DEMO_USERS["admin"]["email"],
                                     DEMO_USERS["editor"]["email"]])


def test_anonymous_requests_are_redirected_on_every_guarded_route(database):
    """The guard works on any route that uses it, not just /admin."""
    from fastapi import Depends
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.security import require

    app = create_app()
    for name in ("one", "two"):
        app.get(f"/admin/probe-{name}", dependencies=[Depends(require("console.view"))])(
            lambda: "ok")
    c = TestClient(app)
    for path in ("/admin", "/admin/probe-one", "/admin/probe-two"):
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login", path


@pytest.mark.parametrize("path", ["/login", "/logout"])
def test_anonymous_post_without_a_token_is_refused(client, path):
    # fresh client: no session cookie at all, so there is no token to match
    r = client.post(path, data={"email": DEMO_USERS["admin"]["email"],
                                "password": DEMO_USERS["admin"]["password"]},
                    follow_redirects=False)
    assert r.status_code == 403
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_default_secret_key_logs_a_warning(database, monkeypatch, caplog):
    from app import settings
    from app.main import create_app
    monkeypatch.setattr(settings, "SECRET_KEY_IS_DEV_DEFAULT", True)
    with caplog.at_level(logging.WARNING):
        create_app()
    assert "CMS_SECRET_KEY is not set" in caplog.text
