"""Render the public site into site/ as plain HTML.

T00 publishes a placeholder home page. As you build content types, extend
render_site() to write one file per published item. Two rules the rubric checks:

  1. Only PUBLISHED content is written here. A draft that reaches site/ is a bug.
  2. Every href and src is RELATIVE ("style.css", "posts/x.html"), never
     root-absolute ("/style.css"), because Pages serves this from a subfolder.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import db, images, pages, settings
from app.markdown import images_without_alt, render_body

CSS = """/* Minimal starter styles — make them yours. */
:root { color-scheme: light dark; }
body { font: 16px/1.6 system-ui, sans-serif; margin: 0 auto; max-width: 42rem; padding: 1rem; }
header a { font-weight: 700; text-decoration: none; }
main { margin-block: 2rem; }
"""


class PublishRefused(ValueError):
    """The Public site cannot be rendered; the message says which Recap and why."""


def environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(settings.TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )


def _published_recaps() -> dict[int, list]:
    """Published Recaps by trip id, each list in the order they were Published.
    The only place `cms publish` reads Recaps: nothing else is ever selected."""
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM recap WHERE status = 'published' "
            "ORDER BY published_at, id").fetchall()
    by_trip: dict[int, list] = {}
    for row in rows:
        by_trip.setdefault(row["trip_id"], []).append(row)
    return by_trip


def _published_pages() -> list:
    """Published Pages in Navigation bar order: nav position, then title. The
    only place `cms publish` reads Pages: nothing else is ever selected."""
    with db.connect() as conn:
        return conn.execute(
            "SELECT * FROM page WHERE status = 'published' "
            "ORDER BY nav_position, title, id").fetchall()


def _check_publishable(published: dict[int, list]) -> None:
    """Refuse, naming the Recap, before `site/` is touched: an Image with no alt
    text in a Published Body (it can be edited after Publish), or an Image whose
    uploaded file is gone. Raises PublishRefused."""
    for recaps in published.values():
        for recap in recaps:
            recap_images = images.list_images(recap["id"])
            if images_without_alt(recap["body"], {
                    f"images/{i['filename']}" for i in recap_images}):
                raise PublishRefused(
                    f"Recap '{recap['slug']}' ({recap['title']}) has an image "
                    "without alt text. Add alt text, then publish again.")
            for image in recap_images:
                if not (settings.UPLOADS / image["filename"]).is_file():
                    raise PublishRefused(
                        f"Recap '{recap['slug']}' ({recap['title']}) uses the "
                        f"image {image['filename']}, whose file is missing "
                        f"from {settings.UPLOADS}.")


def _check_page_slugs(live_pages: list) -> None:
    """Refuse, naming the Page, before `site/` is touched: a Published Page
    whose Slug is not safe to write as a folder (the console refuses these,
    but the table does not). Raises PublishRefused."""
    for page in live_pages:
        if not pages.is_valid_slug(page["slug"]):
            raise PublishRefused(
                f"Page '{page['title']}' has the Slug {page['slug']!r}, which "
                "cannot be used as a site address. Fix its Slug, then publish "
                "again.")


def _write(env: Environment, path: Path, template: str, depth: int,
           **context) -> None:
    """Render `template` to `path`, with every link back to the site root
    computed from the page's `depth` below it."""
    root = "../" * depth
    nav = [{"href": f"{root}index.html", "title": "Home"},
           *({"href": f"{root}{page['slug']}/", "title": page["title"]}
             for page in env.globals["nav_pages"])]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(env.get_template(template).render(
        site_title=settings.SITE_TITLE, css_path=f"{root}style.css",
        home_path=f"{root}index.html", nav=nav, instagram_url=settings.INSTAGRAM_URL,
        **context))


def render_site(out: Path | None = None) -> Path:
    out = out or settings.SITE
    published = _published_recaps()
    _check_publishable(published)
    live_pages = _published_pages()
    _check_page_slugs(live_pages)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    env = environment()
    env.globals["nav_pages"] = live_pages
    (out / "style.css").write_text(CSS)

    with db.connect() as conn:
        trips = [t for t in conn.execute(
            "SELECT * FROM trip ORDER BY start_date DESC, id DESC")
            if t["id"] in published]

    _write(env, out / "index.html", "public/home.html", 0,
           title=settings.SITE_TITLE,
           items=[{"href": f"trips/{t['slug']}/", "title": t["conference"],
                   "dates": f"{t['city']}, {t['start_date']}"} for t in trips])
    for page in live_pages:
        _write(env, out / page["slug"] / "index.html", "public/page.html", 1,
               title=page["title"], page=page, body_html=render_body(page["body"]))
    for trip in trips:
        trip_dir = out / "trips" / trip["slug"]
        _write(env, trip_dir / "index.html", "public/trip.html", 2,
               title=trip["conference"], trip=trip,
               recaps=published[trip["id"]])
        for recap in published[trip["id"]]:
            page_dir = trip_dir / recap["slug"]
            recap_images = images.list_images(recap["id"])
            _write(env, page_dir / "index.html",
                   "public/recap.html", 3, title=recap["title"], trip=trip,
                   recap=recap, body_html=render_body(
                       recap["body"], {f"images/{i['filename']}"
                                       for i in recap_images}))
            for image in recap_images:
                (page_dir / "images").mkdir(exist_ok=True)
                shutil.copy2(settings.UPLOADS / image["filename"],
                             page_dir / "images" / image["filename"])
    return out
