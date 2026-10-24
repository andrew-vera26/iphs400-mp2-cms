"""T07: Pages and the Navigation bar.

Seams: the HTTP app (TestClient) and `app.publish.render_site(out)`. Pages are
set up through the real routes, then the output folder is read back as a reader
would see it. Routes under test (all Admin-only):

    GET  /admin/pages[?status=draft|published]      the list, filterable
    GET  /admin/pages/new                           the New Page editor
    POST /admin/pages                               create (always a Draft)
    GET  /admin/pages/{id}                          the editor
    POST /admin/pages/{id}                          save
    POST /admin/pages/{id}/delete
    POST /admin/pages/{id}/publish | unpublish
    POST /admin/pages/preview                       (the New Page editor)
    POST /admin/pages/{id}/preview                  (an existing Page's editor)

The form fields are title, slug, body and nav_position. Preview re-renders the
editor with the sanitized Body inside <section id="preview">. On the Public
site a Published Page is written at `<slug>/index.html`, and every page carries
a <nav> with Home first, then the Published Pages by nav position.
"""
import re

import pytest

from app.markdown import render_body
from app import pages
from app.publish import PublishRefused, render_site
from tests.conftest import DEMO_USERS
from tests.test_t03 import post, rows
from tests.test_t05 import make_recap, make_trip, read, site_files

PAGES = "/admin/pages"
LIVE_NOTICE = "still live until you Deploy"
RESERVED = ["trips", "images", "admin", "login"]
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

HOSTILE = ("Hello **world**.\n\n<script>alert(1)</script>\n\n"
           "[evil](https://evil.example/x) ![pic](https://evil.example/p.png)"
           "\n\n![mine](images/own.png)\n\n<b>raw</b> html\n\n"
           "Mail [me](mailto:jane@kenyon.edu) or jane@kenyon.edu")


# ---- helpers --------------------------------------------------------------

def page_form(**overrides):
    return {"title": "About the club", "slug": "about",
            "body": "We are the **Kenyon** Model UN club.",
            "nav_position": "1", **overrides}


def page_id(admin, title):
    """The id of the listed Page called `title`, read from its editor link."""
    html = admin.get(PAGES).text
    match = re.search(
        rf'<a href="/admin/pages/(\d+)">{re.escape(title)}</a>', html)
    assert match, f"{title!r} is not in the Pages list"
    return int(match.group(1))


def make_page(admin, published=False, **overrides):
    """Create a Page through the real routes (Draft), optionally Publish it.
    Returns its id."""
    form = page_form(**overrides)
    r = post(admin, PAGES, **form)
    assert r.status_code == 303, r.text
    pid = page_id(admin, form["title"])
    if published:
        assert post(admin, f"{PAGES}/{pid}/publish").status_code == 303
    return pid


def follow(c, response):
    assert response.status_code == 303
    return c.get(response.headers["location"])


def forms(html):
    """[(form tag + contents)] for every <form> on the page."""
    return [m.group(0) for m in re.finditer(r"<form\b.*?</form>", html, re.S)]


def preview_region(html):
    match = re.search(r'<section id="preview">(.*?)</section>', html, re.S)
    assert match, "page has no <section id=\"preview\">"
    return match.group(1)


def row_for(html, title):
    """The list row (<tr>) that mentions `title`."""
    match = re.search(rf"<tr>(?:(?!</tr>).)*{re.escape(title)}.*?</tr>", html, re.S)
    assert match, f"{title!r} is not in the Pages list"
    return match.group(0)


def nav_links(html):
    """[(text, href)] of the links inside the page's <nav>."""
    nav = re.search(r"<nav\b.*?</nav>", html, re.S)
    assert nav, "page has no <nav>"
    return [(m.group(2).strip(), m.group(1)) for m in
            re.finditer(r'<a href="([^"]+)"[^>]*>([^<]+)</a>', nav.group(0))]


def html_files(out):
    return [p for p in site_files(out) if p.suffix == ".html"]


# ---- create, edit, delete, Publish, Unpublish -----------------------------

def test_admin_creates_a_page_and_it_starts_as_a_draft(client_as):
    admin = client_as("admin")
    r = post(admin, PAGES, **page_form())
    assert r.status_code == 303 and r.headers["location"] == PAGES
    listing = admin.get(PAGES).text
    assert "About the club" in listing
    assert "Draft" in row_for(listing, "About the club")


def test_a_page_cannot_be_created_already_published(client_as):
    admin = client_as("admin")
    post(admin, PAGES, **page_form(status="published"))
    assert "Draft" in row_for(admin.get(PAGES).text, "About the club")


def test_admin_edits_a_page(client_as):
    admin = client_as("admin")
    pid = make_page(admin)
    r = post(admin, f"{PAGES}/{pid}",
             **page_form(title="About us", body="New words.", nav_position="4"))
    assert r.status_code == 303
    editor = admin.get(f"{PAGES}/{pid}").text
    assert 'value="About us"' in editor and "New words." in editor
    assert re.search(r'name="nav_position"[^>]*value="4"', editor)
    assert "About the club" not in admin.get(PAGES).text


def test_admin_deletes_a_page(client_as):
    admin = client_as("admin")
    pid = make_page(admin)
    r = post(admin, f"{PAGES}/{pid}/delete")
    assert r.status_code == 303
    assert "About the club" not in admin.get(PAGES).text
    assert admin.get(f"{PAGES}/{pid}").status_code == 404


def test_publish_and_unpublish_move_the_status(client_as):
    admin = client_as("admin")
    pid = make_page(admin)
    assert post(admin, f"{PAGES}/{pid}/publish").status_code == 303
    assert "Published" in row_for(admin.get(PAGES).text, "About the club")
    assert post(admin, f"{PAGES}/{pid}/unpublish").status_code == 303
    assert "Draft" in row_for(admin.get(PAGES).text, "About the club")


def test_the_editor_records_owner_and_both_timestamps(client_as):
    admin = client_as("admin")
    pid = make_page(admin)
    owner = rows("SELECT name FROM account WHERE email = ?",
                 DEMO_USERS["admin"]["email"])[0]["name"]
    html = admin.get(f"{PAGES}/{pid}").text
    assert re.search(rf"Owner.*?{re.escape(owner)}", html, re.S)
    assert re.search(r"Created.*?" + TIMESTAMP.pattern, html, re.S)
    assert re.search(r"Last edited.*?" + TIMESTAMP.pattern, html, re.S)


# ---- Slugs ----------------------------------------------------------------

@pytest.mark.parametrize("slug", RESERVED)
def test_a_reserved_slug_is_refused_with_a_clear_error(client_as, slug):
    admin = client_as("admin")
    r = post(admin, PAGES, **page_form(slug=slug))
    assert r.status_code == 400
    assert "reserved" in r.text.lower() and slug in r.text
    assert "About the club" not in admin.get(PAGES).text


@pytest.mark.parametrize("slug", RESERVED)
def test_renaming_a_page_to_a_reserved_slug_is_refused(client_as, slug):
    admin = client_as("admin")
    pid = make_page(admin)
    r = post(admin, f"{PAGES}/{pid}", **page_form(slug=slug))
    assert r.status_code == 400 and "reserved" in r.text.lower()
    assert f'value="{slug}"' not in admin.get(f"{PAGES}/{pid}").text


def test_a_duplicate_page_slug_is_refused_with_a_clear_error(client_as):
    admin = client_as("admin")
    make_page(admin)
    r = post(admin, PAGES, **page_form(title="Another page"))
    assert r.status_code == 400 and "already in use" in r.text
    assert "Another page" not in admin.get(PAGES).text


def test_editing_a_page_onto_another_pages_slug_is_refused(client_as):
    admin = client_as("admin")
    make_page(admin)
    other = make_page(admin, title="Officers", slug="officers")
    r = post(admin, f"{PAGES}/{other}", **page_form(title="Officers"))
    assert r.status_code == 400 and "already in use" in r.text


def test_saving_a_page_with_its_own_slug_is_not_a_clash(client_as):
    admin = client_as("admin")
    pid = make_page(admin)
    assert post(admin, f"{PAGES}/{pid}",
                **page_form(body="Edited.")).status_code == 303


def test_a_nav_position_must_be_a_number(client_as):
    admin = client_as("admin")
    r = post(admin, PAGES, **page_form(nav_position="first"))
    assert r.status_code == 400
    assert "About the club" not in admin.get(PAGES).text


# ---- the Pages list filter ------------------------------------------------

def test_the_pages_list_filters_by_status(client_as):
    admin = client_as("admin")
    make_page(admin, title="Live page", slug="live", published=True)
    make_page(admin, title="Draft page", slug="draft-one")

    both = admin.get(PAGES).text
    assert "Live page" in both and "Draft page" in both
    drafts = admin.get(PAGES, params={"status": "draft"}).text
    assert "Draft page" in drafts and "Live page" not in drafts
    live = admin.get(PAGES, params={"status": "published"}).text
    assert "Live page" in live and "Draft page" not in live


# ---- Preview --------------------------------------------------------------

def assert_sanitized(region):
    assert "<strong>world</strong>" in region
    for gone in ("<script", "alert(1)", "evil.example", "mailto:", "<img",
                 "<b>", "images/own.png"):
        assert gone not in region, gone
    assert "jane@kenyon.edu" in region  # the address survives as plain text


def test_new_page_preview_shows_the_sanitized_body(client_as):
    admin = client_as("admin")
    r = post(admin, f"{PAGES}/preview", **page_form(body=HOSTILE))
    assert r.status_code == 200
    assert_sanitized(preview_region(r.text))
    assert "About the club" not in admin.get(PAGES).text  # nothing was saved


def test_existing_page_preview_shows_the_sanitized_body(client_as):
    admin = client_as("admin")
    pid = make_page(admin)
    r = post(admin, f"{PAGES}/{pid}/preview", **page_form(body=HOSTILE))
    assert r.status_code == 200
    assert_sanitized(preview_region(r.text))
    assert "Kenyon" in admin.get(f"{PAGES}/{pid}").text  # still the saved Body


# ---- the "still live until you Deploy" notice -----------------------------

def test_editing_a_published_page_shows_the_still_live_notice(client_as):
    admin = client_as("admin")
    pid = make_page(admin, published=True)
    r = post(admin, f"{PAGES}/{pid}", **page_form(body="Fixed typo."))
    assert LIVE_NOTICE in follow(admin, r).text


def test_unpublishing_a_page_shows_the_still_live_notice(client_as):
    admin = client_as("admin")
    pid = make_page(admin, published=True)
    r = post(admin, f"{PAGES}/{pid}/unpublish")
    assert LIVE_NOTICE in follow(admin, r).text


def test_editing_a_draft_page_shows_no_notice(client_as):
    admin = client_as("admin")
    pid = make_page(admin)
    r = post(admin, f"{PAGES}/{pid}", **page_form(body="Fixed typo."))
    assert LIVE_NOTICE not in follow(admin, r).text


# ---- Editors are refused --------------------------------------------------

def test_an_editor_cannot_create_edit_publish_or_delete_a_page(client_as):
    admin = client_as("admin")
    pid = make_page(admin, published=True)
    editor = client_as("editor")

    assert post(editor, PAGES, **page_form(title="Sneaky", slug="sneaky")
                ).status_code == 403
    assert post(editor, f"{PAGES}/{pid}", **page_form(title="Hijacked")
                ).status_code == 403
    assert post(editor, f"{PAGES}/{pid}/unpublish").status_code == 403
    assert post(editor, f"{PAGES}/{pid}/delete").status_code == 403
    assert post(editor, f"{PAGES}/preview", **page_form()).status_code == 403

    listing = admin.get(PAGES).text
    assert "Sneaky" not in listing and "Hijacked" not in listing
    assert "Published" in row_for(listing, "About the club")


def test_an_editor_cannot_read_the_pages_area(client_as):
    admin = client_as("admin")
    pid = make_page(admin)
    editor = client_as("editor")
    for path in (PAGES, f"{PAGES}/new", f"{PAGES}/{pid}"):
        assert editor.get(path, follow_redirects=False).status_code == 403, path


# ---- CSRF -----------------------------------------------------------------

def test_every_page_form_carries_a_csrf_token(client_as):
    admin = client_as("admin")
    pid = make_page(admin, published=True)
    make_page(admin, title="Draft page", slug="draft-one")
    for path in (PAGES, f"{PAGES}/new", f"{PAGES}/{pid}"):
        r = admin.get(path)
        assert r.status_code == 200, path
        page_forms = [f for f in forms(r.text) if "/logout" not in f]
        assert page_forms, f"{path} has no forms"
        for form in page_forms:
            assert 'name="csrf_token"' in form, f"{path}: {form[:120]}"


@pytest.mark.parametrize("suffix,expected", [
    ("", 403), ("/1", 403), ("/1/delete", 403), ("/1/publish", 403),
    ("/1/unpublish", 403), ("/preview", 403), ("/1/preview", 403),
])
def test_page_posts_without_a_valid_token_are_403(client_as, suffix, expected):
    admin = client_as("admin")
    pid = make_page(admin)
    path = f"{PAGES}{suffix}".replace("/1", f"/{pid}")
    assert admin.post(path, data=page_form(), follow_redirects=False
                      ).status_code == expected
    assert admin.post(path, data={**page_form(), "csrf_token": "bad"},
                      follow_redirects=False).status_code == expected
    # and the Page is untouched
    assert "Draft" in row_for(admin.get(PAGES).text, "About the club")


# ---- the Public site ------------------------------------------------------

def test_published_pages_are_written_and_drafts_are_not(database, client_as,
                                                       tmp_path):
    admin = client_as("admin")
    make_page(admin, title="About the club", slug="about",
              body="ABOUT-VISIBLE-TEXT", published=True)
    make_page(admin, title="Secret draft", slug="secret",
              body="DRAFT-ONLY-TEXT")

    out = render_site(tmp_path / "site")

    assert "ABOUT-VISIBLE-TEXT" in read(out, "about/index.html")
    assert "About the club" in read(out, "about/index.html")
    assert not (out / "secret").exists()
    everything = "".join(p.read_text() for p in html_files(out))
    for leaked in ("DRAFT-ONLY-TEXT", "Secret draft", "secret"):
        assert leaked not in everything


def test_an_unpublished_page_disappears_on_the_next_run(database, client_as,
                                                        tmp_path):
    admin = client_as("admin")
    pid = make_page(admin, published=True)
    assert (render_site(tmp_path / "site") / "about/index.html").exists()
    post(admin, f"{PAGES}/{pid}/unpublish")
    out = render_site(tmp_path / "site")
    assert not (out / "about").exists()
    assert "About the club" not in read(out, "index.html")


def test_a_page_body_is_sanitized_exactly_as_preview_shows_it(database,
                                                              client_as,
                                                              tmp_path):
    admin = client_as("admin")
    make_page(admin, body=HOSTILE, published=True)
    html = read(render_site(tmp_path / "site"), "about/index.html")
    assert render_body(HOSTILE) in html
    for gone in ("<script", "evil.example", "mailto:", "<img", "<b>raw"):
        assert gone not in html, gone
    assert "jane@kenyon.edu" in html


def test_navigation_bar_is_home_then_published_pages_in_nav_order(
        database, client_as, tmp_path):
    admin = client_as("admin")
    # created out of nav order on purpose, so creation order cannot pass this
    make_page(admin, title="Third", slug="third", nav_position="30",
              published=True)
    make_page(admin, title="First", slug="first", nav_position="10",
              published=True)
    make_page(admin, title="Second", slug="second", nav_position="20",
              published=True)
    make_page(admin, title="Hidden", slug="hidden", nav_position="5")

    out = render_site(tmp_path / "site")

    for page in html_files(out):
        links = nav_links(page.read_text())
        assert [text for text, _ in links] == ["Home", "First", "Second",
                                               "Third"], page.relative_to(out)


def test_pages_sharing_a_nav_position_are_ordered_by_title(database, client_as,
                                                           tmp_path):
    admin = client_as("admin")
    # created Bravo first, so insertion order cannot pass this
    make_page(admin, title="Bravo", slug="bravo", nav_position="5",
              published=True)
    make_page(admin, title="Alpha", slug="alpha", nav_position="5",
              published=True)
    make_page(admin, title="Zulu", slug="zulu", nav_position="1",
              published=True)

    out = render_site(tmp_path / "site")

    assert [t for t, _ in nav_links(read(out, "index.html"))] == [
        "Home", "Zulu", "Alpha", "Bravo"]


def test_navigation_bar_is_home_alone_when_no_page_is_published(database,
                                                                client_as,
                                                                tmp_path):
    make_page(client_as("admin"), title="Hidden", slug="hidden")
    out = render_site(tmp_path / "site")
    assert [t for t, _ in nav_links(read(out, "index.html"))] == ["Home"]


def test_navigation_links_resolve_from_every_depth(database, client_as,
                                                   tmp_path):
    admin = client_as("admin")
    make_page(admin, title="About the club", slug="about", nav_position="1",
              published=True)
    make_page(admin, title="Officers", slug="officers", nav_position="2",
              published=True)
    trip = make_trip("2026-chicago", "2026-03-01")
    make_recap(trip, "food-crawl")

    out = render_site(tmp_path / "site")

    depths = {"index.html": 0, "about/index.html": 1,
              "officers/index.html": 1, "trips/2026-chicago/index.html": 2,
              "trips/2026-chicago/food-crawl/index.html": 3}
    assert {str(p.relative_to(out)) for p in html_files(out)} == set(depths)
    expected = {"Home": out / "index.html",
                "About the club": out / "about/index.html",
                "Officers": out / "officers/index.html"}
    for rel in depths:
        page = out / rel
        for text, href in nav_links(page.read_text()):
            resolved = (page.parent / href).resolve()
            if resolved.is_dir():
                resolved = resolved / "index.html"
            assert resolved == expected[text].resolve(), f"{rel}: {text} -> {href}"


def test_no_root_absolute_paths_with_pages_in_the_output(database, client_as,
                                                         tmp_path):
    admin = client_as("admin")
    make_page(admin, body="Go [home](../index.html).", published=True)
    make_page(admin, title="Officers", slug="officers", nav_position="2",
              published=True)
    trip = make_trip("2026-chicago", "2026-03-01")
    make_recap(trip, "food-crawl")

    out = render_site(tmp_path / "site")

    assert (out / "about/index.html").exists()
    for page in html_files(out):
        html = page.read_text()
        assert 'href="/' not in html and 'src="/' not in html, page
        for target in re.findall(r'(?:href|src)="([^"]+)"', html):
            if target.startswith("https://www.instagram.com/"):
                continue
            assert "://" not in target, f"{page}: {target}"
            resolved = (page.parent / target.split("#")[0]).resolve()
            if resolved.is_dir():
                resolved = resolved / "index.html"
            assert resolved.exists(), f"{page.relative_to(out)}: {target}"


# ---- review follow-ups ----------------------------------------------------

@pytest.mark.parametrize("nav", [
    "²", "--5", "99999999999999999999", "-9223372036854775809",
    "9223372036854775808"])
def test_a_nav_position_that_is_not_a_64_bit_whole_number_is_a_400(client_as,
                                                                   nav):
    admin = client_as("admin")
    r = post(admin, PAGES, **page_form(nav_position=nav))
    assert r.status_code == 400
    assert "About the club" not in admin.get(PAGES).text


@pytest.mark.parametrize("nav", ["-5", "9223372036854775807"])
def test_negative_and_largest_nav_positions_are_still_accepted(client_as, nav):
    admin = client_as("admin")
    assert post(admin, PAGES, **page_form(nav_position=nav)).status_code == 303
    assert "About the club" in admin.get(PAGES).text


def test_a_300_character_slug_is_refused_on_create(client_as):
    admin = client_as("admin")
    r = post(admin, PAGES, **page_form(slug="x" * 300))
    assert r.status_code == 400
    assert "About the club" not in admin.get(PAGES).text


def test_a_300_character_slug_is_refused_on_rename(client_as):
    admin = client_as("admin")
    pid = make_page(admin)
    assert post(admin, f"{PAGES}/{pid}", **page_form(slug="x" * 300)
                ).status_code == 400


def test_the_slug_limit_is_80_characters(client_as):
    admin = client_as("admin")
    assert post(admin, PAGES, **page_form(slug="x" * 81)).status_code == 400
    assert post(admin, PAGES, **page_form(slug="x" * 80)).status_code == 303


@pytest.mark.parametrize("slug", ["..", "a/b", "trips", "x" * 300])
def test_render_site_refuses_a_bad_page_slug_and_leaves_site_alone(
        database, tmp_path, slug):
    owner = rows("SELECT id FROM account WHERE email = ?",
                 DEMO_USERS["admin"]["email"])[0]["id"]
    good = pages.create_page(owner, "Good page", "good", "ok", 1)
    bad = pages.create_page(owner, "Bad page", slug, "oops", 2)
    for pid in (good, bad):  # straight into the table: the routes would refuse
        pages.transition(pid, "publish")
    out = tmp_path / "site"
    out.mkdir()
    (out / "keep.txt").write_text("previous deploy")

    with pytest.raises(PublishRefused) as refusal:
        render_site(out)

    assert "Bad page" in str(refusal.value)
    assert (out / "keep.txt").read_text() == "previous deploy"
    assert not (out / "good").exists()


def test_deleting_a_published_page_shows_the_still_live_notice(client_as):
    admin = client_as("admin")
    pid = make_page(admin, published=True)
    r = post(admin, f"{PAGES}/{pid}/delete")
    assert LIVE_NOTICE in follow(admin, r).text


def test_deleting_a_draft_page_shows_no_notice(client_as):
    admin = client_as("admin")
    pid = make_page(admin)
    r = post(admin, f"{PAGES}/{pid}/delete")
    assert LIVE_NOTICE not in follow(admin, r).text
