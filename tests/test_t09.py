"""T09: seed data, `cms backup` and the final route audit.

Seams: the seed script as a process (exit code and output, with the
environment it documents); the HTTP app (TestClient) for what the seeded data
looks like to a console user; `render_site` and `main(argv)` for the CLI.

Contract the tests read (the ticket leaves it open):

* `cms backup <folder>` creates the folder if it is missing, and writes one
  `cms-backup-<YYYYMMDD-HHMM>.zip` in it. The archive holds the database as
  one SQLite file at its top level, and every uploaded Image under `uploads/`.
  Without an uploads folder it still holds the database.
* A folder inside the repository (or reached through a symlink into it) is
  refused: non-zero exit, a message naming the repository, nothing written and
  no folder created.
* `cms publish` prints a PublishRefused message and returns non-zero. It
  records no render, so "changes not yet live" does not turn off.
* The anonymous sweep and the CSRF sweep take their routes from the app's own
  OpenAPI schema, so a route added later is swept without editing the test.
"""
import html
import io
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import cli, seed, settings, site_state
from app.main import create_app
from app.publish import render_site
from tests.conftest import csrf_from, log_in
from tests.test_t06 import existing_site, published_recap_with_image
from tests.test_t08 import counts

ROOT = settings.ROOT
SCRIPT = ROOT / "scripts" / "seed_demo.py"
ARCHIVE = re.compile(r"^cms-backup-\d{8}-\d{4}\.zip$")


# ---- seed script ----------------------------------------------------------

def env_example():
    """The values a fresh clone gets from `cp .env.example .env`."""
    values = {}
    for line in (ROOT / ".env.example").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def run_seed(tmp_path, **overrides):
    """Run scripts/seed_demo.py in a clean environment with the .env.example
    passwords, a database and uploads folder inside tmp_path."""
    example = env_example()
    env = {k: v for k, v in os.environ.items() if not k.startswith("CMS_")}
    env.update({
        "PYTHONPATH": str(ROOT),
        "CMS_ADMIN_PASSWORD": example["CMS_ADMIN_PASSWORD"],
        "CMS_EDITOR_PASSWORD": example["CMS_EDITOR_PASSWORD"],
        "CMS_DATABASE": str(tmp_path / "seeded.db"),
        "CMS_UPLOADS": str(tmp_path / "uploads"),
    })
    env.update(overrides)
    env = {k: v for k, v in env.items() if v is not None}
    return subprocess.run([sys.executable, str(SCRIPT)], env=env, cwd=ROOT,
                          capture_output=True, text=True)


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    """The seed script run once on a fresh database; the app pointed at it."""
    result = run_seed(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    monkeypatch.setattr(settings, "DATABASE_PATH", tmp_path / "seeded.db")
    monkeypatch.setattr(settings, "UPLOADS", tmp_path / "uploads")
    return tmp_path


def seeded_admin():
    c = TestClient(create_app())
    pw = env_example()["CMS_ADMIN_PASSWORD"]
    assert log_in(c, seed.ADMIN_EMAIL, pw).status_code in (302, 303)
    return c


def titles(c, path, status):
    page = c.get(path, params={"status": status}).text
    link = re.compile(r'<a href="/admin/(?:recaps|pages)/\d+">([^<]*)</a>')
    return [html.unescape(t) for t in link.findall(page)]


def test_env_example_parses_under_uv_env_file():
    """`uv run --env-file .env` stops reading at a value it cannot parse, so an
    unquoted value with spaces silently drops every variable after it."""
    bad = [line for line in (ROOT / ".env.example").read_text().splitlines()
           if line.strip() and not line.lstrip().startswith("#")
           and not re.fullmatch(r"[A-Z_]+=(\S*|\"[^\"]*\")", line)]
    assert not bad, bad


def test_seed_on_a_fresh_database_creates_one_of_everything(seeded):
    c = seeded_admin()
    dashboard = counts(c.get("/admin").text)
    assert dashboard["accounts-active"] == 2
    assert dashboard["trips"] >= 1
    for key in ("recaps-draft", "recaps-submitted", "recaps-published",
                "pages-draft", "pages-published"):
        assert dashboard[key] >= 1, key


def test_seeded_accounts_log_in_with_the_env_example_passwords(seeded):
    example = env_example()
    for email, pw in ((seed.ADMIN_EMAIL, example["CMS_ADMIN_PASSWORD"]),
                      (seed.EDITOR_EMAIL, example["CMS_EDITOR_PASSWORD"])):
        assert log_in(TestClient(create_app()), email, pw
                      ).status_code in (302, 303)


def test_passwords_come_from_the_environment_only(tmp_path, monkeypatch):
    result = run_seed(tmp_path, CMS_ADMIN_PASSWORD="distinct-admin-pw-7",
                      CMS_EDITOR_PASSWORD="distinct-editor-pw-7")
    assert result.returncode == 0, result.stdout + result.stderr
    monkeypatch.setattr(settings, "DATABASE_PATH", tmp_path / "seeded.db")
    ok = log_in(TestClient(create_app()), seed.ADMIN_EMAIL,
                "distinct-admin-pw-7")
    assert ok.status_code in (302, 303)
    stale = log_in(TestClient(create_app()), seed.ADMIN_EMAIL,
                   env_example()["CMS_ADMIN_PASSWORD"])
    assert stale.status_code == 401


def test_running_the_seed_twice_changes_nothing(seeded):
    before = counts(seeded_admin().get("/admin").text)
    again = run_seed(seeded)
    assert again.returncode == 0, again.stdout + again.stderr
    assert counts(seeded_admin().get("/admin").text) == before


@pytest.mark.parametrize("missing", [
    ["CMS_ADMIN_PASSWORD"], ["CMS_EDITOR_PASSWORD"],
    ["CMS_ADMIN_PASSWORD", "CMS_EDITOR_PASSWORD"]])
@pytest.mark.parametrize("blank", [False, True])
def test_seed_without_a_password_exits_nonzero_and_says_which(
        tmp_path, missing, blank):
    result = run_seed(tmp_path, **{name: ("" if blank else None)
                                   for name in missing})
    out = result.stdout + result.stderr
    assert result.returncode != 0
    assert all(name in out for name in missing), out
    assert "Traceback" not in out
    assert not (tmp_path / "seeded.db").exists()


@pytest.mark.parametrize("name", ["CMS_ADMIN_PASSWORD", "CMS_EDITOR_PASSWORD"])
@pytest.mark.parametrize("value", ["   ", "\t\n"])
def test_seed_with_a_whitespace_only_password_counts_as_missing(
        tmp_path, name, value):
    result = run_seed(tmp_path, **{name: value})
    out = result.stdout + result.stderr
    assert result.returncode != 0
    assert name in out, out
    assert "Traceback" not in out
    assert not (tmp_path / "seeded.db").exists()


def test_a_seed_that_fails_part_way_leaves_nothing_and_a_rerun_seeds_fully(
        database):
    from app import db, pages
    with db.connect() as conn:
        admin_id = conn.execute("SELECT id FROM account WHERE email = ?",
                                (seed.ADMIN_EMAIL,)).fetchone()["id"]
    # The second demo Page's Slug is taken, so seeding fails after the Trip and
    # the Recaps were already written.
    blocker = pages.create_page(admin_id, "Blocker", "officers", "x", 9)

    with pytest.raises(Exception):
        seed.seed_content()

    def rows():
        with db.connect() as conn:
            return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ("trip", "recap", "page")}
    assert rows() == {"trip": 0, "recap": 0, "page": 1}

    with db.connect() as conn:
        conn.execute("DELETE FROM page WHERE id = ?", (blocker,))
    seed.seed_content()
    assert rows() == {"trip": 1, "recap": 3, "page": 2}


def test_cms_publish_after_seeding_writes_published_content_only(
        seeded, monkeypatch):
    c = seeded_admin()
    by_status = {s: titles(c, "/admin/recaps", s)
                 for s in ("draft", "submitted", "published")}
    page_by_status = {s: titles(c, "/admin/pages", s)
                      for s in ("draft", "published")}
    every = [t for ts in (*by_status.values(), *page_by_status.values())
             for t in ts]
    assert all(by_status.values()) and all(page_by_status.values())
    assert len(every) == len(set(every)), "seeded titles must be distinct"

    site = seeded / "site"
    monkeypatch.setattr(settings, "SITE", site)
    assert cli.main(["publish"]) == 0
    written = "\n".join(html.unescape(p.read_text())
                        for p in site.rglob("*.html"))
    for title in by_status["published"] + page_by_status["published"]:
        assert title in written, title
    for title in (by_status["draft"] + by_status["submitted"]
                  + page_by_status["draft"]):
        assert title not in written, title


# ---- cms publish ----------------------------------------------------------

def test_cms_publish_prints_a_refusal_instead_of_a_traceback(
        client_as, tmp_path, monkeypatch, capsys):
    _, recap_id, name = published_recap_with_image(client_as)
    from app import db
    with db.connect() as conn:
        conn.execute("UPDATE recap SET body = ? WHERE id = ?",
                     (f"![](images/{name})", recap_id))
    out = existing_site(tmp_path)
    monkeypatch.setattr(settings, "SITE", out)

    assert cli.main(["publish"]) != 0

    shown = capsys.readouterr()
    text = shown.out + shown.err
    assert "cms publish refused" in text
    assert "food-crawl" in text and "alt text" in text.lower()
    assert "Traceback" not in text
    assert (out / "marker.txt").read_text() == "previous render"
    assert site_state.last_rendered() is None


# ---- cms backup -----------------------------------------------------------

@pytest.fixture
def uploads_dir(tmp_path, monkeypatch):
    folder = tmp_path / "uploads"
    folder.mkdir()
    (folder / "aaaa1111aaaa1111.png").write_bytes(b"\x89PNG one")
    (folder / "bbbb2222bbbb2222.jpg").write_bytes(b"\xff\xd8 two")
    monkeypatch.setattr(settings, "UPLOADS", folder)
    return folder


def test_backup_writes_one_dated_archive_with_the_database_and_images(
        database, uploads_dir, tmp_path):
    out = tmp_path / "private" / "backups"          # does not exist yet

    assert cli.main(["backup", str(out)]) == 0

    (archive,) = list(out.iterdir())
    assert ARCHIVE.match(archive.name), archive.name
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        images = {n: z.read(n) for n in names if n.startswith("uploads/")}
        (db_name,) = [n for n in names
                      if not n.startswith("uploads/") and not n.endswith("/")]
        db_bytes = z.read(db_name)
    assert images == {"uploads/aaaa1111aaaa1111.png": b"\x89PNG one",
                      "uploads/bbbb2222bbbb2222.jpg": b"\xff\xd8 two"}
    restored = tmp_path / "restored.db"
    restored.write_bytes(db_bytes)
    emails = {r[0] for r in sqlite3.connect(restored).execute(
        "SELECT email FROM account")}
    assert emails == {seed.ADMIN_EMAIL, seed.EDITOR_EMAIL}


def test_backup_without_an_uploads_folder_still_saves_the_database(
        database, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOADS", tmp_path / "never-created")
    out = tmp_path / "out"
    assert cli.main(["backup", str(out)]) == 0
    (archive,) = list(out.iterdir())
    with zipfile.ZipFile(archive) as z:
        assert len(z.namelist()) == 1


def stray_archives():
    return {*ROOT.glob("cms-backup-*.zip"),
            *(ROOT / "docs").glob("cms-backup-*.zip")}


@pytest.mark.parametrize("inside,made", [
    # (folder asked for, the top folder a wrong implementation would create)
    (ROOT / "cms-backups-t09-probe", ROOT / "cms-backups-t09-probe"),
    (ROOT / "docs" / "t09-probe" / "deeper", ROOT / "docs" / "t09-probe"),
    (ROOT / "docs", None),                    # an existing repo folder
    (ROOT, None),                             # the repo itself
])
def test_backup_inside_the_repository_is_refused(
        database, uploads_dir, inside, made, capsys):
    before = stray_archives()
    try:
        assert cli.main(["backup", str(inside)]) != 0
        shown = capsys.readouterr()
        assert "repository" in (shown.out + shown.err).lower()
        if made:
            assert not inside.exists(), "refused, yet the folder was created"
        assert stray_archives() == before
    finally:
        if made:
            shutil.rmtree(made, ignore_errors=True)
        for created in stray_archives() - before:
            created.unlink()


def test_backup_inside_the_repository_is_refused_whatever_the_case(
        database, uploads_dir, capsys):
    swapped = ROOT.parent / ROOT.name.swapcase()
    if not swapped.exists():
        pytest.skip("case-sensitive filesystem")
    probe = swapped / "t09-case-probe"
    try:
        assert cli.main(["backup", str(probe)]) != 0
        shown = capsys.readouterr()
        assert "repository" in (shown.out + shown.err).lower()
        assert not (ROOT / "t09-case-probe").exists()
    finally:
        shutil.rmtree(ROOT / "t09-case-probe", ignore_errors=True)


def test_backup_through_a_symlink_into_the_repository_is_refused(
        database, uploads_dir, tmp_path, capsys):
    link = tmp_path / "looks-outside"
    link.symlink_to(ROOT / "docs", target_is_directory=True)
    assert cli.main(["backup", str(link / "nested")]) != 0
    shown = capsys.readouterr()
    assert "repository" in (shown.out + shown.err).lower()
    assert not list((ROOT / "docs").rglob("cms-backup-*.zip"))
    assert not (ROOT / "docs" / "nested").exists()


def test_backup_without_a_database_refuses_and_creates_nothing(
        tmp_path, monkeypatch, capsys):
    absent = tmp_path / "absent.db"
    monkeypatch.setattr(settings, "DATABASE_PATH", absent)
    out = tmp_path / "out"

    assert cli.main(["backup", str(out)]) == 1

    shown = capsys.readouterr()
    text = (shown.out + shown.err).lower()
    assert "database" in text and "does not exist" in text
    assert "traceback" not in text
    assert not absent.exists(), "a stray empty database was created"
    assert not out.exists()


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 24, 12, 0)


def test_backup_refuses_to_overwrite_an_archive_of_the_same_name(
        database, uploads_dir, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "datetime", FixedClock)
    out = tmp_path / "out"
    assert cli.main(["backup", str(out)]) == 0
    (first,) = list(out.iterdir())
    assert first.name == "cms-backup-20261024-1200.zip"
    original = first.read_bytes()
    (uploads_dir / "cccc3333cccc3333.png").write_bytes(b"\x89PNG three")
    capsys.readouterr()

    assert cli.main(["backup", str(out)]) == 1

    shown = capsys.readouterr()
    text = shown.out + shown.err
    assert "already exists" in text and first.name in text
    assert list(out.iterdir()) == [first]
    assert first.read_bytes() == original


def test_a_failed_backup_leaves_no_partial_archive(
        database, uploads_dir, tmp_path, monkeypatch):
    real_write = zipfile.ZipFile.write
    calls = []

    def flaky(self, *args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise OSError("disk full")
        return real_write(self, *args, **kwargs)
    monkeypatch.setattr(zipfile.ZipFile, "write", flaky)
    out = tmp_path / "out"

    with pytest.raises(OSError):
        cli.backup(out)

    assert len(calls) >= 2, "the failure was never reached"
    assert list(out.iterdir()) == [], "a partial file was left behind"


def test_backup_skips_symlinks_in_uploads_and_says_so(
        database, uploads_dir, tmp_path, capsys):
    outside = tmp_path / "outside-secret.txt"
    outside.write_bytes(b"TOP SECRET")
    (uploads_dir / "sneaky.png").symlink_to(outside)
    out = tmp_path / "out"

    assert cli.main(["backup", str(out)]) == 0

    shown = capsys.readouterr()
    text = shown.out + shown.err
    assert "sneaky.png" in text and "skip" in text.lower()
    (archive,) = list(out.iterdir())
    with zipfile.ZipFile(archive) as z:
        assert "uploads/sneaky.png" not in z.namelist()
        assert not any(b"TOP SECRET" in z.read(n) for n in z.namelist())
        assert "uploads/aaaa1111aaaa1111.png" in z.namelist()


def test_backup_archives_are_gitignored():
    for path in ("cms-backup-20261024-1200.zip",
                 "backups/cms-backup-20261024-1200.zip"):
        r = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
        assert r.returncode == 0, f"{path} is not gitignored"


# ---- final route audit ----------------------------------------------------

def swept_routes(app, prefix=""):
    """(method, concrete path) for every route in the app's own OpenAPI schema
    under `prefix`, path parameters filled with plausible values."""
    found = []
    for path, item in app.openapi()["paths"].items():
        if not path.startswith(prefix):
            continue
        concrete = re.sub(r"\{filename\}", "x.png", path)
        concrete = re.sub(r"\{[^}]+\}", "1", concrete)
        found += [(m.upper(), concrete) for m in item
                  if m in ("get", "post", "put", "patch", "delete")]
    return sorted(found)


def test_the_sweep_sees_the_whole_console():
    routes = swept_routes(create_app(), "/admin")
    assert len(routes) >= 35, routes
    assert ("GET", "/admin") in routes
    assert ("POST", "/admin/recaps/1/images/1/delete") in routes
    assert ("GET", "/admin/recaps/1/images/x.png") in routes


def test_every_console_route_sends_an_anonymous_visitor_to_login(client):
    token = csrf_from(client.get("/login"))     # a session with no Account
    app_routes = swept_routes(client.app, "/admin")
    failures = []
    for method, path in app_routes:
        r = client.request(method, path, data={"csrf_token": token},
                           follow_redirects=False)
        if not (r.status_code in (302, 303)
                and r.headers.get("location") == "/login"):
            failures.append((method, path, r.status_code))
    assert not failures, failures


def test_every_post_route_refuses_a_missing_or_wrong_csrf_token(client_as):
    c = client_as("admin")
    posts = [(m, p) for m, p in swept_routes(c.app) if m == "POST"]
    assert len(posts) >= 25, posts
    failures = []
    for method, path in posts:
        for data in ({}, {"csrf_token": "wrong"}):
            r = c.request(method, path, data=data, follow_redirects=False)
            if r.status_code != 403:
                failures.append((method, path, data, r.status_code))
    assert not failures, failures
    assert c.get("/admin").status_code == 200       # still signed in


def test_every_console_form_in_the_templates_carries_the_token():
    bare = []
    for template in sorted((ROOT / "templates").rglob("*.html")):
        text = template.read_text()
        for form in re.finditer(r"<form\b(.*?)</form>", text, re.S | re.I):
            if re.search(r'method="post"', form.group(1), re.I) \
                    and 'name="csrf_token"' not in form.group(1):
                bare.append(template.name)
    assert not bare, bare
