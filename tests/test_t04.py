"""T04: the Recap status machine, sanitized Markdown and Preview.

Seam: the HTTP app, through TestClient. Routes under test:

    POST /admin/recaps/{id}/submit | send-back | publish | unpublish
    POST /admin/recaps/{id}/preview   (an existing Recap's editor)
    POST /admin/recaps/preview        (the New Recap editor)

Preview re-renders the editor with the sanitized Body inside <section id="preview">.
"""
import re

import pytest

from app import db, recaps
from tests.test_t03 import (BODY, RECAPS, make_recap, make_trip, post,
                            recap_form, recap_row, second_editor)

LIVE_NOTICE = "still live until you Deploy"
REFUSED = (400, 403, 409)


# ---- helpers --------------------------------------------------------------

def editors_recap(client_as, status="draft"):
    """An Editor's Recap, moved to `status` through the real routes.
    Returns (recap_id, trip_id)."""
    trip_id = make_trip(client_as("admin"))
    recap_id = make_recap(client_as("editor"), trip_id)
    if status in ("submitted", "published"):
        assert post(client_as("editor"), f"{RECAPS}/{recap_id}/submit"
                    ).status_code == 303
    if status == "published":
        assert post(client_as("admin"), f"{RECAPS}/{recap_id}/publish"
                    ).status_code == 303
    assert recap_row(recap_id)["status"] == status
    return recap_id, trip_id


def action_forms(html):
    """{form action: form html} for every <form> on the page."""
    return {m.group(1): m.group(0) for m in re.finditer(
        r'<form[^>]*action="([^"]+)"[^>]*>.*?</form>', html, re.S)}


def preview_region(html):
    match = re.search(r'<section id="preview">(.*?)</section>', html, re.S)
    assert match, "page has no <section id=\"preview\">"
    return match.group(1)


# ---- the status machine: allowed transitions ------------------------------

@pytest.mark.parametrize("actor,start,action,end", [
    ("editor", "draft", "submit", "submitted"),
    ("admin", "submitted", "send-back", "draft"),
    ("admin", "draft", "publish", "published"),
    ("admin", "submitted", "publish", "published"),
    ("admin", "published", "unpublish", "draft"),
])
def test_allowed_transitions_move_the_status(client_as, actor, start, action,
                                              end):
    recap_id, _ = editors_recap(client_as, start)
    r = post(client_as(actor), f"{RECAPS}/{recap_id}/{action}")
    assert r.status_code == 303
    assert recap_row(recap_id)["status"] == end


# ---- the status machine: transitions not in the table ---------------------

@pytest.mark.parametrize("actor,start,action", [
    ("editor", "submitted", "submit"),
    ("editor", "published", "submit"),
    # Only the Editor who Owns a Draft Submits it; the table has no Admin row.
    ("admin", "draft", "submit"),
    ("admin", "submitted", "submit"),
    ("admin", "published", "submit"),
    ("admin", "draft", "send-back"),
    ("admin", "published", "send-back"),
    ("admin", "published", "publish"),
    ("admin", "draft", "unpublish"),
    ("admin", "submitted", "unpublish"),
])
def test_transitions_not_in_the_table_are_refused(client_as, actor, start,
                                                  action):
    recap_id, _ = editors_recap(client_as, start)
    before = tuple(recap_row(recap_id))
    r = post(client_as(actor), f"{RECAPS}/{recap_id}/{action}")
    assert r.status_code in REFUSED
    assert tuple(recap_row(recap_id)) == before


# ---- who may do what ------------------------------------------------------

@pytest.mark.parametrize("start,action", [
    ("draft", "publish"),
    ("submitted", "publish"),
    ("submitted", "send-back"),
    ("published", "unpublish"),
])
def test_an_editor_cannot_publish_unpublish_or_send_back(client_as, start,
                                                         action):
    recap_id, _ = editors_recap(client_as, start)
    before = tuple(recap_row(recap_id))
    r = post(client_as("editor"), f"{RECAPS}/{recap_id}/{action}")
    assert r.status_code in REFUSED
    assert tuple(recap_row(recap_id)) == before


def test_an_editor_cannot_submit_another_persons_recap(client_as):
    admin = client_as("admin")
    trip_id = make_trip(admin)
    admins_entry = make_recap(admin, trip_id)
    editors = make_recap(client_as("editor"), trip_id, title="Mine", slug="mine")

    other = second_editor()
    for recap_id in (admins_entry, editors):
        before = tuple(recap_row(recap_id))
        assert post(other, f"{RECAPS}/{recap_id}/submit").status_code == 403
        assert tuple(recap_row(recap_id)) == before
    assert post(client_as("editor"), f"{RECAPS}/{admins_entry}/submit"
                ).status_code == 403
    assert recap_row(admins_entry)["status"] == "draft"


@pytest.mark.parametrize("status", ["submitted", "published"])
def test_an_editor_cannot_edit_or_delete_their_recap_once_it_is_locked(
        client_as, status):
    recap_id, trip_id = editors_recap(client_as, status)
    editor = client_as("editor")
    before = tuple(recap_row(recap_id))

    assert post(editor, f"{RECAPS}/{recap_id}",
                **recap_form(trip_id, title="Sneaky", body="Sneaky edit.")
                ).status_code == 403
    assert post(editor, f"{RECAPS}/{recap_id}/delete").status_code == 403
    assert tuple(recap_row(recap_id)) == before


def lock_behind_the_routes_back(client_as, monkeypatch, status):
    """A Draft the Editor's request already read (and so passed the policy on),
    then moved to `status` before that request writes. Returns the ids and the
    row as it stood afterwards."""
    recap_id, trip_id = editors_recap(client_as)
    stale = recaps.get_recap(recap_id)           # what the request saw: a Draft
    assert post(client_as("editor"), f"{RECAPS}/{recap_id}/submit"
                ).status_code == 303
    if status == "published":
        assert post(client_as("admin"), f"{RECAPS}/{recap_id}/publish"
                    ).status_code == 303
    assert recap_row(recap_id)["status"] == status
    monkeypatch.setattr(recaps, "get_recap", lambda _id: stale)
    return recap_id, trip_id, tuple(recap_row(recap_id))


@pytest.mark.parametrize("status", ["submitted", "published"])
def test_an_editor_save_landing_after_the_recap_locked_is_refused(
        client_as, monkeypatch, status):
    recap_id, trip_id, before = lock_behind_the_routes_back(
        client_as, monkeypatch, status)
    r = post(client_as("editor"), f"{RECAPS}/{recap_id}",
             **recap_form(trip_id, title="Late", body="Late edit."))
    assert r.status_code in REFUSED
    assert tuple(recap_row(recap_id)) == before


@pytest.mark.parametrize("status", ["submitted", "published"])
def test_an_editor_delete_landing_after_the_recap_locked_is_refused(
        client_as, monkeypatch, status):
    recap_id, _, before = lock_behind_the_routes_back(
        client_as, monkeypatch, status)
    r = post(client_as("editor"), f"{RECAPS}/{recap_id}/delete")
    assert r.status_code in REFUSED
    assert tuple(recap_row(recap_id)) == before


def test_sending_back_gives_the_editor_their_recap_again(client_as):
    recap_id, trip_id = editors_recap(client_as, "submitted")
    post(client_as("admin"), f"{RECAPS}/{recap_id}/send-back")
    r = post(client_as("editor"), f"{RECAPS}/{recap_id}",
             **recap_form(trip_id, body="Revised."))
    assert r.status_code == 303
    assert recap_row(recap_id)["body"] == "Revised."


# ---- Submit needs a Body; Publish records a time --------------------------

@pytest.mark.parametrize("body", ["", "  \n\t "])
def test_submitting_with_an_empty_body_is_refused(client_as, body):
    recap_id, _ = editors_recap(client_as)
    with db.connect() as conn:  # forms refuse empty Bodies, so set one directly
        conn.execute("UPDATE recap SET body = ? WHERE id = ?", (body, recap_id))
    r = post(client_as("editor"), f"{RECAPS}/{recap_id}/submit")
    assert r.status_code in REFUSED
    assert recap_row(recap_id)["status"] == "draft"


def test_publishing_records_the_published_timestamp(client_as):
    recap_id, _ = editors_recap(client_as, "submitted")
    assert recap_row(recap_id)["published_at"] is None
    post(client_as("admin"), f"{RECAPS}/{recap_id}/publish")
    assert recap_row(recap_id)["published_at"]


# ---- the "still live until you Deploy" notice -----------------------------

def follow(c, response):
    assert response.status_code == 303
    return c.get(response.headers["location"])


def test_editing_a_published_recap_shows_the_still_live_notice(client_as):
    recap_id, trip_id = editors_recap(client_as, "published")
    admin = client_as("admin")
    r = post(admin, f"{RECAPS}/{recap_id}",
             **recap_form(trip_id, body="Fixed typo.",
                          byline_name="Jane Doe", byline_class_year="2027"))
    assert LIVE_NOTICE in follow(admin, r).text


def test_unpublishing_shows_the_still_live_notice(client_as):
    recap_id, _ = editors_recap(client_as, "published")
    admin = client_as("admin")
    r = post(admin, f"{RECAPS}/{recap_id}/unpublish")
    assert LIVE_NOTICE in follow(admin, r).text


@pytest.mark.parametrize("start", ["draft", "submitted"])
def test_editing_a_recap_that_is_not_published_shows_no_notice(client_as, start):
    recap_id, trip_id = editors_recap(client_as, start)
    admin = client_as("admin")
    r = post(admin, f"{RECAPS}/{recap_id}",
             **recap_form(trip_id, body="Fixed typo.",
                          byline_name="Jane Doe", byline_class_year="2027"))
    assert LIVE_NOTICE not in follow(admin, r).text


# ---- the editor shows only the buttons the person may use -----------------

def action_names(html, recap_id):
    prefix = f"{RECAPS}/{recap_id}/"
    return {a[len(prefix):] for a in action_forms(html) if a.startswith(prefix)
            and a[len(prefix):] in ("submit", "send-back", "publish",
                                    "unpublish")}


def test_an_editor_sees_only_submit_on_their_draft(client_as):
    recap_id, _ = editors_recap(client_as)
    page = client_as("editor").get(f"{RECAPS}/{recap_id}")
    assert action_names(page.text, recap_id) == {"submit"}


@pytest.mark.parametrize("start,expected", [
    ("draft", {"publish"}),
    ("submitted", {"send-back", "publish"}),
    ("published", {"unpublish"}),
])
def test_an_admin_sees_only_the_actions_that_apply(client_as, start, expected):
    recap_id, _ = editors_recap(client_as, start)
    page = client_as("admin").get(f"{RECAPS}/{recap_id}")
    assert action_names(page.text, recap_id) == expected


@pytest.mark.parametrize("start", ["draft", "submitted", "published"])
def test_every_action_form_carries_a_csrf_token(client_as, start):
    recap_id, _ = editors_recap(client_as, start)
    page = client_as("admin").get(f"{RECAPS}/{recap_id}")
    names = action_names(page.text, recap_id)
    assert names
    for name in names:
        assert 'name="csrf_token"' in action_forms(page.text)[
            f"{RECAPS}/{recap_id}/{name}"]


@pytest.mark.parametrize("start,action,actor", [
    ("draft", "submit", "editor"),
    ("submitted", "send-back", "admin"),
    ("submitted", "publish", "admin"),
    ("published", "unpublish", "admin"),
])
def test_an_action_without_a_csrf_token_is_refused(client_as, start, action,
                                                   actor):
    recap_id, _ = editors_recap(client_as, start)
    c = client_as(actor)
    before = tuple(recap_row(recap_id))
    assert c.post(f"{RECAPS}/{recap_id}/{action}", data={},
                  follow_redirects=False).status_code == 403
    assert c.post(f"{RECAPS}/{recap_id}/{action}",
                  data={"csrf_token": "wrong"},
                  follow_redirects=False).status_code == 403
    assert tuple(recap_row(recap_id)) == before


# ---- sanitized Markdown, through Preview ----------------------------------

HOSTILE = (
    "Hello **bold** and a [relative link](../other-recap/).\n\n"
    "<script>alert('pwned')</script>\n\n"
    '<div onclick="steal()">raw html</div>\n\n'
    "[external link](https://evil.example/page)\n\n"
    "[scheme-relative](//evil.example/page)\n\n"
    "![external image](https://evil.example/pic.png)\n\n"
    "[mail me](mailto:someone@example.test)\n"
)


def preview(c, recap_id, trip_id, body):
    return post(c, f"{RECAPS}/{recap_id}/preview", **recap_form(trip_id, body=body))


def test_preview_removes_script_external_link_and_external_image(client_as):
    recap_id, trip_id = editors_recap(client_as)
    r = preview(client_as("editor"), recap_id, trip_id, HOSTILE)
    assert r.status_code == 200
    html = preview_region(r.text)

    assert "<script" not in html and "pwned" not in html
    assert "onclick" not in html
    assert "evil.example" not in html
    assert "<img" not in html
    assert "external link" in html          # the link text stays as plain text
    assert "scheme-relative" in html


def test_preview_keeps_ordinary_markdown_formatting(client_as):
    recap_id, trip_id = editors_recap(client_as)
    r = preview(client_as("editor"), recap_id, trip_id, HOSTILE)
    html = preview_region(r.text)
    assert "<strong>bold</strong>" in html
    assert 'href="../other-recap/"' in html


def test_mailto_links_are_removed_but_their_text_stays(client_as):
    recap_id, trip_id = editors_recap(client_as)
    r = preview(client_as("editor"), recap_id, trip_id, HOSTILE)
    html = preview_region(r.text)
    assert "mailto" not in html and "someone@example.test" not in html
    assert "mail me" in html


def test_mailto_becomes_plain_text_not_an_anchor(client_as):
    recap_id, trip_id = editors_recap(client_as)
    html = preview_region(preview(client_as("editor"), recap_id, trip_id,
                                  HOSTILE).text)
    assert not re.search(r"<a\b[^>]*>[^<]*mail me", html)


def test_preview_strips_event_handler_attributes_such_as_onerror(client_as):
    body = ('<img src="x" onerror="steal()">\n\n'
            '<p onerror="steal()" onmouseover="steal()">kept paragraph</p>\n')
    recap_id, trip_id = editors_recap(client_as)
    html = preview_region(preview(client_as("editor"), recap_id, trip_id,
                                  body).text)
    assert "onerror" not in html and "onmouseover" not in html
    assert "steal" not in html
    assert "kept paragraph" not in html  # raw HTML is gone, text and all


@pytest.mark.parametrize("body", [
    "[click me](javascript:alert(1))",
    "[click me](JaVaScRiPt:alert(1))",
    '<a href="javascript:alert(1)">click me</a>',
    '<a href=" javascript:alert(1)">click me</a>',
])
def test_javascript_links_never_become_links(client_as, body):
    recap_id, trip_id = editors_recap(client_as)
    html = preview_region(preview(client_as("editor"), recap_id, trip_id,
                                  body).text)
    assert not re.search(r"href\s*=\s*[\"']?\s*javascript", html, re.I)
    assert not re.search(r"<a\b[^>]*>[^<]*click me", html)


def test_preview_does_not_save_the_body(client_as):
    recap_id, trip_id = editors_recap(client_as)
    preview(client_as("editor"), recap_id, trip_id, "A different body.")
    assert recap_row(recap_id)["body"] == BODY


def test_preview_works_on_the_new_recap_editor(client_as):
    trip_id = make_trip(client_as("admin"))
    editor = client_as("editor")
    r = post(editor, f"{RECAPS}/preview", **recap_form(trip_id, body=HOSTILE))
    assert r.status_code == 200
    html = preview_region(r.text)
    assert "<strong>bold</strong>" in html and "<script" not in html


def test_both_editors_have_a_preview_button(client_as):
    recap_id, _ = editors_recap(client_as)
    editor = client_as("editor")
    assert "Preview" in editor.get(f"{RECAPS}/{recap_id}").text
    assert "Preview" in editor.get(f"{RECAPS}/new").text


def test_an_editor_cannot_preview_through_another_persons_recap(client_as):
    admin = client_as("admin")
    trip_id = make_trip(admin)
    admins_entry = make_recap(admin, trip_id)
    r = preview(client_as("editor"), admins_entry, trip_id, "Anything.")
    assert r.status_code == 403
