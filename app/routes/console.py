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
    see_all = policy.can(account, "recaps.see_all")
    overview = policy.can(account, "console.overview")
    context = {
        "title": "Admin", "account": account,
        "recap_counts": dashboard.recap_counts(None if see_all else account.id),
        "admin": dashboard.admin_counts() if overview else None,
        "not_live": overview and site_state.changes_not_live()}
    return templates.TemplateResponse(request, "admin/dashboard.html", context)
