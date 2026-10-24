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
    # the dashboard's site-wide counts and "changes not yet live" notice
    "console.overview": frozenset({ADMIN}),
    "accounts.manage": frozenset({ADMIN}),
    "trips.manage": frozenset({ADMIN}),
    "pages.manage": frozenset({ADMIN}),
    "recaps.create": frozenset({ADMIN, EDITOR}),
    "recaps.view": frozenset({ADMIN, EDITOR}),
    "recaps.edit": frozenset({ADMIN, EDITOR}),
    "recaps.delete": frozenset({ADMIN, EDITOR}),
    "recaps.submit": frozenset({EDITOR}),
    "recaps.publish": frozenset({ADMIN}),
    "recaps.unpublish": frozenset({ADMIN}),
    "recaps.send_back": frozenset({ADMIN}),
    # everyone's Recaps in lists and counts, and the Owner filter
    "recaps.see_all": frozenset({ADMIN}),
    # writes to any Recap; otherwise a write is pinned to the Account's own
    "recaps.edit_any": frozenset({ADMIN}),
    # type a Contributor Byline; otherwise it comes from the Account
    "recaps.type_byline": frozenset({ADMIN}),
}

# Actions on one Recap. An Editor may do these only to a Draft they Own; an
# Admin may do them to any Recap. `obj` is the Recap row.
RECAP_ACTIONS = frozenset({"recaps.view", "recaps.edit", "recaps.delete"})


# Only the Editor who Owns a Draft Submits it (an Admin has no row for this).
OWN_DRAFT_ACTIONS = frozenset({"recaps.submit"})


def can(account: Account | None, action: str, obj: object | None = None) -> bool:
    if account is None or not account.active:
        return False
    if account.role not in ROLE_RULES.get(action, frozenset()):
        return False
    if action in OWN_DRAFT_ACTIONS:
        return (obj is not None and obj["owner_id"] == account.id
                and obj["status"] == "draft")
    if action in RECAP_ACTIONS and account.role != ADMIN:
        return (obj is not None and obj["owner_id"] == account.id
                and obj["status"] == "draft")
    return True
