"""The permission policy: can this Account do this action to this object?

Every route asks `can` (through `security.require`); routes never check roles
themselves. Unknown actions are denied. Add an action here when a ticket adds a
capability. Rules that depend on the object (an Editor's own Draft) take the
`obj` argument.
"""
from __future__ import annotations

from app.accounts import Account

ADMIN = "admin"
EDITOR = "editor"

# action -> roles allowed to do it
ROLE_RULES: dict[str, frozenset[str]] = {
    "console.view": frozenset({ADMIN, EDITOR}),
    "accounts.manage": frozenset({ADMIN}),
}


def can(account: Account | None, action: str, obj: object | None = None) -> bool:
    if account is None or not account.active:
        return False
    return account.role in ROLE_RULES.get(action, frozenset())
