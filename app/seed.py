"""Demo Accounts, shared by scripts/seed_demo.py and the test fixtures."""
from __future__ import annotations

from app import accounts, db, trips

ADMIN_EMAIL = "admin@example.test"
EDITOR_EMAIL = "editor@example.test"


def seed_accounts(admin_password: str, editor_password: str) -> None:
    """Create the demo Admin and Editor. Safe to run again."""
    db.init_db()
    accounts.create_account(ADMIN_EMAIL, "Demo Admin", 2027, "admin",
                            admin_password)
    accounts.create_account(EDITOR_EMAIL, "Demo Editor", 2028, "editor",
                            editor_password)


DEMO_TRIP = {"conference": "Chicago International MUN", "city": "Chicago",
             "start_date": "2026-03-05", "end_date": "2026-03-08",
             "summary": "Four days of committee work in Chicago.",
             "slug": "2026-chicago"}

# (slug, title, status, owner role)
DEMO_RECAPS = [
    ("chicago-food-crawl", "Chicago food crawl", "published", "editor"),
    ("committee-night-one", "Committee, night one", "submitted", "editor"),
    ("lost-in-the-loop", "Lost in the Loop", "draft", "editor"),
]

# (slug, title, status, nav position)
DEMO_PAGES = [
    ("about", "About the club", "published", 1),
    ("officers", "Officers and contact", "draft", 2),
]


def seed_content() -> None:
    """Create a Trip, a Recap in each status and a Draft and a Published Page,
    owned by the demo Accounts. All or nothing: it is one transaction, so a
    failure part-way leaves nothing and a re-run seeds fully. Safe to run
    again: it does nothing once the demo Trip exists."""
    stamp = "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM trip WHERE slug = ?",
                        (DEMO_TRIP["slug"],)).fetchone():
            return
        ids = {r["email"]: (r["id"], r["name"], r["class_year"])
               for r in conn.execute("SELECT * FROM account")}
        admin_id = ids[ADMIN_EMAIL][0]
        editor_id, editor_name, editor_year = ids[EDITOR_EMAIL]

        fields = list(trips.FIELDS)
        trip_id = conn.execute(
            f"INSERT INTO trip ({', '.join(fields)}) "
            f"VALUES ({', '.join('?' for _ in fields)})",
            [DEMO_TRIP[f] for f in fields]).lastrowid
        for slug, title, status, _ in DEMO_RECAPS:
            published_at = stamp if status == "published" else "NULL"
            conn.execute(
                "INSERT INTO recap (trip_id, owner_id, title, slug, body, "
                "byline_name, byline_class_year, status, published_at) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, {published_at})",
                (trip_id, editor_id, title, slug,
                 f"We landed at O'Hare and **{title.lower()}** began.",
                 editor_name, editor_year, status))
        for slug, title, status, position in DEMO_PAGES:
            conn.execute(
                "INSERT INTO page (owner_id, title, slug, body, nav_position, "
                "status) VALUES (?, ?, ?, ?, ?, ?)",
                (admin_id, title, slug, f"This is the {title.lower()} page.",
                 position, status))
