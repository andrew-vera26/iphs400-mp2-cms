"""T03: Trips and Recap Drafts with ownership."""
import re

import pytest

from app import accounts, db
from tests.conftest import DEMO_USERS, csrf_from, log_in
from fastapi.testclient import TestClient
from app.main import create_app

TRIPS = "/admin/trips"
RECAPS = "/admin/recaps"

CHICAGO = {"conference": "Chicago International MUN", "city": "Chicago",
           "start_date": "2026-03-05", "end_date": "2026-03-08",
           "summary": "Four days of committee work in Chicago.",
           "slug": "2026-chicago"}
BOSTON = {"conference": "Boston Collegiate MUN", "city": "Boston",
          "start_date": "2026-02-12", "end_date": "2026-02-15",
          "summary": "A long weekend in Boston.", "slug": "2026-boston"}

BODY = "We **landed** at O'Hare and the food crawl began."


# ---- helpers --------------------------------------------------------------

def post(c, path, **data):
    """POST a form with a valid CSRF token taken from the console home."""
    token = csrf_from(c.get("/admin"))
    return c.post(path, data={"csrf_token": token, **data},
                  follow_redirects=False)


def rows(sql, *args):
    with db.connect() as conn:
        return conn.execute(sql, args).fetchall()


def count(table):
    return rows(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]


def account_id(email):
    return rows("SELECT id FROM account WHERE email = ?", email)[0]["id"]


def make_trip(admin, **overrides):
    r = post(admin, TRIPS, **{**CHICAGO, **overrides})
    assert r.status_code == 303, r.text
    slug = {**CHICAGO, **overrides}["slug"]
    return rows("SELECT id FROM trip WHERE slug = ?", slug)[0]["id"]


def recap_form(trip_id, **overrides):
    return {"trip_id": str(trip_id), "title": "Chicago food crawl",
            "slug": "chicago-food-crawl", "body": BODY, **overrides}


def make_recap(c, trip_id, **overrides):
    """Create a Recap as c. The default Byline is what an Admin must type for a
    Contributor; an Editor's request ignores it."""
    form = recap_form(trip_id, byline_name="Contributor Name",
                      byline_class_year="2027", **overrides)
    r = post(c, RECAPS, **form)
    assert r.status_code == 303, r.text
    slug = form["slug"]
    return rows("SELECT id FROM recap WHERE trip_id = ? AND slug = ?",
                trip_id, slug)[0]["id"]


def recap_row(recap_id):
    return rows("SELECT * FROM recap WHERE id = ?", recap_id)[0]


def second_editor():
    accounts.create_account("other.editor@example.test", "Other Editor", 2027,
                            "editor", "other-editor-pw")
    c = TestClient(create_app())
    assert log_in(c, "other.editor@example.test", "other-editor-pw"
                  ).status_code == 303
    return c


# ---- Trips: create, list, validate ----------------------------------------

def test_admin_creates_a_trip_and_it_is_listed(client_as):
    admin = client_as("admin")
    r = post(admin, TRIPS, **CHICAGO)
    assert r.status_code == 303 and r.headers["location"] == TRIPS

    row = rows("SELECT * FROM trip")[0]
    for field, value in CHICAGO.items():
        assert row[field] == value
    assert CHICAGO["conference"] in admin.get(TRIPS).text


@pytest.mark.parametrize("field", list(CHICAGO))
@pytest.mark.parametrize("blank", ["", "   "])
def test_every_trip_field_and_the_slug_are_required(client_as, field, blank):
    admin = client_as("admin")
    assert post(admin, TRIPS, **{**CHICAGO, field: blank}).status_code == 400
    assert count("trip") == 0


@pytest.mark.parametrize("start_date,city,suggested", [
    ("2026-03-05", "Chicago", "2026-chicago"),
    ("2027-11-20", "St. Louis", "2027-st-louis"),
])
def test_trip_slug_is_suggested_from_year_and_city(client_as, start_date, city,
                                                   suggested):
    page = client_as("admin").get(
        f"{TRIPS}/new", params={"start_date": start_date, "city": city})
    assert f'name="slug" value="{suggested}"' in page.text


def test_duplicate_trip_slug_is_refused_with_a_clear_error(client_as):
    admin = client_as("admin")
    make_trip(admin)
    r = post(admin, TRIPS, **{**BOSTON, "slug": CHICAGO["slug"]})
    assert r.status_code == 400
    assert "already in use" in r.text.lower()
    assert count("trip") == 1


# ---- Trips: edit and delete -----------------------------------------------

def test_admin_edits_a_trip(client_as):
    admin = client_as("admin")
    trip_id = make_trip(admin)
    r = post(admin, f"{TRIPS}/{trip_id}",
             **{**CHICAGO, "summary": "Revised summary."})
    assert r.status_code == 303
    assert rows("SELECT summary FROM trip WHERE id = ?", trip_id
                )[0]["summary"] == "Revised summary."


def test_editing_a_trip_cannot_take_another_trips_slug(client_as):
    admin = client_as("admin")
    make_trip(admin)
    boston_id = make_trip(admin, **BOSTON)
    r = post(admin, f"{TRIPS}/{boston_id}", **{**BOSTON, "slug": "2026-chicago"})
    assert r.status_code == 400 and "already in use" in r.text.lower()
    assert rows("SELECT slug FROM trip WHERE id = ?", boston_id
                )[0]["slug"] == "2026-boston"


def test_admin_deletes_a_trip_without_recaps(client_as):
    admin = client_as("admin")
    trip_id = make_trip(admin)
    assert post(admin, f"{TRIPS}/{trip_id}/delete").status_code == 303
    assert count("trip") == 0


def test_deleting_a_trip_that_has_a_recap_is_refused(client_as):
    admin = client_as("admin")
    trip_id = make_trip(admin)
    make_recap(admin, trip_id)
    r = post(admin, f"{TRIPS}/{trip_id}/delete")
    assert r.status_code in (400, 409)
    assert count("trip") == 1 and count("recap") == 1


def test_editor_cannot_write_trips(client_as):
    admin, editor = client_as("admin"), client_as("editor")
    trip_id = make_trip(admin)
    assert post(editor, TRIPS, **BOSTON).status_code == 403
    assert post(editor, f"{TRIPS}/{trip_id}", **{**CHICAGO, "summary": "x"}
                ).status_code == 403
    assert post(editor, f"{TRIPS}/{trip_id}/delete").status_code == 403
    assert count("trip") == 1
    assert rows("SELECT summary FROM trip")[0]["summary"] == CHICAGO["summary"]


# ---- Recaps: creating a Draft ---------------------------------------------

def test_editor_creates_a_draft_with_byline_and_owner_from_their_account(
        client_as):
    trip_id = make_trip(client_as("admin"))
    editor = client_as("editor")
    r = post(editor, RECAPS, **recap_form(trip_id))
    assert r.status_code == 303

    row = rows("SELECT * FROM recap")[0]
    assert row["status"] == "draft"
    assert row["trip_id"] == trip_id
    assert row["title"] == "Chicago food crawl"
    assert row["slug"] == "chicago-food-crawl"
    assert row["body"] == BODY  # stored raw
    assert row["owner_id"] == account_id(DEMO_USERS["editor"]["email"])
    assert row["byline_name"] == "Demo Editor"
    assert row["byline_class_year"] == 2028


def test_editor_picks_the_trip_from_a_list(client_as):
    trip_id = make_trip(client_as("admin"))
    page = client_as("editor").get(f"{RECAPS}/new")
    assert page.status_code == 200
    assert f'value="{trip_id}"' in page.text
    assert CHICAGO["conference"] in page.text


def test_recap_for_a_trip_that_does_not_exist_is_refused(client_as):
    assert post(client_as("editor"), RECAPS, **recap_form(999)
                ).status_code == 400
    assert count("recap") == 0


def test_recap_slug_is_suggested_from_the_title(client_as):
    make_trip(client_as("admin"))
    page = client_as("editor").get(f"{RECAPS}/new",
                                   params={"title": "Chicago Food Crawl!"})
    assert 'name="slug" value="chicago-food-crawl"' in page.text


def test_recap_slug_clash_within_a_trip_is_refused(client_as):
    trip_id = make_trip(client_as("admin"))
    editor = client_as("editor")
    make_recap(editor, trip_id)
    r = post(editor, RECAPS, **recap_form(trip_id, title="Another title"))
    assert r.status_code == 400 and "already in use" in r.text.lower()
    assert count("recap") == 1


def test_same_recap_slug_on_a_different_trip_is_allowed(client_as):
    admin, editor = client_as("admin"), client_as("editor")
    make_recap(editor, make_trip(admin))
    boston_id = make_trip(admin, **BOSTON)
    assert post(editor, RECAPS, **recap_form(boston_id)).status_code == 303
    assert count("recap") == 2


@pytest.mark.parametrize("field", ["title", "slug"])
@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_title_or_slug_is_refused(client_as, field, blank):
    trip_id = make_trip(client_as("admin"))
    r = post(client_as("editor"), RECAPS, **recap_form(trip_id, **{field: blank}))
    assert r.status_code == 400
    alert = re.search(r'role="alert">([^<]*)<', r.text)
    assert alert and field in alert.group(1).lower()
    assert count("recap") == 0


@pytest.mark.parametrize("body", ["", "   ", "\n\t \n"])
def test_empty_or_whitespace_body_is_refused(client_as, body):
    trip_id = make_trip(client_as("admin"))
    assert post(client_as("editor"), RECAPS, **recap_form(trip_id, body=body)
                ).status_code == 400
    assert count("recap") == 0


def test_admin_enters_a_recap_for_a_contributor(client_as):
    admin = client_as("admin")
    trip_id = make_trip(admin)
    r = post(admin, RECAPS, **recap_form(
        trip_id, byline_name="Jane Doe", byline_class_year="2027"))
    assert r.status_code == 303

    row = rows("SELECT * FROM recap")[0]
    assert row["byline_name"] == "Jane Doe" and row["byline_class_year"] == 2027
    assert row["owner_id"] == account_id(DEMO_USERS["admin"]["email"])
    assert row["status"] == "draft"


@pytest.mark.parametrize("byline", [
    {},
    {"byline_name": "", "byline_class_year": ""},
    {"byline_name": "Jane Doe"},
    {"byline_class_year": "2027"},
    {"byline_name": "   ", "byline_class_year": "2027"},
    {"byline_name": "Jane Doe", "byline_class_year": "not-a-year"},
])
def test_admin_must_type_both_parts_of_a_contributor_byline(client_as, byline):
    admin = client_as("admin")
    trip_id = make_trip(admin)
    r = post(admin, RECAPS, **recap_form(trip_id, **byline))
    assert r.status_code == 400
    assert "byline" in r.text.lower()
    assert count("recap") == 0


def test_an_editor_cannot_type_a_byline(client_as):
    trip_id = make_trip(client_as("admin"))
    post(client_as("editor"), RECAPS, **recap_form(
        trip_id, byline_name="Somebody Else", byline_class_year="1999"))
    row = rows("SELECT * FROM recap")[0]
    assert row["byline_name"] == "Demo Editor"
    assert row["byline_class_year"] == 2028


def test_renaming_the_owner_later_does_not_change_the_byline(client_as):
    trip_id = make_trip(client_as("admin"))
    recap_id = make_recap(client_as("editor"), trip_id)
    with db.connect() as conn:
        conn.execute("UPDATE account SET name = 'Renamed Person', "
                     "class_year = 2031 WHERE role = 'editor'")
    row = recap_row(recap_id)
    assert row["byline_name"] == "Demo Editor"
    assert row["byline_class_year"] == 2028


def test_editor_shows_owner_and_timestamps(client_as):
    trip_id = make_trip(client_as("admin"))
    editor = client_as("editor")
    recap_id = make_recap(editor, trip_id)
    row = recap_row(recap_id)
    assert row["created_at"] and row["edited_at"]

    page = editor.get(f"{RECAPS}/{recap_id}")
    assert page.status_code == 200
    assert "Demo Editor" in page.text
    assert row["created_at"] in page.text and row["edited_at"] in page.text


# ---- Recaps: Editor edits and deletes their own Draft ---------------------

def test_editor_edits_their_own_draft(client_as):
    trip_id = make_trip(client_as("admin"))
    editor = client_as("editor")
    recap_id = make_recap(editor, trip_id)
    r = post(editor, f"{RECAPS}/{recap_id}",
             **recap_form(trip_id, title="New title", body="New body."))
    assert r.status_code == 303
    row = recap_row(recap_id)
    assert row["title"] == "New title" and row["body"] == "New body."
    assert row["status"] == "draft"
    assert row["owner_id"] == account_id(DEMO_USERS["editor"]["email"])


def test_saving_an_edit_with_an_empty_body_is_refused(client_as):
    trip_id = make_trip(client_as("admin"))
    editor = client_as("editor")
    recap_id = make_recap(editor, trip_id)
    assert post(editor, f"{RECAPS}/{recap_id}", **recap_form(trip_id, body="  ")
                ).status_code == 400
    assert recap_row(recap_id)["body"] == BODY


def test_editing_a_recap_cannot_take_a_sibling_slug(client_as):
    trip_id = make_trip(client_as("admin"))
    editor = client_as("editor")
    make_recap(editor, trip_id)
    other_id = make_recap(editor, trip_id, title="Second", slug="second")
    r = post(editor, f"{RECAPS}/{other_id}",
             **recap_form(trip_id, title="Second", slug="chicago-food-crawl"))
    assert r.status_code == 400 and "already in use" in r.text.lower()
    assert recap_row(other_id)["slug"] == "second"


def test_editor_deletes_their_own_draft(client_as):
    trip_id = make_trip(client_as("admin"))
    editor = client_as("editor")
    recap_id = make_recap(editor, trip_id)
    assert post(editor, f"{RECAPS}/{recap_id}/delete").status_code == 303
    assert count("recap") == 0


# ---- Recaps: ownership ----------------------------------------------------

def test_editor_is_refused_on_another_persons_recap(client_as):
    admin = client_as("admin")
    trip_id = make_trip(admin)
    recap_id = make_recap(admin, trip_id)  # owned by the Admin
    before = recap_row(recap_id)
    editor = client_as("editor")

    assert editor.get(f"{RECAPS}/{recap_id}").status_code == 403
    assert post(editor, f"{RECAPS}/{recap_id}",
                **recap_form(trip_id, title="Hijacked", body="Hijacked.")
                ).status_code == 403
    assert post(editor, f"{RECAPS}/{recap_id}/delete").status_code == 403
    assert tuple(recap_row(recap_id)) == tuple(before)


def test_one_editor_cannot_touch_another_editors_recap(client_as):
    trip_id = make_trip(client_as("admin"))
    recap_id = make_recap(client_as("editor"), trip_id)
    before = recap_row(recap_id)
    other = second_editor()

    assert other.get(f"{RECAPS}/{recap_id}").status_code == 403
    assert post(other, f"{RECAPS}/{recap_id}",
                **recap_form(trip_id, body="Hijacked.")).status_code == 403
    assert post(other, f"{RECAPS}/{recap_id}/delete").status_code == 403
    assert tuple(recap_row(recap_id)) == tuple(before)


def test_editors_list_shows_only_their_own_recaps_and_admins_see_all(client_as):
    admin, editor = client_as("admin"), client_as("editor")
    trip_id = make_trip(admin)
    make_recap(editor, trip_id, title="Mine", slug="mine")
    make_recap(admin, trip_id, title="Admins entry", slug="admins-entry")

    mine = editor.get(RECAPS)
    assert mine.status_code == 200
    assert "Mine" in mine.text and "Admins entry" not in mine.text

    everything = admin.get(RECAPS)
    assert "Mine" in everything.text and "Admins entry" in everything.text


# ---- Recaps: Admin powers -------------------------------------------------

def test_admin_edits_any_recap_including_the_byline(client_as):
    trip_id = make_trip(client_as("admin"))
    recap_id = make_recap(client_as("editor"), trip_id)
    admin = client_as("admin")
    r = post(admin, f"{RECAPS}/{recap_id}", **recap_form(
        trip_id, body="Fixed typo.", byline_name="Jane Doe",
        byline_class_year="2027"))
    assert r.status_code == 303
    row = recap_row(recap_id)
    assert row["body"] == "Fixed typo."
    assert row["byline_name"] == "Jane Doe" and row["byline_class_year"] == 2027
    # editing does not hand the Recap to the Admin
    assert row["owner_id"] == account_id(DEMO_USERS["editor"]["email"])


@pytest.mark.parametrize("byline", [
    {"byline_name": "", "byline_class_year": "2027"},
    {"byline_name": "Jane Doe", "byline_class_year": "not-a-year"},
])
def test_admin_cannot_blank_a_byline_on_edit(client_as, byline):
    trip_id = make_trip(client_as("admin"))
    recap_id = make_recap(client_as("editor"), trip_id)
    before = recap_row(recap_id)
    r = post(client_as("admin"), f"{RECAPS}/{recap_id}",
             **recap_form(trip_id, **byline))
    assert r.status_code == 400 and "byline" in r.text.lower()
    assert tuple(recap_row(recap_id)) == tuple(before)


def test_admin_deletes_any_recap(client_as):
    trip_id = make_trip(client_as("admin"))
    recap_id = make_recap(client_as("editor"), trip_id)
    assert post(client_as("admin"), f"{RECAPS}/{recap_id}/delete"
                ).status_code == 303
    assert count("recap") == 0


# ---- CSRF -----------------------------------------------------------------

@pytest.mark.parametrize("path", [f"{TRIPS}/new", f"{RECAPS}/new"])
def test_new_forms_carry_a_csrf_token(client_as, path):
    make_trip(client_as("admin"))
    assert csrf_from(client_as("admin").get(path))


def test_state_changing_requests_without_a_token_are_refused(client_as):
    admin = client_as("admin")
    trip_id = make_trip(admin)
    assert admin.post(TRIPS, data=BOSTON).status_code == 403
    assert admin.post(RECAPS, data=recap_form(trip_id)).status_code == 403
    assert admin.post(f"{TRIPS}/{trip_id}/delete").status_code == 403
    assert count("trip") == 1 and count("recap") == 0


# ---- review fix: typed Slugs must be URL-safe -------------------------------

BAD_SLUGS = ["../x", "A B", "a/b", "Upper", "-lead", "trail-", "a--b", "é"]


@pytest.mark.parametrize("slug", BAD_SLUGS)
def test_trip_slug_must_be_url_safe(client_as, slug):
    admin = client_as("admin")
    r = post(admin, TRIPS, **{**CHICAGO, "slug": slug})
    assert r.status_code == 400
    assert count("trip") == 0


@pytest.mark.parametrize("slug", BAD_SLUGS)
def test_recap_slug_must_be_url_safe(client_as, slug):
    admin = client_as("admin")
    trip_id = make_trip(admin)
    r = post(admin, RECAPS, **recap_form(trip_id, slug=slug,
             byline_name="Contributor Name", byline_class_year="2027"))
    assert r.status_code == 400
    assert count("recap") == 0


def test_edit_cannot_change_a_slug_to_an_unsafe_one(client_as):
    admin = client_as("admin")
    trip_id = make_trip(admin)
    r = post(admin, f"{TRIPS}/{trip_id}", **{**CHICAGO, "slug": "a/b"})
    assert r.status_code == 400
    assert rows("SELECT slug FROM trip WHERE id = ?", trip_id)[0]["slug"] \
        == CHICAGO["slug"]


# ---- review fix: Trip dates are validated on the server ---------------------

@pytest.mark.parametrize("field", ["start_date", "end_date"])
@pytest.mark.parametrize("bad", ["garbage", "2026-02-30", "2026-3-5",
                                 "03/05/2026"])
def test_trip_dates_must_be_real_iso_dates(client_as, field, bad):
    admin = client_as("admin")
    assert post(admin, TRIPS, **{**CHICAGO, field: bad}).status_code == 400
    assert count("trip") == 0


def test_trip_cannot_end_before_it_starts(client_as):
    admin = client_as("admin")
    r = post(admin, TRIPS, **{**CHICAGO, "start_date": "2026-03-08",
                              "end_date": "2026-03-05"})
    assert r.status_code == 400
    assert "end" in r.text.lower() and count("trip") == 0


def test_one_day_trip_is_allowed(client_as):
    admin = client_as("admin")
    r = post(admin, TRIPS, **{**CHICAGO, "end_date": CHICAGO["start_date"]})
    assert r.status_code == 303


def test_edit_cannot_move_the_end_before_the_start(client_as):
    admin = client_as("admin")
    trip_id = make_trip(admin)
    r = post(admin, f"{TRIPS}/{trip_id}", **{**CHICAGO, "end_date": "2026-03-01"})
    assert r.status_code == 400
    assert rows("SELECT end_date FROM trip WHERE id = ?", trip_id)[0][
        "end_date"] == CHICAGO["end_date"]


@pytest.mark.parametrize("start_date", ["abcd-01-01", "²³⁴⁵-01-01", "20", ""])
def test_slug_suggestion_ignores_a_start_date_that_is_not_a_date(
        client_as, start_date):
    page = client_as("admin").get(
        f"{TRIPS}/new", params={"start_date": start_date, "city": "Chicago"})
    assert page.status_code == 200 and 'name="slug" value=""' in page.text


# ---- review fix: only a UNIQUE clash means "Slug already in use" -------------

def test_a_non_slug_integrity_error_is_not_reported_as_a_slug_clash(client_as):
    import sqlite3
    from app import recaps, trips
    client_as("admin")
    with pytest.raises(sqlite3.IntegrityError) as trip_err:
        trips.create_trip({**CHICAGO, "conference": None})
    assert not isinstance(trip_err.value, trips.SlugTaken)

    trip_id = trips.create_trip(CHICAGO)
    owner = account_id(DEMO_USERS["admin"]["email"])
    with pytest.raises(sqlite3.IntegrityError) as recap_err:
        recaps.create_recap(trip_id, owner, None, "a-slug", BODY, "Name", 2027)
    assert not isinstance(recap_err.value, recaps.SlugTaken)
