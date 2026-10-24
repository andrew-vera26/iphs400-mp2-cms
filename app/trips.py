"""Trips: the conferences the club travelled to. Admins manage them."""
from __future__ import annotations

import re
import sqlite3
from datetime import date

from app import db, site_state

FIELDS = ("conference", "city", "start_date", "end_date", "summary", "slug")


def parse_date(text: str) -> date | None:
    """The date for a strict YYYY-MM-DD string, or None if it is not a real
    calendar date."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text, re.ASCII):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


class SlugTaken(ValueError):
    """Another Trip already uses this Slug."""


def create_trip(values: dict[str, str]) -> int:
    """Insert a Trip from the six form fields; return its id.

    Raises SlugTaken if the Slug is in use. The UNIQUE constraint decides, so
    two simultaneous saves cannot both win.
    """
    try:
        with db.connect() as conn:
            cur = conn.execute(
                f"INSERT INTO trip ({', '.join(FIELDS)}) "
                f"VALUES ({', '.join('?' for _ in FIELDS)})",
                [values[f] for f in FIELDS])
            return cur.lastrowid
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" not in str(exc):
            raise
        raise SlugTaken(values["slug"]) from exc


def get_trip(trip_id: int) -> sqlite3.Row | None:
    with db.connect() as conn:
        return conn.execute("SELECT * FROM trip WHERE id = ?",
                            (trip_id,)).fetchone()


def update_trip(trip_id: int, values: dict[str, str]) -> bool:
    """Overwrite a Trip's six fields. False if there is no such Trip; raises
    SlugTaken if another Trip uses the Slug."""
    try:
        with db.connect() as conn:
            cur = conn.execute(
                f"UPDATE trip SET {', '.join(f + ' = ?' for f in FIELDS)}, "
                "edited_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
                "WHERE id = ?",
                [values[f] for f in FIELDS] + [trip_id])
            return cur.rowcount == 1
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" not in str(exc):
            raise
        raise SlugTaken(values["slug"]) from exc


def delete_trip(trip_id: int) -> bool:
    """Delete a Trip that has no Recaps. False if nothing was deleted: there is
    no such Trip, or it still has Recaps. One statement, so a Recap saved at the
    same moment cannot be orphaned."""
    with db.connect() as conn:
        deleted = conn.execute(
            "DELETE FROM trip WHERE id = ? AND NOT EXISTS "
            "(SELECT 1 FROM recap WHERE recap.trip_id = trip.id)",
            (trip_id,)).rowcount == 1
        if deleted:
            site_state.note_removal(conn)
        return deleted


def list_trips() -> list[sqlite3.Row]:
    """All Trips, newest start date first."""
    with db.connect() as conn:
        return conn.execute(
            "SELECT * FROM trip ORDER BY start_date DESC, id DESC").fetchall()
