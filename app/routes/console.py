"""Admin console pages. Every route names its action for the policy."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app import dashboard, policy, site_state
from app.accounts import Account
from app.security import require
from app.templating import templates

router = APIRouter(prefix="/admin")


@router.get("")
def admin_home(request: Request, account: Account = Depends(require("console.view"))):
    is_admin = account.role == policy.ADMIN
    context = {
        "title": "Admin", "account": account,
        "recap_counts": dashboard.recap_counts(None if is_admin else account.id),
        "admin": dashboard.admin_counts() if is_admin else None,
        "not_live": is_admin and site_state.changes_not_live()}
    return templates.TemplateResponse(request, "admin/dashboard.html", context)
