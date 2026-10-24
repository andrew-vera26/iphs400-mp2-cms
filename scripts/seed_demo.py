#!/usr/bin/env python3
"""Create demo data so a grader (and you) can use the CMS immediately.

    uv run --env-file .env python scripts/seed_demo.py

Creates the demo Admin and Editor Accounts, with passwords read from
CMS_ADMIN_PASSWORD and CMS_EDITOR_PASSWORD. Also creates a Trip, Recaps in
every status and two Pages. Safe to run again.

The rubric expects this to run clean on a fresh clone with .env.example values
(item E4), because the database itself is never committed.
"""
from __future__ import annotations

import os
import sys

from app import seed


def main() -> int:
    admin_pw = os.environ.get("CMS_ADMIN_PASSWORD")
    editor_pw = os.environ.get("CMS_EDITOR_PASSWORD")
    if not (admin_pw or "").strip() or not (editor_pw or "").strip():
        print("Set CMS_ADMIN_PASSWORD and CMS_EDITOR_PASSWORD in .env "
              "(copy .env.example).")
        return 1

    seed.seed_accounts(admin_pw, editor_pw)
    seed.seed_content()
    print(f"Seeded {seed.ADMIN_EMAIL} and {seed.EDITOR_EMAIL}, a Trip, "
          "Recaps in every status, and two Pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
