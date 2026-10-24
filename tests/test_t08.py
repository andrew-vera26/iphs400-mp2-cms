"""T08: Dashboard and content list.

Seams: the HTTP app (TestClient). Data is set up with the app's own write
functions and routes; the pages are read back as a console user sees them.

    GET /admin                                       the dashboard
    GET /admin/recaps[?status=&trip=&owner=]         the Recaps list

Markup contract the tests read (the ticket leaves it open):

* Each dashboard count is an element carrying `data-count="<key>"` whose text is
  the number. Admin keys: recaps-draft, recaps-submitted, recaps-published,
  trips, pages-draft, pages-published, accounts-active. An Editor's dashboard
  has the three recaps-* keys only.
* The "changes not yet live" notice is the phrase "changes not yet live" on the
  Admin dashboard, and appears nowhere else on it.
* The list has one `<a href="/admin/recaps/{id}">` per row, in display order.
  An Admin's filter form has fields named status, trip and owner; an Editor's
  has status and trip only.
* A malformed filter value (status not draft/submitted/published, trip or owner
  not a whole number) is refused with 400 and is never echoed into the page. A
  well-formed trip or owner that matches nothing gives an empty list. An
  Editor's `owner` is ignored: they only ever see their own Recaps.
"""
import re
import time

import pytest

from app import accounts, cli, db, pages, recaps, seed, settings, site_state, trips
from tests.conftest import csrf_from
from tests.test_t03 import BOSTON, CHICAGO, account_id, count, post, recap_form
from tests.test_t06 import PNG, image_rows, upload
from tests.test_t07 import page_form

RECAPS = "/admin/recaps"
LONG_AGO = "2000-01-01T00:00:00Z"
BEFORE_THAT = "1999-12-31T00:00:00Z"
NOTICE = "changes not yet live"


# ---- helpers --------------------------------------------------------------

def counts(html):
    return {k: int(n) for k, n in
            re.findall(r'data-count="([a-z-]+)"[^>]*>\s*(\d+)\s*<', html)}


def listed(c, **params):
    """Recap ids on the list page, in display order."""
    r = c.get(RECAPS, params=params)
    assert r.status_code == 200, r.text
    return [int(i) for i in re.findall(r'href="/admin/recaps/(\d+)"', r.text)]


def make(owner_id, trip_id, slug, status="draft", title=None):
    recap_id = recaps.create_recap(trip_id, owner_id, title or f"Title {slug}",
                                   slug, "A short anecdote.", "Jane Doe", 2027)
    if status in ("submitted", "published"):
        recaps.transition(recap_id, "submit")
    if status == "published":
        recaps.transition(recap_id, "publish")
    return recap_id


class World:
    """Two Editors, two Trips, seven Recaps, three Pages, one Deactivated
    Account. Admin sees: draft 2, submitted 3, published 2, trips 2, pages
    draft 2 / published 1, active accounts 3 (Admin, two Editors)."""


@pytest.fixture
def world(database):
    w = World()
    w.admin = account_id(seed.ADMIN_EMAIL)
    w.e1 = account_id(seed.EDITOR_EMAIL)
    w.e2 = accounts.create_account("other.editor@example.test", "Other Editor",
                                   2027, "editor", "other-editor-pw")
    gone = accounts.create_account("gone@example.test", "Gone Member", 2025,
                                   "editor", "gone-pw")
    accounts.deactivate(gone)
    w.chicago = trips.create_trip(dict(CHICAGO))
    w.boston = trips.create_trip(dict(BOSTON))
    w.r1 = make(w.e1, w.chicago, "r1", "draft")
    w.r2 = make(w.e1, w.chicago, "r2", "submitted")
    w.r3 = make(w.e1, w.boston, "r3", "published")
    w.r4 = make(w.e2, w.chicago, "r4", "draft")
    w.r5 = make(w.e2, w.boston, "r5", "submitted")
    w.r6 = make(w.e2, w.boston, "r6", "submitted")
    w.r7 = make(w.admin, w.boston, "r7", "published")
    w.mine = {w.r1, w.r2, w.r3}
    w.everything = w.mine | {w.r4, w.r5, w.r6, w.r7}
    w.submitted = {w.r2, w.r5, w.r6}
    for slug, nav in (("about", 1), ("officers", 2), ("history", 3)):
        pages.create_page(w.admin, slug.title(), slug, "Text.", nav)
    pages.transition(1, "publish")
    return w


@pytest.fixture
def admin(client_as, world):
    return client_as("admin")


@pytest.fixture
def editor(client_as, world):
    return client_as("editor")


@pytest.fixture
def other_editor(world):
    from tests.test_t03 import second_editor
    return second_editor()


def pin_site_state(render_at):
    with db.connect() as conn:
        conn.execute("INSERT INTO site_state (id, last_rendered_at) VALUES "
                     "(1, ?) ON CONFLICT (id) DO UPDATE SET "
                     "last_rendered_at = excluded.last_rendered_at",
                     (render_at,))


def settle():
    """The world as it is right after `cms publish`: every row last touched
    before the render, pinned far in the past so no test depends on the clock."""
    with db.connect() as conn:
        for table in ("trip", "recap", "page"):
            conn.execute(f"UPDATE {table} SET created_at = ?, edited_at = ?",
                         (BEFORE_THAT, BEFORE_THAT))
        conn.execute("UPDATE recap SET published_at = ? "
                     "WHERE published_at IS NOT NULL", (BEFORE_THAT,))
    pin_site_state(LONG_AGO)


def stamp_recap(recap_id, edited_at):
    with db.connect() as conn:
        conn.execute("UPDATE recap SET edited_at = ? WHERE id = ?",
                     (edited_at, recap_id))


# ---- anonymous ------------------------------------------------------------

@pytest.mark.parametrize("path", ["/admin", RECAPS])
def test_anonymous_requests_redirect_to_login(client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


# ---- dashboard counts -----------------------------------------------------

def test_admin_dashboard_counts_match_the_data(admin):
    assert counts(admin.get("/admin").text) == {
        "recaps-draft": 2, "recaps-submitted": 3, "recaps-published": 2,
        "trips": 2, "pages-draft": 2, "pages-published": 1,
        "accounts-active": 3}


def test_deactivating_an_account_lowers_the_active_count(admin, world):
    accounts.deactivate(world.e2)
    assert counts(admin.get("/admin").text)["accounts-active"] == 2


def test_editor_dashboard_counts_only_their_own_recaps(editor, world):
    assert counts(editor.get("/admin").text) == {
        "recaps-draft": 1, "recaps-submitted": 1, "recaps-published": 1}


def test_editor_dashboard_does_not_move_when_others_recaps_change(
        editor, world):
    before = counts(editor.get("/admin").text)
    make(world.e2, world.chicago, "another", "published")
    make(world.admin, world.chicago, "admin-draft", "draft")
    assert counts(editor.get("/admin").text) == before


def test_other_editor_sees_their_own_numbers(other_editor):
    assert counts(other_editor.get("/admin").text) == {
        "recaps-draft": 1, "recaps-submitted": 2, "recaps-published": 0}


# ---- "changes not yet live" notice ----------------------------------------

def test_notice_shows_when_the_site_has_never_been_rendered(admin):
    assert site_state.last_rendered() is None
    assert NOTICE in admin.get("/admin").text.lower()


def test_notice_is_absent_right_after_a_render(admin):
    settle()
    assert NOTICE not in admin.get("/admin").text.lower()


@pytest.mark.parametrize("change", [
    pytest.param(lambda a, w: post(a, "/admin/trips/%d" % w.chicago, **{
        **CHICAGO, "summary": "Changed summary."}), id="edit-trip"),
    pytest.param(lambda a, w: post(a, "/admin/trips", **{
        **BOSTON, "slug": "2026-new", "city": "Newtown"}), id="create-trip"),
    pytest.param(lambda a, w: post(a, "%s/%d" % (RECAPS, w.r1), **recap_form(
        w.chicago, body="Edited.", byline_name="Jane Doe",
        byline_class_year="2027")), id="edit-recap"),
    pytest.param(lambda a, w: post(a, "%s/%d/publish" % (RECAPS, w.r2)),
                 id="publish-recap"),
    pytest.param(lambda a, w: post(a, "%s/%d/unpublish" % (RECAPS, w.r3)),
                 id="unpublish-recap"),
    pytest.param(lambda a, w: post(a, "/admin/pages/1", **page_form(
        body="Edited page.")), id="edit-page"),
    pytest.param(lambda a, w: post(a, "/admin/pages/2/publish"),
                 id="publish-page"),
    pytest.param(lambda a, w: post(a, "/admin/pages/1/unpublish"),
                 id="unpublish-page"),
    pytest.param(lambda a, w: post(a, "%s/%d/delete" % (RECAPS, w.r3)),
                 id="delete-published-recap"),
])
def test_notice_appears_after_any_content_change(admin, world, change):
    settle()
    assert NOTICE not in admin.get("/admin").text.lower()
    r = change(admin, world)
    assert r.status_code == 303, r.text
    assert NOTICE in admin.get("/admin").text.lower()


def test_notice_cycle_with_the_real_cms_publish(admin, world, tmp_path,
                                                monkeypatch):
    monkeypatch.setattr(settings, "SITE", tmp_path / "site")
    assert NOTICE in admin.get("/admin").text.lower()

    assert cli.main(["publish"]) == 0
    assert NOTICE not in admin.get("/admin").text.lower()

    time.sleep(1.1)  # the stamps have one-second precision
    post(admin, "/admin/pages/1", **page_form(body="Edited after the render."))
    assert NOTICE in admin.get("/admin").text.lower()

    assert cli.main(["publish"]) == 0
    assert NOTICE not in admin.get("/admin").text.lower()


def test_edit_in_the_same_second_as_the_render_is_not_a_change(admin, world):
    settle()
    stamp_recap(world.r1, LONG_AGO)
    assert NOTICE not in admin.get("/admin").text.lower()


def test_edit_one_second_after_the_render_is_a_change(admin, world):
    settle()
    stamp_recap(world.r1, "2000-01-01T00:00:01Z")
    assert NOTICE in admin.get("/admin").text.lower()


def test_edit_one_second_before_the_render_is_not_a_change(admin, world):
    settle()
    stamp_recap(world.r1, "1999-12-31T23:59:59Z")
    assert NOTICE not in admin.get("/admin").text.lower()


def test_editors_never_see_the_notice(editor, world):
    assert site_state.last_rendered() is None
    assert NOTICE not in editor.get("/admin").text.lower()


# ---- Admin list: contents, filters, order ----------------------------------

def test_admin_list_shows_every_recap(admin, world):
    assert set(listed(admin)) == world.everything
    assert len(listed(admin)) == 7


@pytest.mark.parametrize("status, expected", [
    ("draft", {"r1", "r4"}),
    ("submitted", {"r2", "r5", "r6"}),
    ("published", {"r3", "r7"}),
])
def test_admin_filters_by_status(admin, world, status, expected):
    assert set(listed(admin, status=status)) == {
        getattr(world, n) for n in expected}


def test_admin_filters_by_trip(admin, world):
    assert set(listed(admin, trip=world.chicago)) == {
        world.r1, world.r2, world.r4}
    assert set(listed(admin, trip=world.boston)) == {
        world.r3, world.r5, world.r6, world.r7}


def test_admin_filters_by_owner(admin, world):
    assert set(listed(admin, owner=world.e1)) == world.mine
    assert set(listed(admin, owner=world.e2)) == {world.r4, world.r5, world.r6}
    assert set(listed(admin, owner=world.admin)) == {world.r7}


def test_admin_filters_combine(admin, world):
    assert set(listed(admin, status="submitted", trip=world.boston)) == {
        world.r5, world.r6}
    assert set(listed(admin, status="submitted", owner=world.e2)) == {
        world.r5, world.r6}
    assert set(listed(admin, trip=world.chicago, owner=world.e1)) == {
        world.r1, world.r2}
    assert listed(admin, status="published", trip=world.boston,
                  owner=world.e1) == [world.r3]
    assert listed(admin, status="draft", trip=world.boston,
                  owner=world.e1) == []


def test_empty_filter_values_mean_no_filter(admin, world):
    assert set(listed(admin, status="", trip="", owner="")) == world.everything


def test_submitted_recaps_come_first_for_an_admin(admin, world):
    ids = listed(admin)
    assert set(ids[:3]) == world.submitted
    assert set(ids[3:]) == world.everything - world.submitted


def test_submitted_first_holds_when_only_trip_is_filtered(admin, world):
    ids = listed(admin, trip=world.boston)
    assert set(ids[:2]) == {world.r5, world.r6}


def test_admin_filter_form_has_status_trip_and_owner(admin):
    html = admin.get(RECAPS).text
    for name in ("status", "trip", "owner"):
        assert f'name="{name}"' in html


# ---- Editor list: own Recaps only ------------------------------------------

def test_editor_list_contains_only_their_own_recaps(editor, world):
    assert set(listed(editor)) == world.mine
    assert len(listed(editor)) == 3


def test_editor_filters_by_status_and_trip(editor, world):
    assert listed(editor, status="draft") == [world.r1]
    assert listed(editor, status="published") == [world.r3]
    assert set(listed(editor, trip=world.chicago)) == {world.r1, world.r2}
    assert listed(editor, status="submitted", trip=world.chicago) == [world.r2]
    assert listed(editor, status="draft", trip=world.boston) == []


@pytest.mark.parametrize("who", ["e2", "admin", "e1"])
def test_editor_owner_filter_cannot_reveal_anyone_elses_recaps(
        editor, world, who):
    assert set(listed(editor, owner=getattr(world, who))) == world.mine


def test_editor_owner_filter_cannot_widen_other_filters(editor, world):
    assert listed(editor, owner=world.e2, status="draft") == [world.r1]
    assert listed(editor, owner=world.e2, trip=world.boston) == [world.r3]


def test_editor_list_shows_no_owner_filter_and_no_other_editors_titles(
        editor, world):
    html = editor.get(RECAPS).text
    assert 'name="owner"' not in html
    assert 'name="status"' in html and 'name="trip"' in html
    for slug in ("r4", "r5", "r6", "r7"):
        assert f"Title {slug}" not in html
    assert "Other Editor" not in html


def test_other_editors_list_is_theirs_alone(other_editor, world):
    assert set(listed(other_editor)) == {world.r4, world.r5, world.r6}


# ---- filter values are validated, never trusted ----------------------------

HOSTILE_VALUES = [
    "bogus", "' OR '1'='1", "draft' OR '1'='1", "draft; DROP TABLE recap;--",
    "<script>alert(1)</script>", "DRAFT", "draft ", "1 OR 1=1", "-1 UNION SELECT",
]


@pytest.mark.parametrize("value", HOSTILE_VALUES)
def test_bad_status_is_refused_and_never_echoed(admin, world, value):
    r = admin.get(RECAPS, params={"status": value})
    assert r.status_code == 400
    assert "<script>alert(1)" not in r.text
    if "<" in value:
        assert value not in r.text
    assert count("recap") == 7


@pytest.mark.parametrize("field", ["trip", "owner"])
@pytest.mark.parametrize("value", [
    "abc", "1 OR 1=1", "1; DROP TABLE recap;--", "' OR '1'='1",
    "<script>alert(1)</script>", "1.5", "99999999999999999999999",
])
def test_bad_trip_or_owner_is_refused_and_never_echoed(
        admin, world, field, value):
    r = admin.get(RECAPS, params={field: value})
    assert r.status_code == 400
    assert "<script>alert(1)" not in r.text
    assert count("recap") == 7


def test_bad_trip_is_refused_for_an_editor_too(editor, world):
    assert editor.get(RECAPS, params={"trip": "1 OR 1=1"}).status_code == 400
    assert editor.get(RECAPS, params={"status": "x' OR '1'='1"}
                      ).status_code == 400


def test_a_well_formed_trip_or_owner_that_matches_nothing_is_an_empty_list(
        admin, world):
    assert listed(admin, trip=99999) == []
    assert listed(admin, owner=99999) == []


def test_repeated_filter_parameters_cannot_smuggle_a_value(admin, world):
    r = admin.get(f"{RECAPS}?status=draft&status=' OR '1'='1")
    assert r.status_code in (200, 400)
    if r.status_code == 200:
        ids = [int(i) for i in re.findall(r'href="/admin/recaps/(\d+)"', r.text)]
        assert set(ids) <= {world.r1, world.r4}


def test_recap_titles_are_escaped_in_the_list(admin, world):
    make(world.admin, world.chicago, "xss", title="<script>alert(9)</script>")
    html = admin.get(RECAPS).text
    assert "<script>alert(9)</script>" not in html
    assert "&lt;script&gt;alert(9)&lt;/script&gt;" in html


# ---- CSRF -------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/admin", RECAPS])
@pytest.mark.parametrize("role", ["admin", "editor"])
def test_every_post_form_on_the_new_pages_carries_a_csrf_token(
        client_as, world, path, role):
    html = client_as(role).get(path).text
    forms = re.findall(r"<form\b[^>]*>.*?</form>", html, re.S | re.I)
    assert forms, "expected at least the sign-out form"
    for form in forms:
        opening = re.match(r"<form\b[^>]*>", form, re.I).group(0)
        if 'method="post"' in opening.lower():
            assert 'name="csrf_token"' in form
    assert csrf_from(client_as(role).get(path))


# ---- review fixes: images and no-op deletes ---------------------------------

@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOADS", tmp_path / "uploads")


def test_uploading_an_image_to_a_recap_turns_the_notice_on(
        admin, world, uploads):
    settle()
    assert NOTICE not in admin.get("/admin").text.lower()
    assert upload(admin, world.r3, PNG).status_code == 200
    assert NOTICE in admin.get("/admin").text.lower()


def test_deleting_an_image_of_a_recap_turns_the_notice_on(
        admin, world, uploads):
    assert upload(admin, world.r3, PNG).status_code == 200
    (image,) = image_rows(world.r3)
    settle()
    assert NOTICE not in admin.get("/admin").text.lower()
    r = post(admin, f"{RECAPS}/{world.r3}/images/{image['id']}/delete")
    assert r.status_code == 303, r.text
    assert NOTICE in admin.get("/admin").text.lower()


def test_deleting_a_recap_that_does_not_exist_leaves_the_notice_off(
        admin, world):
    settle()
    recaps.delete_recap(99999)
    assert NOTICE not in admin.get("/admin").text.lower()
