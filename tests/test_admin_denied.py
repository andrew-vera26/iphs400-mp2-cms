"""A permission refusal shown to a browser is a styled page with a way back;
anything that does not ask for HTML keeps the JSON body; the CSRF refusal is
unchanged."""
import re

import pytest

from tests.conftest import csrf_from
from tests.test_t03 import make_recap, make_trip

HTML = {"Accept": "text/html,application/xhtml+xml"}
MESSAGE = "You don't have permission to do that"


def denied_pages(client_as):
    """(label, response) for each way an Editor is refused, asking for HTML."""
    admin = client_as("admin")
    other = make_recap(admin, make_trip(admin))
    editor = client_as("editor")
    token = csrf_from(editor.get("/admin"))
    return [
        ("admin screen", editor.get("/admin/accounts?x=<script>alert(1)</script>",
                                    headers=HTML)),
        ("someone else's recap", editor.post(
            f"/admin/recaps/{other}/delete", data={"csrf_token": token},
            headers=HTML, follow_redirects=False)),
    ]


def test_a_refusal_for_a_browser_is_a_styled_403_page(client_as):
    for label, r in denied_pages(client_as):
        assert r.status_code == 403, label
        assert r.headers["content-type"].startswith("text/html"), label
        assert MESSAGE in r.text, label
        assert '<link rel="stylesheet" href="/static/admin.css">' in r.text, label
        assert re.search(r'<a href="/admin">[^<]*[Dd]ashboard[^<]*</a>', r.text), label
        assert "Sign out" in r.text, label                  # the admin header
        assert '"detail"' not in r.text, label


def test_the_refusal_page_shows_no_internals_and_escapes_the_request(client_as):
    for label, r in denied_pages(client_as):
        assert r.headers["content-type"].startswith("text/html"), label
        low = r.text.lower()
        for leak in ("traceback", "app/security", "app/routes", ".py",
                     "<script>alert"):
            assert leak not in low, (label, leak)


@pytest.mark.parametrize("headers", [{}, {"Accept": "*/*"},
                                     {"Accept": "application/json"}])
def test_a_refusal_that_does_not_ask_for_html_stays_json(client_as, headers):
    r = client_as("editor").get("/admin/accounts", headers=headers)
    assert r.status_code == 403
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {"detail": "You do not have permission to do that"}


def test_the_csrf_refusal_keeps_its_current_behaviour(client_as):
    c = client_as("editor")
    for headers in ({}, HTML):
        r = c.post("/admin/recaps", data={"csrf_token": "wrong"},
                   headers=headers, follow_redirects=False)
        assert r.status_code == 403
        assert r.headers["content-type"].startswith("application/json")
        assert r.json() == {"detail": "Missing or invalid CSRF token"}


def test_logged_out_visitors_are_still_sent_to_login(client):
    r = client.get("/admin/accounts", headers=HTML, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


@pytest.mark.parametrize("path", ["/admin/trips", "/admin/pages",
                                  "/admin/accounts"])
def test_an_editor_opening_an_admin_list_gets_the_styled_page(client_as, path):
    r = client_as("editor").get(path, headers=HTML)
    assert r.status_code == 403
    assert r.headers["content-type"].startswith("text/html")
    assert MESSAGE in r.text
    assert '<link rel="stylesheet" href="/static/admin.css">' in r.text
    assert '<a href="/admin">' in r.text
