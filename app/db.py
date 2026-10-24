"""SQLite access. The database path is read from settings on every call."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from app import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS account (
    id            INTEGER PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    class_year    INTEGER NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'editor')),
    password_hash TEXT NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS trip (
    id         INTEGER PRIMARY KEY,
    conference TEXT NOT NULL,
    city       TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date   TEXT NOT NULL,
    summary    TEXT NOT NULL,
    slug       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    edited_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS recap (
    id                INTEGER PRIMARY KEY,
    trip_id           INTEGER NOT NULL REFERENCES trip (id),
    owner_id          INTEGER NOT NULL REFERENCES account (id),
    title             TEXT NOT NULL,
    slug              TEXT NOT NULL,
    body              TEXT NOT NULL,
    byline_name       TEXT NOT NULL,
    byline_class_year INTEGER NOT NULL,
    status            TEXT NOT NULL DEFAULT 'draft'
                      CHECK (status IN ('draft', 'submitted', 'published')),
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    edited_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    published_at      TEXT,
    UNIQUE (trip_id, slug)
);

CREATE TABLE IF NOT EXISTS page (
    id           INTEGER PRIMARY KEY,
    owner_id     INTEGER NOT NULL REFERENCES account (id),
    title        TEXT NOT NULL,
    slug         TEXT NOT NULL UNIQUE,
    body         TEXT NOT NULL,
    nav_position INTEGER NOT NULL,
    status       TEXT NOT NULL DEFAULT 'draft'
                 CHECK (status IN ('draft', 'published')),
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    edited_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS image (
    id           INTEGER PRIMARY KEY,
    recap_id     INTEGER NOT NULL REFERENCES recap (id),
    filename     TEXT NOT NULL UNIQUE,
    content_type TEXT NOT NULL,
    size         INTEGER NOT NULL,
    alt          TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS site_state (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    last_rendered_at  TEXT
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a connection; commit on success, roll back on error, always close."""
    conn = sqlite3.connect(settings.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str,
                           definition: str) -> None:
    """CREATE TABLE IF NOT EXISTS never alters a table that already exists, so
    a column added to SCHEMA later is added here for databases made before it."""
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        except sqlite3.OperationalError as exc:
            # Another process started at the same moment and added it first.
            if "duplicate column name" not in str(exc):
                raise


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _add_column_if_missing(conn, "recap", "published_at", "TEXT")
