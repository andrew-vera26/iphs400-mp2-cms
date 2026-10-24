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


class UnknownAccount(LookupError):
    """No Account has this id."""


class LastActiveAdmin(ValueError):
    """The change would leave the club without an active Admin."""


def list_accounts() -> list[Account]:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM account ORDER BY active DESC, "
                            "role, name").fetchall()
    return [Account.from_row(r) for r in rows]


def _lock_account(conn, account_id: int):
    """Start a write transaction and return the Account's row."""
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute("SELECT * FROM account WHERE id = ?",
                       (account_id,)).fetchone()
    if row is None:
        raise UnknownAccount(account_id)
    return row


def _is_last_active_admin(conn, row) -> bool:
    if not (row["role"] == "admin" and row["active"]):
        return False
    return conn.execute("SELECT COUNT(*) FROM account WHERE role = 'admin' "
                        "AND active = 1").fetchone()[0] <= 1


def set_role(account_id: int, role: str) -> None:
    """Change an Account's role; refuse to demote the last active Admin."""
    with db.connect() as conn:
        row = _lock_account(conn, account_id)
        if role != "admin" and _is_last_active_admin(conn, row):
            raise LastActiveAdmin(account_id)
        conn.execute("UPDATE account SET role = ? WHERE id = ?",
                     (role, account_id))


def deactivate(account_id: int) -> None:
    """Deactivate an Account; refuse for the last active Admin. Irreversible."""
    with db.connect() as conn:
        row = _lock_account(conn, account_id)
        if _is_last_active_admin(conn, row):
            raise LastActiveAdmin(account_id)
        conn.execute("UPDATE account SET active = 0 WHERE id = ?",
                     (account_id,))


def set_password(account_id: int, password: str) -> None:
    with db.connect() as conn:
        _lock_account(conn, account_id)
        conn.execute("UPDATE account SET password_hash = ? WHERE id = ?",
                     (hash_password(password), account_id))


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
