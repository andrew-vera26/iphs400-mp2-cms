"""Recaps: one member's account of one Trip, and the status machine that moves
them from Draft to Published."""
from __future__ import annotations

import sqlite3

from app import db


class RecapLocked(ValueError):
    """An Editor's write found the Recap no longer their own Draft."""


class SlugTaken(ValueError):
    """Another Recap on this Trip already uses this Slug."""


# Appended to an Editor's write so the write itself checks what the policy
# checked a moment earlier; the Recap may have been Submitted in between.
_EDITOR_DRAFT_ONLY = " AND status = 'draft' AND owner_id = ?"


def get_recap(recap_id: int) -> sqlite3.Row | None:
    """One Recap with its Owner's name, or None."""
    with db.connect() as conn:
        return conn.execute(
            "SELECT recap.*, account.name AS owner_name FROM recap "
            "JOIN account ON account.id = recap.owner_id WHERE recap.id = ?",
            (recap_id,)).fetchone()


def update_recap(recap_id: int, trip_id: int, title: str, slug: str, body: str,
                 byline_name: str, byline_class_year: int,
                 editor_id: int | None = None) -> None:
    """Overwrite a Recap's editable fields and stamp the edit time. The Owner,
    status and created time never change here. Raises SlugTaken on a clash.

    Pass `editor_id` for an Editor: the write then applies only if that Editor
    still owns a Draft, checked in the UPDATE itself, else RecapLocked."""
    try:
        with db.connect() as conn:
            cur = conn.execute(
                "UPDATE recap SET trip_id = ?, title = ?, slug = ?, body = ?, "
                "byline_name = ?, byline_class_year = ?, "
                "edited_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') "
                f"WHERE id = ?{_EDITOR_DRAFT_ONLY if editor_id else ''}",
                (trip_id, title, slug, body, byline_name, byline_class_year,
                 recap_id, *((editor_id,) if editor_id else ())))
            if editor_id and cur.rowcount == 0:
                raise RecapLocked(recap_id)
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


def delete_recap(recap_id: int, editor_id: int | None = None) -> None:
    """Delete a Recap. Pass `editor_id` for an Editor: it is deleted only if
    that Editor still owns a Draft, checked in the DELETE itself, else
    RecapLocked."""
    with db.connect() as conn:
        cur = conn.execute(
            f"DELETE FROM recap WHERE id = ?"
            f"{_EDITOR_DRAFT_ONLY if editor_id else ''}",
            (recap_id, *((editor_id,) if editor_id else ())))
        if editor_id and cur.rowcount == 0:
            raise RecapLocked(recap_id)


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


class TransitionRefused(ValueError):
    """The Recap is not in a status this action can start from."""


# action -> (statuses it may start from, status it ends in). Who may do each
# action is the policy's business, not this table's.
TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "submit": (("draft",), "submitted"),
    "send-back": (("submitted",), "draft"),
    "publish": (("draft", "submitted"), "published"),
    "unpublish": (("published",), "draft"),
}


# Publishing stamps the time; Unpublishing clears it.
PUBLISHED_AT_SQL = {
    "publish": ", published_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')",
    "unpublish": ", published_at = NULL",
}


def transition(recap_id: int, action: str) -> None:
    """Move a Recap along `action`. The status is checked inside the UPDATE, so
    two simultaneous requests cannot both move it. Raises TransitionRefused."""
    from_statuses, to_status = TRANSITIONS[action]
    marks = ", ".join("?" for _ in from_statuses)
    stamp = PUBLISHED_AT_SQL.get(action, "")
    with db.connect() as conn:
        cur = conn.execute(
            f"UPDATE recap SET status = ?{stamp} WHERE id = ? "
            f"AND status IN ({marks})",
            (to_status, recap_id, *from_statuses))
        if cur.rowcount == 0:
            raise TransitionRefused(action)
