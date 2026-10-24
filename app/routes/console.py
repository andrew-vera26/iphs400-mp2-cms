"""Admin console pages. Every route names its action for the policy."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.accounts import Account
from app.security import require
from app.templating import templates

router = APIRouter(prefix="/admin")


@router.get("")
def admin_home(request: Request, account: Account = Depends(require("console.view"))):
    return templates.TemplateResponse(
        request, "admin/hello.html", {"title": "Admin", "account": account})
