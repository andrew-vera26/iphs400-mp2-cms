"""Site state: the single record of when `cms publish` last rendered the Public
site. T08's "changes not yet live" notice compares content edit times against it."""
from __future__ import annotations

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
