"""Recap Drafts: Editors write their own; Admins can act on any."""
from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import policy, recaps, trips
from app.accounts import Account
from app.routes.accounts import CLASS_YEAR, CLASS_YEAR_RANGE
from app.security import require
from app.slugs import is_url_safe, slugify
from app.templating import templates

router = APIRouter(prefix="/admin/recaps")

BYLINE_ERROR = ("A Byline needs both the writer's name and a four-digit "
                "class year, such as 2027.")
TRIP_ERROR = "Choose one of the existing Trips."
BODY_ERROR = "The Body cannot be empty."
TITLE_ERROR = "The title cannot be blank."
SLUG_ERROR = "The Slug cannot be blank."
SLUG_UNSAFE_ERROR = ("A Slug may only use lowercase letters, digits and single "
                     "hyphens, such as chicago-food-crawl.")
SLUG_TAKEN_ERROR = ("That Slug is already in use by another Recap on this "
                    "Trip. Choose a different one.")


def _form(request: Request, account: Account, values: dict, action: str,
          title: str, error: str | None = None, status_code: int = 200,
          recap=None):
    return templates.TemplateResponse(
        request, "admin/recap_form.html",
        {"title": title, "account": account, "values": values,
         "action": action, "trips": trips.list_trips(), "error": error,
         "recap": recap}, status_code=status_code)


def _typed_byline(name: str, class_year: str):
    """(name, class year) from what an Admin typed, or None if either part is
    missing or the year is not a four-digit year."""
    name, class_year = name.strip(), class_year.strip()
    if not name or not CLASS_YEAR.fullmatch(class_year) \
            or int(class_year) not in CLASS_YEAR_RANGE:
        return None
    return name, int(class_year)


def _allowed_recap(recap_id: int, account: Account, action: str):
    """The Recap, if it exists and this Account may do `action` to it."""
    recap = recaps.get_recap(recap_id)
    if recap is None:
        raise HTTPException(404, "No such Recap")
    if not policy.can(account, action, recap):
        raise HTTPException(403, "You do not have permission to do that")
    return recap


def _save(request: Request, account: Account, form: dict[str, str],
          action: str, title: str,
          save: Callable[[int, str, str, str, str, int], object],
          existing=None):
    """Validate the form, then save with (trip_id, title, slug, body, byline
    name, byline class year). On a refusal re-show the form with a 400.

    An Editor's Byline is never read from the form: it is their Account's on
    creation and unchanged on edit. An Admin types it.
    """
    if account.role == policy.ADMIN:
        byline = _typed_byline(form["byline_name"], form["byline_class_year"])
    elif existing is not None:
        byline = existing["byline_name"], existing["byline_class_year"]
    else:
        byline = account.name, account.class_year

    trip_id = form["trip_id"]
    error = (BYLINE_ERROR if byline is None
             else TRIP_ERROR if not trip_id.isdigit()
             or trips.get_trip(int(trip_id)) is None
             else TITLE_ERROR if not form["title"].strip()
             else SLUG_ERROR if not form["slug"].strip()
             else SLUG_UNSAFE_ERROR if not is_url_safe(form["slug"].strip())
             else BODY_ERROR if not form["body"].strip() else None)
    if not error:
        try:
            save(int(trip_id), form["title"].strip(), form["slug"].strip(),
                 form["body"], *byline)
        except recaps.SlugTaken:
            error = SLUG_TAKEN_ERROR
    if error:
        return _form(request, account, form, action, title, error, 400,
                     recap=existing)
    return RedirectResponse("/admin/recaps", status_code=303)


@router.get("")
def list_recaps(request: Request,
                account: Account = Depends(require("console.view"))):
    # Editors see only their own Recaps; Admins see all of them.
    owner_id = None if account.role == policy.ADMIN else account.id
    return templates.TemplateResponse(
        request, "admin/recaps.html",
        {"title": "Recaps", "account": account,
         "recaps": recaps.list_recaps(owner_id)})


@router.get("/new")
def new_recap(request: Request,
              account: Account = Depends(require("recaps.create")),
              title: str = "", trip_id: str = ""):
    values = {"trip_id": trip_id, "title": title, "slug": slugify(title)}
    return _form(request, account, values, "/admin/recaps", "New Recap")


@router.get("/{recap_id}")
def edit_recap_form(recap_id: int, request: Request,
                    account: Account = Depends(require("console.view"))):
    recap = _allowed_recap(recap_id, account, "recaps.view")
    values = {k: recap[k] for k in ("trip_id", "title", "slug", "body",
                                    "byline_name", "byline_class_year")}
    return _form(request, account, values, f"/admin/recaps/{recap_id}",
                 "Edit Recap", recap=recap)


@router.post("/{recap_id}/delete")
def delete_recap(recap_id: int,
                 account: Account = Depends(require("console.view"))):
    _allowed_recap(recap_id, account, "recaps.delete")
    recaps.delete_recap(recap_id)
    return RedirectResponse("/admin/recaps", status_code=303)


@router.post("/{recap_id}")
def edit_recap(recap_id: int, request: Request,
               account: Account = Depends(require("console.view")),
               trip_id: str = Form(""), title: str = Form(""),
               slug: str = Form(""), body: str = Form(""),
               byline_name: str = Form(""),
               byline_class_year: str = Form("")):
    recap = _allowed_recap(recap_id, account, "recaps.edit")
    form = {"trip_id": trip_id, "title": title, "slug": slug, "body": body,
            "byline_name": byline_name, "byline_class_year": byline_class_year}
    return _save(request, account, form, f"/admin/recaps/{recap_id}",
                 "Edit Recap",
                 lambda *fields: recaps.update_recap(recap_id, *fields),
                 existing=recap)


@router.post("")
def create_recap(request: Request,
                 account: Account = Depends(require("recaps.create")),
                 trip_id: str = Form(""), title: str = Form(""),
                 slug: str = Form(""), body: str = Form(""),
                 byline_name: str = Form(""),
                 byline_class_year: str = Form("")):
    form = {"trip_id": trip_id, "title": title, "slug": slug, "body": body,
            "byline_name": byline_name, "byline_class_year": byline_class_year}
    return _save(request, account, form, "/admin/recaps", "New Recap",
                 lambda *fields: recaps.create_recap(
                     fields[0], account.id, *fields[1:]))
