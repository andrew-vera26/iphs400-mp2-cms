"""Sessions, CSRF and the route guard.

The session is a signed cookie (Starlette's SessionMiddleware, itsdangerous
underneath) holding the Account id and a CSRF token. The Account itself is
reread from the database on every request.
"""
from __future__ import annotations

import secrets
from typing import Callable

from fastapi import Depends, HTTPException, Request

from app import accounts, policy
from app.accounts import Account

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
LOGIN_URL = "/login"


PERMISSION_DETAIL = "You do not have permission to do that"


class PermissionDenied(HTTPException):
    """The Account is signed in but the policy says no. Distinct from the CSRF
    refusal, which is also a 403: a browser is shown a page for this one."""

    def __init__(self) -> None:
        super().__init__(403, PERMISSION_DETAIL)


def csrf_token(request: Request) -> str:
    """The session's CSRF token, created on first use."""
    token = request.session.get("csrf")
    if not token:
        token = request.session["csrf"] = secrets.token_urlsafe(32)
    return token


async def csrf_protect(request: Request) -> None:
    """App-wide dependency: refuse any state-changing request without the token."""
    if request.method in SAFE_METHODS:
        return
    form = await request.form()
    sent = form.get("csrf_token")
    expected = request.session.get("csrf")
    if not (isinstance(sent, str) and expected
            and secrets.compare_digest(sent, expected)):
        raise HTTPException(403, "Missing or invalid CSRF token")


def current_account(request: Request) -> Account | None:
    """Reread the signed-in Account; a Deactivated one counts as signed out."""
    account_id = request.session.get("account_id")
    account = accounts.get(account_id) if account_id else None
    if account is None or not account.active:
        request.session.pop("account_id", None)
        return None
    return account


def require(action: str) -> Callable[..., Account]:
    """Route dependency: logged out -> login page, not allowed -> 403."""

    def guard(account: Account | None = Depends(current_account)) -> Account:
        if account is None:
            raise HTTPException(303, headers={"Location": LOGIN_URL})
        if not policy.can(account, action):
            raise PermissionDenied()
        return account

    return guard
