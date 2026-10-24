"""Pages: Admin only, on every route."""
from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import pages
from app.accounts import Account
from app.flash import flash
from app.markdown import render_body
from app.security import require
from app.slugs import is_url_safe, slugify
from app.templating import templates

router = APIRouter(prefix="/admin/pages")
manage = require("pages.manage")

LIVE_NOTICE = ("This Page is Published, so the change is still live until you "
               "Deploy.")
TRANSITION_ERROR = "That change is not allowed for a Page in its current status."
TITLE_ERROR = "The title cannot be blank."
SLUG_ERROR = "The Slug cannot be blank."
SLUG_UNSAFE_ERROR = ("A Slug may only use lowercase letters, digits and single "
                     "hyphens, such as about-the-club.")
SLUG_LENGTH_ERROR = ("A Slug can be at most {limit} characters long. Choose a "
                     "shorter one.")
SLUG_RESERVED_ERROR = ("'{slug}' is a reserved Slug, because the site already "
                       "uses that address. Choose a different one.")
SLUG_TAKEN_ERROR = ("That Slug is already in use by another Page. Choose a "
                    "different one.")
NAV_ERROR = "The nav position must be a whole number, such as 1."
STATUSES = ("draft", "published")


def _form(request: Request, account: Account, values: dict, action: str,
          title: str, error: str | None = None, status_code: int = 200,
          page=None, preview_html: str | None = None):
    available = [(name, name.capitalize()) for name, (start, _)
                 in pages.TRANSITIONS.items()
                 if page is not None and page["status"] == start]
    return templates.TemplateResponse(
        request, "admin/page_form.html",
        {"title": title, "account": account, "values": values,
         "action": action, "error": error, "page": page,
         "status_actions": available, "preview_html": preview_html},
        status_code=status_code)


def _get_or_404(page_id: int):
    page = pages.get_page(page_id)
    if page is None:
        raise HTTPException(404, "No such Page")
    return page


def _values(title: str, slug: str, body: str, nav_position: str) -> dict:
    return {"title": title, "slug": slug, "body": body,
            "nav_position": nav_position}


def _save(request: Request, account: Account, form: dict[str, str],
          action: str, title: str, save: Callable[..., object], existing=None):
    """Validate the form, then save with (title, slug, body, nav position). On
    a refusal re-show the form with a 400."""
    slug, nav = form["slug"].strip(), pages.parse_nav_position(
        form["nav_position"])
    error = (TITLE_ERROR if not form["title"].strip()
             else SLUG_ERROR if not slug
             else SLUG_UNSAFE_ERROR if not is_url_safe(slug)
             else SLUG_LENGTH_ERROR.format(limit=pages.MAX_SLUG_LENGTH)
             if len(slug) > pages.MAX_SLUG_LENGTH
             else SLUG_RESERVED_ERROR.format(slug=slug)
             if slug in pages.RESERVED_SLUGS
             else NAV_ERROR if nav is None else None)
    if not error:
        try:
            save(form["title"].strip(), slug, form["body"], nav)
        except pages.SlugTaken:
            error = SLUG_TAKEN_ERROR
        else:
            if existing is not None and existing["status"] == "published":
                flash(request, LIVE_NOTICE)
    if error:
        return _form(request, account, form, action, title, error, 400,
                     page=existing)
    return RedirectResponse("/admin/pages", status_code=303)


@router.get("")
def list_pages(request: Request, account: Account = Depends(manage),
               status: str = ""):
    return templates.TemplateResponse(
        request, "admin/pages.html",
        {"title": "Pages", "account": account, "status": status,
         "pages": pages.list_pages(status if status in STATUSES else None)})


@router.get("/new")
def new_page(request: Request, account: Account = Depends(manage),
             title: str = ""):
    values = _values(title, slugify(title), "", "1")
    return _form(request, account, values, "/admin/pages", "New Page")


@router.post("/preview")
def preview_new_page(request: Request, account: Account = Depends(manage),
                     title: str = Form(""), slug: str = Form(""),
                     body: str = Form(""), nav_position: str = Form("")):
    return _form(request, account, _values(title, slug, body, nav_position),
                 "/admin/pages", "New Page", preview_html=render_body(body))


@router.post("")
def create_page(request: Request, account: Account = Depends(manage),
                title: str = Form(""), slug: str = Form(""),
                body: str = Form(""), nav_position: str = Form("")):
    return _save(request, account, _values(title, slug, body, nav_position),
                 "/admin/pages", "New Page",
                 lambda *fields: pages.create_page(account.id, *fields))


@router.get("/{page_id}")
def edit_page_form(page_id: int, request: Request,
                   account: Account = Depends(manage)):
    page = _get_or_404(page_id)
    values = {k: page[k] for k in ("title", "slug", "body", "nav_position")}
    return _form(request, account, values, f"/admin/pages/{page_id}",
                 "Edit Page", page=page)


@router.post("/{page_id}/preview")
def preview_page(page_id: int, request: Request,
                 account: Account = Depends(manage), title: str = Form(""),
                 slug: str = Form(""), body: str = Form(""),
                 nav_position: str = Form("")):
    page = _get_or_404(page_id)
    return _form(request, account, _values(title, slug, body, nav_position),
                 f"/admin/pages/{page_id}", "Edit Page", page=page,
                 preview_html=render_body(body))


@router.post("/{page_id}/delete")
def delete_page(page_id: int, request: Request,
                account: Account = Depends(manage)):
    page = _get_or_404(page_id)
    pages.delete_page(page_id)
    if page["status"] == "published":
        flash(request, LIVE_NOTICE)
    return RedirectResponse("/admin/pages", status_code=303)


def _move(request: Request, page_id: int, action: str):
    _get_or_404(page_id)
    try:
        pages.transition(page_id, action)
    except pages.TransitionRefused:
        raise HTTPException(409, TRANSITION_ERROR)
    if action == "unpublish":
        flash(request, LIVE_NOTICE)
    return RedirectResponse("/admin/pages", status_code=303)


@router.post("/{page_id}/publish")
def publish_page(page_id: int, request: Request,
                 account: Account = Depends(manage)):
    return _move(request, page_id, "publish")


@router.post("/{page_id}/unpublish")
def unpublish_page(page_id: int, request: Request,
                   account: Account = Depends(manage)):
    return _move(request, page_id, "unpublish")


@router.post("/{page_id}")
def edit_page(page_id: int, request: Request,
              account: Account = Depends(manage), title: str = Form(""),
              slug: str = Form(""), body: str = Form(""),
              nav_position: str = Form("")):
    page = _get_or_404(page_id)
    return _save(request, account, _values(title, slug, body, nav_position),
                 f"/admin/pages/{page_id}", "Edit Page",
                 lambda *fields: pages.update_page(page_id, *fields),
                 existing=page)
