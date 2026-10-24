"""Trip management: Admin only."""
from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import slugs, trips
from app.accounts import Account
from app.security import require
from app.templating import templates

router = APIRouter(prefix="/admin/trips")
manage = require("trips.manage")

HAS_RECAPS_ERROR = ("This Trip still has Recaps, so it cannot be deleted. "
                    "Delete or move its Recaps first.")
SLUG_TAKEN_ERROR = ("That Slug is already in use by another Trip. Choose a "
                    "different one.")
DATE_ERROR = "Dates must be real dates written as YYYY-MM-DD, such as 2026-03-05."
END_BEFORE_START_ERROR = "The end date cannot be before the start date."
SLUG_UNSAFE_ERROR = ("A Slug may only use lowercase letters, digits and single "
                     "hyphens, such as 2026-chicago.")


def _form(request: Request, account: Account, values, action: str, title: str,
          error: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request, "admin/trip_form.html",
        {"title": title, "account": account, "values": values,
         "action": action, "error": error}, status_code=status_code)


def _save(request: Request, account: Account, values: dict[str, str],
          save: Callable[[dict[str, str]], object], action: str, title: str):
    """Validate and save; re-show the form with a 400 and a message if refused."""
    error = None
    if not all(values.values()):
        error = "Every field is required."
    elif not (start := trips.parse_date(values["start_date"])) \
            or not (end := trips.parse_date(values["end_date"])):
        error = DATE_ERROR
    elif end < start:
        error = END_BEFORE_START_ERROR
    elif not slugs.is_url_safe(values["slug"]):
        error = SLUG_UNSAFE_ERROR
    else:
        try:
            save(values)
        except trips.SlugTaken:
            error = SLUG_TAKEN_ERROR
    if error:
        return _form(request, account, values, action, title, error, 400)
    return RedirectResponse("/admin/trips", status_code=303)


def _trip_or_404(trip_id: int):
    trip = trips.get_trip(trip_id)
    if trip is None:
        raise HTTPException(404, "No such Trip")
    return trip


def _listing(request: Request, account: Account, error: str | None = None,
             status_code: int = 200):
    return templates.TemplateResponse(
        request, "admin/trips.html",
        {"title": "Trips", "account": account, "trips": trips.list_trips(),
         "error": error}, status_code=status_code)


@router.get("")
def list_trips(request: Request, account: Account = Depends(manage)):
    return _listing(request, account)


@router.get("/new")
def new_trip(request: Request, account: Account = Depends(manage),
             start_date: str = "", city: str = ""):
    values = {"start_date": start_date, "city": city,
              "slug": slugs.suggest_trip_slug(start_date, city)}
    return _form(request, account, values, "/admin/trips", "New Trip")


@router.post("")
def create_trip(request: Request, account: Account = Depends(manage),
                conference: str = Form(""), city: str = Form(""),
                start_date: str = Form(""), end_date: str = Form(""),
                summary: str = Form(""), slug: str = Form("")):
    values = {"conference": conference.strip(), "city": city.strip(),
              "start_date": start_date.strip(), "end_date": end_date.strip(),
              "summary": summary.strip(), "slug": slug.strip()}
    return _save(request, account, values, trips.create_trip,
                 "/admin/trips", "New Trip")


@router.post("/{trip_id}/delete")
def delete_trip(trip_id: int, request: Request,
                account: Account = Depends(manage)):
    _trip_or_404(trip_id)
    if not trips.delete_trip(trip_id):
        return _listing(request, account, HAS_RECAPS_ERROR, 409)
    return RedirectResponse("/admin/trips", status_code=303)


@router.get("/{trip_id}")
def edit_trip_form(trip_id: int, request: Request,
                   account: Account = Depends(manage)):
    return _form(request, account, _trip_or_404(trip_id),
                 f"/admin/trips/{trip_id}", "Edit Trip")


@router.post("/{trip_id}")
def edit_trip(trip_id: int, request: Request,
              account: Account = Depends(manage),
              conference: str = Form(""), city: str = Form(""),
              start_date: str = Form(""), end_date: str = Form(""),
              summary: str = Form(""), slug: str = Form("")):
    _trip_or_404(trip_id)
    values = {"conference": conference.strip(), "city": city.strip(),
              "start_date": start_date.strip(), "end_date": end_date.strip(),
              "summary": summary.strip(), "slug": slug.strip()}
    return _save(request, account, values,
                 lambda v: trips.update_trip(trip_id, v),
                 f"/admin/trips/{trip_id}", "Edit Trip")
