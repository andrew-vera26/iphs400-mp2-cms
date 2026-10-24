"""Dashboard counts. An Editor's numbers are scoped to their own Recaps."""
from __future__ import annotations

from app import db

RECAP_STATUSES = ("draft", "submitted", "published")
PAGE_STATUSES = ("draft", "published")


def _by_status(conn, table: str, statuses: tuple[str, ...],
               owner_id: int | None = None) -> dict[str, int]:
    """Row counts per status for a fixed table name (never user input)."""
    found = {row["status"]: row["n"] for row in conn.execute(
        f"SELECT status, COUNT(*) AS n FROM {table} "
        "WHERE (? IS NULL OR owner_id = ?) GROUP BY status",
        (owner_id, owner_id))}
    return {status: found.get(status, 0) for status in statuses}


def recap_counts(owner_id: int | None = None) -> dict[str, int]:
    """Recaps per status; only owner_id's if given."""
    with db.connect() as conn:
        return _by_status(conn, "recap", RECAP_STATUSES, owner_id)


def admin_counts() -> dict[str, dict[str, int] | int]:
    """Everything the Admin dashboard shows."""
    with db.connect() as conn:
        return {
            "recaps": _by_status(conn, "recap", RECAP_STATUSES),
            "pages": _by_status(conn, "page", PAGE_STATUSES),
            "trips": conn.execute("SELECT COUNT(*) FROM trip").fetchone()[0],
            "accounts": conn.execute(
                "SELECT COUNT(*) FROM account WHERE active = 1").fetchone()[0],
        }
