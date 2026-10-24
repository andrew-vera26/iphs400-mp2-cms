"""Accounts: creation, lookup and password checks."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app import db

_hasher = PasswordHasher()
# Verified against when an email is unknown, so both failures cost the same.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


@dataclass(frozen=True)
class Account:
    id: int
    email: str
    name: str
    class_year: int
    role: str
    active: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Account:
        return cls(row["id"], row["email"], row["name"], row["class_year"],
                   row["role"], bool(row["active"]))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def create_account(email: str, name: str, class_year: int, role: str,
                   password: str) -> int | None:
    """Insert an Account; return its id, or None if the email is taken."""
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO account (email, name, class_year, role, "
            "password_hash) VALUES (?, ?, ?, ?, ?)",
            (email.strip().lower(), name, class_year, role,
             hash_password(password)),
        )
        return cur.lastrowid if cur.rowcount else None


def get(account_id: int) -> Account | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM account WHERE id = ?",
                           (account_id,)).fetchone()
    return Account.from_row(row) if row else None


def authenticate(email: str, password: str) -> Account | None:
    """Return the active Account for these credentials, else None."""
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM account WHERE email = ?",
                           (email.strip().lower(),)).fetchone()
    stored = row["password_hash"] if row else _DUMMY_HASH
    try:
        ok = _hasher.verify(stored, password)
    except (VerificationError, InvalidHashError):
        ok = False
    if row and ok and row["active"]:
        return Account.from_row(row)
    return None
