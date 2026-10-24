"""The admin console is styled and does not overflow a phone screen: every
admin page links one local stylesheet, and every table sits in a wrapper that
scrolls sideways, so the page itself never does."""
import re

import pytest

from tests.conftest import log_in

TABLE_PAGES = ["/admin/recaps", "/admin/trips", "/admin/pages",
               "/admin/accounts"]
STYLESHEET = re.compile(r'<link rel="stylesheet" href="([^"]+)"')


def stylesheet_href(response):
    (href,) = STYLESHEET.findall(response.text)
    return href


@pytest.mark.parametrize("path", ["/login", "/admin", *TABLE_PAGES])
def test_admin_pages_link_the_admin_stylesheet(client_as, path):
    c = client_as("admin")
    href = stylesheet_href(c.get(path))
    assert href.startswith("/") and "//" not in href, href    # local only
    css = c.get(href)
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")


def test_the_stylesheet_has_the_required_parts(client_as):
    c = client_as("admin")
    css = c.get(stylesheet_href(c.get("/admin"))).text
    assert "overflow-x: auto" in css
    assert "@media" in css and "max-width" in css
    assert ":focus-visible" in css
    assert "@import" not in css and "http" not in css       # no CDN, no fonts


@pytest.mark.parametrize("path", TABLE_PAGES)
def test_every_table_is_inside_a_horizontal_scroll_wrapper(client_as, path):
    page = client_as("admin").get(path).text
    tables = page.count("<table")
    assert tables >= 1
    wrapped = re.findall(r'<div class="table-scroll">\s*<table\b.*?</table>\s*</div>',
                         page, re.S)
    assert len(wrapped) == tables


def test_the_scroll_wrapper_is_what_scrolls(client_as):
    c = client_as("admin")
    css = c.get(stylesheet_href(c.get("/admin"))).text
    rule = re.search(r"\.table-scroll\s*\{([^}]*)\}", css)
    assert rule and "overflow-x: auto" in rule.group(1)


def test_no_admin_template_uses_inline_styles():
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "templates"
    offenders = [p.name for p in [root / "base.html",
                                  *(root / "admin").glob("*.html")]
                 if re.search(r"\sstyle=|<style\b", p.read_text())]
    assert not offenders, offenders


def test_static_serves_the_stylesheet_and_nothing_outside_its_folder(client):
    css = client.get("/static/admin.css")
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")
    for path in ("/static/../cms.db", "/static/%2e%2e/cms.db",
                 "/static/%2e%2e/.env", "/static/%2e%2e/main.py",
                 "/static/..%2fcms.db", "/static/admin.css/../../cms.db"):
        r = client.get(path, follow_redirects=True)
        assert r.status_code != 200, path
        assert not r.content.startswith(b"SQLite format 3"), path
