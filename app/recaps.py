"""Recaps: one member's account of one Trip. T03 covers Drafts only."""
from __future__ import annotations

import sqlite3

from app import db


class SlugTaken(ValueError):
    """Another Recap on this Trip already uses this Slug."""


def get_recap(recap_id: int) -> sqlite3.Row | None:
    """One Recap with its Owner's name, or None."""
    with db.connect() as conn:
        return conn.execute(
            "SELECT recap.*, account.name AS owner_name FROM recap "
            "JOIN account ON account.id = recap.owner_id WHERE recap.id = ?",
            (recap_id,)).fetchone()


def update_recap(recap_id: int, trip_id: int, title: str, slug: str, body: str,
                 byline_name: str, byline_class_year: int) -> None:
    """Overwrite a Recap's editable fields and stamp the edit time. The Owner,
    status and created time never change here. Raises SlugTaken on a clash."""
    try:
        with db.connect() as conn:
            conn.execute(
                "UPDATE recap SET trip_id = ?, title = ?, slug = ?, body = ?, "
                "byline_name = ?, byline_class_year = ?, "
                "edited_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
                "WHERE id = ?",
                (trip_id, title, slug, body, byline_name, byline_class_year,
                 recap_id))
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" not in str(exc):
            raise
        raise SlugTaken(slug) from exc


def list_recaps(owner_id: int | None = None) -> list[sqlite3.Row]:
    """Recaps with Trip and Owner names, newest first; only owner_id's if given."""
    with db.connect() as conn:
        return conn.execute(
            "SELECT recap.*, trip.conference AS trip_name, "
            "account.name AS owner_name FROM recap "
            "JOIN trip ON trip.id = recap.trip_id "
            "JOIN account ON account.id = recap.owner_id "
            "WHERE (? IS NULL OR recap.owner_id = ?) "
            "ORDER BY recap.created_at DESC, recap.id DESC",
            (owner_id, owner_id)).fetchall()


def delete_recap(recap_id: int) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM recap WHERE id = ?", (recap_id,))


def create_recap(trip_id: int, owner_id: int, title: str, slug: str, body: str,
                 byline_name: str, byline_class_year: int) -> int:
    """Insert a Draft Recap; return its id. The Body is stored as written.

    Raises SlugTaken if the Trip already has a Recap with this Slug. The
    UNIQUE (trip_id, slug) constraint decides, so two simultaneous saves
    cannot both win.
    """
    try:
        with db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO recap (trip_id, owner_id, title, slug, body, "
                "byline_name, byline_class_year) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (trip_id, owner_id, title, slug, body, byline_name,
                 byline_class_year))
            return cur.lastrowid
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" not in str(exc):
            raise
        raise SlugTaken(slug) from exc
