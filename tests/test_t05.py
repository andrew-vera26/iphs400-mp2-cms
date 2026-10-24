"""T05: the Public site for Trips and Recaps.

Seams: `app.publish.render_site(out)` and the `cms publish` command. Content is
set up through the data modules, then the output folder is read back as a reader
would see it.

    index.html                       the home page: Trips with a Published Recap
    trips/<trip>/index.html          a Trip's Summary, then its Published Recaps
    trips/<trip>/<recap>/index.html  one Published Recap
"""
import re
from pathlib import PurePosixPath

import pytest

from app import cli, db, recaps, seed, settings, trips
from app.markdown import render_body
from app.publish import render_site

HOME_PLACEHOLDER = "https://www.instagram.com/REPLACE-ME/"
HOSTILE = ("Hello **world**.\n\n<script>alert(1)</script>\n\n"
           "[evil](https://evil.example/x) ![pic](https://evil.example/p.png)\n\n"
           "Mail [me](mailto:jane@kenyon.edu) or jane@kenyon.edu")


# ---- helpers --------------------------------------------------------------

def make_trip(slug, start, city="Chicago", summary="The overall trip."):
    return trips.create_trip({
        "conference": f"{city} MUN", "city": city, "start_date": start,
        "end_date": start, "summary": summary, "slug": slug})


def make_recap(trip_id, slug, status="published", body="A short anecdote.",
               name="Jane Doe", year=2027, published_at=None):
    """A Recap in `status`; `published_at` pins the Published time so ordering
    does not depend on the clock."""
    with db.connect() as conn:
        owner = conn.execute("SELECT id FROM account WHERE email = ?",
                             (seed.EDITOR_EMAIL,)).fetchone()["id"]
    recap_id = recaps.create_recap(trip_id, owner, f"Title {slug}", slug, body,
                                   name, year)
    if status in ("submitted", "published"):
        recaps.transition(recap_id, "submit")
    if status == "published":
        recaps.transition(recap_id, "publish")
        if published_at:
            with db.connect() as conn:
                conn.execute("UPDATE recap SET published_at = ? WHERE id = ?",
                             (published_at, recap_id))
    return recap_id


def site_files(out):
    return sorted(p for p in out.rglob("*") if p.is_file())


def read(out, rel):
    return (out / rel).read_text()


# ---- addresses ------------------------------------------------------------

def test_writes_home_trip_and_recap_pages_at_index_addresses(database, tmp_path):
    trip = make_trip("2026-chicago", "2026-03-01")
    make_recap(trip, "food-crawl")
    out = render_site(tmp_path / "site")
    assert (out / "index.html").exists()
    assert (out / "trips/2026-chicago/index.html").exists()
    assert (out / "trips/2026-chicago/food-crawl/index.html").exists()


def test_draft_and_submitted_recaps_and_empty_trips_are_absent(database, tmp_path):
    live = make_trip("2026-chicago", "2026-03-01")
    make_recap(live, "shown")
    make_recap(live, "secret-draft", status="draft", body="DRAFT-ONLY-TEXT")
    make_recap(live, "secret-submitted", status="submitted",
               body="SUBMITTED-ONLY-TEXT")
    only_draft = make_trip("2025-boston", "2025-03-01", city="Boston")
    make_recap(only_draft, "unseen", status="draft")
    make_trip("2024-empty", "2024-03-01", city="Empty")

    out = render_site(tmp_path / "site")

    assert (out / "trips/2026-chicago/shown/index.html").exists()
    assert not (out / "trips/2026-chicago/secret-draft").exists()
    assert not (out / "trips/2026-chicago/secret-submitted").exists()
    assert not (out / "trips/2025-boston").exists()
    assert not (out / "trips/2024-empty").exists()
    everything = "".join(p.read_text() for p in site_files(out)
                         if p.suffix == ".html")
    for leaked in ("DRAFT-ONLY-TEXT", "SUBMITTED-ONLY-TEXT", "Boston", "Empty",
                   "secret-draft", "unseen"):
        assert leaked not in everything


def test_unpublished_recap_disappears_on_the_next_run(database, tmp_path):
    trip = make_trip("2026-chicago", "2026-03-01")
    make_recap(trip, "stays")
    going = make_recap(trip, "goes")
    render_site(tmp_path / "site")
    recaps.transition(going, "unpublish")
    out = render_site(tmp_path / "site")
    assert not (out / "trips/2026-chicago/goes").exists()
    assert (out / "trips/2026-chicago/stays/index.html").exists()


# ---- ordering and content -------------------------------------------------

def test_home_lists_trips_newest_start_date_first(database, tmp_path):
    for slug, start, city in [("2025-boston", "2025-03-01", "Boston"),
                              ("2026-chicago", "2026-03-01", "Chicago"),
                              ("2024-dc", "2024-03-01", "Washington")]:
        make_recap(make_trip(slug, start, city=city), "r")
    html = read(render_site(tmp_path / "site"), "index.html")
    positions = [html.index(f'href="trips/{s}/"')
                 for s in ("2026-chicago", "2025-boston", "2024-dc")]
    assert positions == sorted(positions)


def test_trip_page_shows_summary_then_recaps_in_published_order_with_bylines(
        database, tmp_path):
    trip = make_trip("2026-chicago", "2026-03-01",
                     summary="SUMMARY-MARKER we went to Chicago.")
    make_recap(trip, "second", name="Sam Lee", year=2028,
               published_at="2026-03-05T10:00:00Z")
    make_recap(trip, "first", name="Jane Doe", year=2027,
               published_at="2026-03-02T10:00:00Z")
    html = read(render_site(tmp_path / "site"), "trips/2026-chicago/index.html")

    assert html.index("SUMMARY-MARKER") < html.index('href="first/"')
    assert html.index('href="first/"') < html.index('href="second/"')
    assert "by Jane Doe '27" in html
    assert "by Sam Lee '28" in html


def test_recap_page_shows_title_byline_and_rendered_body(database, tmp_path):
    trip = make_trip("2026-chicago", "2026-03-01")
    make_recap(trip, "food-crawl", body="We **landed** at O'Hare.")
    html = read(render_site(tmp_path / "site"),
                "trips/2026-chicago/food-crawl/index.html")
    assert "Title food-crawl" in html
    assert "by Jane Doe '27" in html
    assert "<strong>landed</strong>" in html


# ---- sanitizing -----------------------------------------------------------

def test_hostile_body_is_sanitized_in_the_output(database, tmp_path):
    trip = make_trip("2026-chicago", "2026-03-01")
    make_recap(trip, "bad", body=HOSTILE)
    html = read(render_site(tmp_path / "site"),
                "trips/2026-chicago/bad/index.html")
    assert "<script" not in html and "alert(1)" not in html
    assert "evil.example" not in html
    assert "<strong>world</strong>" in html
    assert "evil" in html  # the link text survives, the link does not


def test_published_body_is_exactly_what_preview_renders(database, tmp_path):
    trip = make_trip("2026-chicago", "2026-03-01")
    make_recap(trip, "bad", body=HOSTILE)
    html = read(render_site(tmp_path / "site"),
                "trips/2026-chicago/bad/index.html")
    assert render_body(HOSTILE) in html


def test_contact_emails_stay_plain_text_with_no_mailto_links(database, tmp_path):
    trip = make_trip("2026-chicago", "2026-03-01")
    make_recap(trip, "bad", body=HOSTILE)
    out = render_site(tmp_path / "site")
    assert "mailto:" not in "".join(p.read_text() for p in site_files(out)
                                    if p.suffix == ".html")
    assert "jane@kenyon.edu" in read(out, "trips/2026-chicago/bad/index.html")


# ---- relative paths -------------------------------------------------------

def test_no_root_absolute_paths_and_nested_links_resolve(database, tmp_path):
    trip = make_trip("2026-chicago", "2026-03-01")
    make_recap(trip, "food-crawl", body="Go [home](../../../index.html).")
    out = render_site(tmp_path / "site")

    for page in site_files(out):
        if page.suffix != ".html":
            continue
        html = page.read_text()
        assert 'href="/' not in html and 'src="/' not in html
        for target in re.findall(r'(?:href|src)="([^"]+)"', html):
            if target.startswith("https://www.instagram.com/"):
                continue
            assert "://" not in target, f"{page}: {target}"
            resolved = (page.parent / target.split("#")[0]).resolve()
            if resolved.is_dir():
                resolved = resolved / "index.html"
            assert resolved.exists(), f"{page.relative_to(out)}: {target}"


def test_stylesheet_reference_is_computed_from_page_depth(database, tmp_path):
    trip = make_trip("2026-chicago", "2026-03-01")
    make_recap(trip, "food-crawl")
    out = render_site(tmp_path / "site")
    for rel, expected in [("index.html", "style.css"),
                          ("trips/2026-chicago/index.html", "../../style.css"),
                          ("trips/2026-chicago/food-crawl/index.html",
                           "../../../style.css")]:
        assert f'href="{expected}"' in read(out, rel), rel


# ---- Instagram footer -----------------------------------------------------

def test_placeholder_instagram_constant_is_committed_in_settings():
    assert settings.INSTAGRAM_URL == HOME_PLACEHOLDER


def test_every_page_has_the_instagram_footer_from_the_constant(
        database, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "INSTAGRAM_URL",
                        "https://www.instagram.com/kenyon-mun/")
    trip = make_trip("2026-chicago", "2026-03-01")
    make_recap(trip, "food-crawl")
    out = render_site(tmp_path / "site")
    pages = [p for p in site_files(out) if p.suffix == ".html"]
    assert len(pages) == 3
    for page in pages:
        assert re.search(
            r'<footer>.*href="https://www\.instagram\.com/kenyon-mun/".*</footer>',
            page.read_text(), re.S), page


# ---- cms publish and the Site state record --------------------------------

def test_cms_publish_writes_site_and_records_when_it_rendered(
        database, tmp_path, monkeypatch):
    from app import site_state
    monkeypatch.setattr(settings, "SITE", tmp_path / "site")
    trip = make_trip("2026-chicago", "2026-03-01")
    make_recap(trip, "food-crawl")
    assert site_state.last_rendered() is None

    assert cli.main(["publish"]) == 0

    assert (tmp_path / "site/trips/2026-chicago/food-crawl/index.html").exists()
    first = site_state.last_rendered()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", first)


def test_each_publish_run_updates_the_one_site_state_record(
        database, tmp_path, monkeypatch):
    from app import site_state
    monkeypatch.setattr(settings, "SITE", tmp_path / "site")
    cli.main(["publish"])
    with db.connect() as conn:
        conn.execute("UPDATE site_state SET last_rendered_at = "
                     "'2000-01-01T00:00:00Z'")
    cli.main(["publish"])
    assert site_state.last_rendered() > "2000-01-01T00:00:00Z"
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM site_state").fetchone()[0] == 1
