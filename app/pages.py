"""Pages: standing, text-only content about the club. Admins manage them."""
from __future__ import annotations

import sqlite3

from app import db
from app.slugs import is_url_safe

# Slugs the Public site already uses for something else.
RESERVED_SLUGS = frozenset({"trips", "images", "admin", "login"})
# A Slug becomes a folder name in site/, which filesystems cap near 255 bytes.
MAX_SLUG_LENGTH = 80
# SQLite stores integers in 64 bits.
NAV_POSITION_RANGE = range(-2**63, 2**63)


def is_valid_slug(slug: str) -> bool:
    """True if slug is safe to write as a folder in site/."""
    return (is_url_safe(slug) and len(slug) <= MAX_SLUG_LENGTH
            and slug not in RESERVED_SLUGS)


def parse_nav_position(text: str) -> int | None:
    """The whole number in text, or None if it is not one that fits in 64 bits."""
    try:
        number = int(text.strip())
    except ValueError:
        return None
    return number if number in NAV_POSITION_RANGE else None


class SlugTaken(ValueError):
    """Another Page already uses this Slug."""


class TransitionRefused(ValueError):
    """The Page is not in a status this action can start from."""


# action -> (status it may start from, status it ends in).
TRANSITIONS: dict[str, tuple[str, str]] = {
    "publish": ("draft", "published"),
    "unpublish": ("published", "draft"),
}

_PAGE_WITH_OWNER = ("SELECT page.*, account.name AS owner_name FROM page "
                    "JOIN account ON account.id = page.owner_id ")


def get_page(page_id: int) -> sqlite3.Row | None:
    """One Page with its Owner's name, or None."""
    with db.connect() as conn:
        return conn.execute(_PAGE_WITH_OWNER + "WHERE page.id = ?",
                            (page_id,)).fetchone()


def list_pages(status: str | None = None) -> list[sqlite3.Row]:
    """Pages with their Owner's name, in nav order; only `status` if given."""
    with db.connect() as conn:
        return conn.execute(
            _PAGE_WITH_OWNER + "WHERE (? IS NULL OR page.status = ?) "
            "ORDER BY page.nav_position, page.title, page.id",
            (status, status)).fetchall()


def create_page(owner_id: int, title: str, slug: str, body: str,
                nav_position: int) -> int:
    """Insert a Draft Page; return its id. The Body is stored as written.
    Raises SlugTaken; the UNIQUE constraint decides."""
    try:
        with db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO page (owner_id, title, slug, body, nav_position) "
                "VALUES (?, ?, ?, ?, ?)",
                (owner_id, title, slug, body, nav_position))
            return cur.lastrowid
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" not in str(exc):
            raise
        raise SlugTaken(slug) from exc


def update_page(page_id: int, title: str, slug: str, body: str,
                nav_position: int) -> None:
    """Overwrite a Page's editable fields and stamp the edit time. The Owner,
    status and created time never change here. Raises SlugTaken."""
    try:
        with db.connect() as conn:
            conn.execute(
                "UPDATE page SET title = ?, slug = ?, body = ?, "
                "nav_position = ?, "
                "edited_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
                "WHERE id = ?", (title, slug, body, nav_position, page_id))
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" not in str(exc):
            raise
        raise SlugTaken(slug) from exc


def delete_page(page_id: int) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM page WHERE id = ?", (page_id,))


def transition(page_id: int, action: str) -> None:
    """Publish or Unpublish. The status is checked inside the UPDATE, so two
    simultaneous requests cannot both move it. Raises TransitionRefused."""
    from_status, to_status = TRANSITIONS[action]
    with db.connect() as conn:
        cur = conn.execute("UPDATE page SET status = ? WHERE id = ? "
                           "AND status = ?", (to_status, page_id, from_status))
        if cur.rowcount == 0:
            raise TransitionRefused(action)
