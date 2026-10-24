"""Demo Accounts, shared by scripts/seed_demo.py and the test fixtures."""
from __future__ import annotations

from app import accounts, db

ADMIN_EMAIL = "admin@example.test"
EDITOR_EMAIL = "editor@example.test"


def seed_accounts(admin_password: str, editor_password: str) -> None:
    """Create the demo Admin and Editor. Safe to run again."""
    db.init_db()
    accounts.create_account(ADMIN_EMAIL, "Demo Admin", 2027, "admin",
                            admin_password)
    accounts.create_account(EDITOR_EMAIL, "Demo Editor", 2028, "editor",
                            editor_password)
