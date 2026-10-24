"""Site state: the single record of when `cms publish` last rendered the Public
site, and the "changes not yet live" check that compares it with content edits."""
from __future__ import annotations

import sqlite3

from app import db

_NOW = "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"


def record_render() -> None:
    """Stamp now as the time the Public site was last rendered."""
    db.init_db()
    with db.connect() as conn:
        conn.execute(
            f"INSERT INTO site_state (id, last_rendered_at) VALUES (1, {_NOW}) "
            f"ON CONFLICT (id) DO UPDATE SET last_rendered_at = {_NOW}")


def last_rendered() -> str | None:
    """When the Public site was last rendered, or None if it never has."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT last_rendered_at FROM site_state WHERE id = 1").fetchone()
    return row["last_rendered_at"] if row else None


def note_removal(conn: sqlite3.Connection) -> None:
    """Record that a Trip, Recap or Page was deleted. A deleted row leaves no
    edit time behind, so the removal is stamped on the Site state instead. Call
    it on the connection that does the DELETE so the two commit together."""
    conn.execute(
        f"INSERT INTO site_state (id, content_changed_at) VALUES (1, {_NOW}) "
        f"ON CONFLICT (id) DO UPDATE SET content_changed_at = {_NOW}")


def changes_not_live() -> bool:
    """True if any Trip, Recap or Page changed since `cms publish` last ran.

    Known limit: every stamp has one-second precision, so a change made in the
    same second as the render counts as already rendered, and an edit that
    lands in that second after the render is missed until the next change.
    The other choice, counting ties as changes, would leave the notice up
    forever after the render that made it.
    """
    with db.connect() as conn:
        row = conn.execute(
            "SELECT last_rendered_at, content_changed_at FROM site_state "
            "WHERE id = 1").fetchone()
        rendered = row["last_rendered_at"] if row else None
        if rendered is None:
            # Never rendered: anything at all in the database is not yet live.
            return bool(row and row["content_changed_at"]) or any(
                conn.execute(f"SELECT EXISTS (SELECT 1 FROM {table})")
                .fetchone()[0] for table in ("trip", "recap", "page"))
        if row["content_changed_at"] and row["content_changed_at"] > rendered:
            return True
        return bool(conn.execute(
            "SELECT EXISTS (SELECT 1 FROM trip WHERE edited_at > ? "
            "OR created_at > ?) OR EXISTS (SELECT 1 FROM recap WHERE "
            "edited_at > ? OR created_at > ? OR published_at > ?) "
            "OR EXISTS (SELECT 1 FROM page WHERE edited_at > ? "
            "OR created_at > ?)",
            (rendered,) * 7).fetchone()[0])
