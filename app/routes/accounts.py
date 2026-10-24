"""Account management: Admin only. There is deliberately no Reactivate."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse

from app import accounts, policy
from app.accounts import Account
from app.security import require
from app.templating import templates

router = APIRouter(prefix="/admin/accounts")
manage = require("accounts.manage")

ROLES = (policy.ADMIN, policy.EDITOR)
CLASS_YEAR = re.compile(r"[0-9]{4}")  # ASCII digits only; str.isdigit() accepts more
CLASS_YEAR_RANGE = range(2000, 2101)
CLASS_YEAR_ERROR = "Class year must be a four-digit year between 2000 and 2100."
LAST_ADMIN_ERROR = ("This is the last active Admin, so it cannot be "
                    "deactivated or demoted. Make another Admin first.")


def _listing(request: Request, account: Account, error: str | None = None,
             status_code: int = 200):
    return templates.TemplateResponse(
        request, "admin/accounts.html",
        {"title": "Accounts", "account": account, "roles": ROLES,
         "accounts": accounts.list_accounts(), "error": error},
        status_code=status_code)


def _form(request: Request, account: Account, values: dict,
          error: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request, "admin/account_new.html",
        {"title": "New Account", "account": account, "roles": ROLES,
         "values": values, "error": error}, status_code=status_code)


def _done() -> RedirectResponse:
    return RedirectResponse("/admin/accounts", status_code=303)


@router.get("")
def list_accounts(request: Request, account: Account = Depends(manage)):
    return _listing(request, account)


@router.get("/new")
def new_account(request: Request, account: Account = Depends(manage)):
    return _form(request, account, {})


@router.post("")
def create_account(request: Request, account: Account = Depends(manage),
                   email: str = Form(""), name: str = Form(""),
                   class_year: str = Form(""), role: str = Form(""),
                   password: str = Form("")):
    values = {"email": email, "name": name, "class_year": class_year,
              "role": role}

    def refuse(message: str):
        return _form(request, account, values, message, 400)

    if not email.strip() or "@" not in email:
        return refuse("Enter an email address.")
    if not name.strip():
        return refuse("Enter a name.")
    if not (CLASS_YEAR.fullmatch(class_year)
            and int(class_year) in CLASS_YEAR_RANGE):
        return refuse(CLASS_YEAR_ERROR)
    if role not in ROLES:
        return refuse("Role must be Admin or Editor.")
    if not password:
        return refuse("Enter an initial password.")
    if accounts.create_account(email, name.strip(), int(class_year), role,
                               password) is None:
        return refuse("That email is already in use by another Account.")
    return _done()


@router.post("/{account_id}/role")
def change_role(request: Request, account_id: int,
                account: Account = Depends(manage), role: str = Form("")):
    if role not in ROLES:
        return _listing(request, account, "Role must be Admin or Editor.", 400)
    try:
        accounts.set_role(account_id, role)
    except accounts.UnknownAccount:
        return _listing(request, account, "No such Account.", 404)
    except accounts.LastActiveAdmin:
        return _listing(request, account, LAST_ADMIN_ERROR, 400)
    return _done()


@router.post("/{account_id}/deactivate")
def deactivate(request: Request, account_id: int,
               account: Account = Depends(manage)):
    try:
        accounts.deactivate(account_id)
    except accounts.UnknownAccount:
        return _listing(request, account, "No such Account.", 404)
    except accounts.LastActiveAdmin:
        return _listing(request, account, LAST_ADMIN_ERROR, 400)
    return _done()


@router.post("/{account_id}/password")
def set_password(request: Request, account_id: int,
                 account: Account = Depends(manage), password: str = Form("")):
    if not password:
        return _listing(request, account, "Enter a new password.", 400)
    try:
        accounts.set_password(account_id, password)
    except accounts.UnknownAccount:
        return _listing(request, account, "No such Account.", 404)
    return _done()
