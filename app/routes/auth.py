"""/login and /logout."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app import accounts
from app.templating import templates

router = APIRouter()

GENERIC_ERROR = "Email or password is incorrect."


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(request, "admin/login.html",
                                      {"title": "Log in", "error": None})


@router.post("/login")
def login(request: Request, email: str = Form(""), password: str = Form("")):
    account = accounts.authenticate(email, password)
    if account is None:
        return templates.TemplateResponse(
            request, "admin/login.html",
            {"title": "Log in", "error": GENERIC_ERROR}, status_code=401)
    request.session.clear()  # new session, new CSRF token
    request.session["account_id"] = account.id
    request.session["csrf"] = secrets.token_urlsafe(32)
    return RedirectResponse("/admin", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
