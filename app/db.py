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
    UNIQUE (trip_id, slug)
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


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
