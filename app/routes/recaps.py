"""Recap Drafts: Editors write their own; Admins can act on any."""
from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from app import accounts, dashboard, images, policy, recaps, settings, trips
from app.flash import flash
from app.markdown import images_without_alt, render_body
from app.accounts import Account
from app.routes.accounts import CLASS_YEAR, CLASS_YEAR_RANGE
from app.security import PermissionDenied, require
from app.slugs import is_url_safe, slugify
from app.templating import templates

router = APIRouter(prefix="/admin/recaps")

BYLINE_ERROR = ("A Byline needs both the writer's name and a four-digit "
                "class year, such as 2027.")
TRIP_ERROR = "Choose one of the existing Trips."
BODY_ERROR = "The Body cannot be empty."
SUBMIT_EMPTY_ERROR = "A Recap with an empty Body cannot be Submitted."
LIVE_NOTICE = ("This Recap is Published, so the change is still live until you "
               "Deploy.")
LOCKED_ERROR = ("This Recap was Submitted or Published, so it can no longer "
                "be changed by its Editor.")
TRANSITION_ERROR = "That change is not allowed for a Recap in its current status."
ALT_PUBLISH_ERROR = ("This Recap's Body has an image without alt text. Add alt "
                     "text to every image before it is Published.")
TITLE_ERROR = "The title cannot be blank."
SLUG_ERROR = "The Slug cannot be blank."
SLUG_UNSAFE_ERROR = ("A Slug may only use lowercase letters, digits and single "
                     "hyphens, such as chicago-food-crawl.")
SLUG_TAKEN_ERROR = ("That Slug is already in use by another Recap on this "
                    "Trip. Choose a different one.")


# URL name -> (policy action, button label), in the order the buttons show.
STATUS_ACTIONS = {
    "submit": ("recaps.submit", "Submit"),
    "send-back": ("recaps.send_back", "Send back"),
    "publish": ("recaps.publish", "Publish"),
    "unpublish": ("recaps.unpublish", "Unpublish"),
}


def _available_actions(account: Account, recap) -> list[tuple[str, str]]:
    """(URL name, label) of the status changes this person may make to this
    Recap right now: the policy says who, the status machine says from where."""
    if recap is None:
        return []
    return [(name, label) for name, (policy_action, label)
            in STATUS_ACTIONS.items()
            if recap["status"] in recaps.TRANSITIONS[name][0]
            and policy.can(account, policy_action, recap)]


def _form(request: Request, account: Account, values: dict, action: str,
          title: str, error: str | None = None, status_code: int = 200,
          recap=None, preview_html: str | None = None,
          snippet: str | None = None):
    return templates.TemplateResponse(
        request, "admin/recap_form.html",
        {"title": title, "account": account, "values": values,
         "action": action, "trips": trips.list_trips(), "error": error,
         "recap": recap, "status_actions": _available_actions(account, recap),
         "preview_html": preview_html, "snippet": snippet,
         "images": images.list_images(recap["id"]) if recap else [],
         "can_edit_images": recap is not None
         and policy.can(account, "recaps.edit", recap)},
        status_code=status_code)


def _typed_byline(name: str, class_year: str):
    """(name, class year) from what an Admin typed, or None if either part is
    missing or the year is not a four-digit year."""
    name, class_year = name.strip(), class_year.strip()
    if not name or not CLASS_YEAR.fullmatch(class_year) \
            or int(class_year) not in CLASS_YEAR_RANGE:
        return None
    return name, int(class_year)


def _editor_id(account: Account) -> int | None:
    """The id to pin a write to an Editor's own Draft; None leaves an Admin's
    writes unrestricted."""
    return None if account.role == policy.ADMIN else account.id


def _allowed_recap(recap_id: int, account: Account, action: str):
    """The Recap, if it exists and this Account may do `action` to it."""
    recap = recaps.get_recap(recap_id)
    if recap is None:
        raise HTTPException(404, "No such Recap")
    if not policy.can(account, action, recap):
        raise PermissionDenied()
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
        except recaps.RecapLocked:
            raise HTTPException(409, LOCKED_ERROR)
        else:
            if existing is not None and existing["status"] == "published":
                flash(request, LIVE_NOTICE)
    if error:
        return _form(request, account, form, action, title, error, 400,
                     recap=existing)
    return RedirectResponse("/admin/recaps", status_code=303)


MAX_ID_DIGITS = 18  # ids are SQLite integers; longer is never a real id


def _one_param(request: Request, name: str) -> str | None:
    """The single value of a query parameter, '' and absent meaning None.
    A repeated parameter is refused rather than guessing which one counts."""
    values = request.query_params.getlist(name)
    if len(values) > 1:
        raise HTTPException(400, "Invalid filter")
    return values[0] or None if values else None


def _filter_id(request: Request, name: str) -> int | None:
    value = _one_param(request, name)
    if value is None:
        return None
    if not (value.isascii() and value.isdigit()) or len(value) > MAX_ID_DIGITS:
        raise HTTPException(400, "Invalid filter")
    return int(value)


def _filter_status(request: Request) -> str | None:
    value = _one_param(request, "status")
    if value is not None and value not in dashboard.RECAP_STATUSES:
        raise HTTPException(400, "Invalid filter")
    return value


@router.get("")
def list_recaps(request: Request,
                account: Account = Depends(require("console.view"))):
    status = _filter_status(request)
    trip_id = _filter_id(request, "trip")
    # Editors see only their own Recaps and any owner filter is ignored; the
    # Owner filter is an Admin's.
    is_admin = account.role == policy.ADMIN
    owner_id = _filter_id(request, "owner") if is_admin else account.id
    return templates.TemplateResponse(
        request, "admin/recaps.html",
        {"title": "Recaps", "account": account,
         "recaps": recaps.list_recaps(owner_id, status, trip_id,
                                      submitted_first=is_admin),
         "statuses": dashboard.RECAP_STATUSES, "trips": trips.list_trips(),
         "owners": accounts.list_accounts() if is_admin else [],
         "selected": {"status": status, "trip": trip_id,
                      "owner": owner_id if is_admin else None}})


@router.get("/new")
def new_recap(request: Request,
              account: Account = Depends(require("recaps.create")),
              title: str = "", trip_id: str = ""):
    values = {"trip_id": trip_id, "title": title, "slug": slugify(title)}
    return _form(request, account, values, "/admin/recaps", "New Recap")


def _edit_form(request: Request, account: Account, recap,
               error: str | None = None, status_code: int = 200,
               snippet: str | None = None):
    """The saved Recap's editor, as stored."""
    values = {k: recap[k] for k in ("trip_id", "title", "slug", "body",
                                    "byline_name", "byline_class_year")}
    return _form(request, account, values, f"/admin/recaps/{recap['id']}",
                 "Edit Recap", error, status_code, recap=recap, snippet=snippet)


@router.get("/{recap_id}")
def edit_recap_form(recap_id: int, request: Request,
                    account: Account = Depends(require("console.view"))):
    return _edit_form(request, account,
                      _allowed_recap(recap_id, account, "recaps.view"))


def _move(request: Request, recap_id: int, account: Account, action: str, policy_action: str):
    """Run one status change: the policy decides who, the status machine
    decides from which status. A refusal is a 403 or a 409 and changes nothing."""
    recap = _allowed_recap(recap_id, account, policy_action)
    if action == "submit" and not recap["body"].strip():
        raise HTTPException(400, SUBMIT_EMPTY_ERROR)
    if action == "publish" and images_without_alt(
            recap["body"], _image_urls(recap_id)):
        raise HTTPException(400, ALT_PUBLISH_ERROR)
    try:
        recaps.transition(recap_id, action)
    except recaps.TransitionRefused:
        raise HTTPException(409, TRANSITION_ERROR)
    if action == "unpublish":
        flash(request, LIVE_NOTICE)
    return RedirectResponse("/admin/recaps", status_code=303)


@router.post("/{recap_id}/submit")
def submit_recap(recap_id: int, request: Request,
                 account: Account = Depends(require("console.view"))):
    return _move(request, recap_id, account, "submit", "recaps.submit")


@router.post("/{recap_id}/send-back")
def send_back_recap(recap_id: int, request: Request,
                    account: Account = Depends(require("recaps.send_back"))):
    return _move(request, recap_id, account, "send-back", "recaps.send_back")


@router.post("/{recap_id}/publish")
def publish_recap(recap_id: int, request: Request,
                  account: Account = Depends(require("recaps.publish"))):
    return _move(request, recap_id, account, "publish", "recaps.publish")


@router.post("/{recap_id}/unpublish")
def unpublish_recap(recap_id: int, request: Request,
                    account: Account = Depends(require("recaps.unpublish"))):
    return _move(request, recap_id, account, "unpublish", "recaps.unpublish")


@router.get("/{recap_id}/images/{filename}")
def show_image(recap_id: int, filename: str,
               account: Account = Depends(require("console.view"))):
    """The console's copy of an Image. Preview's `images/<file>` resolves here."""
    _allowed_recap(recap_id, account, "recaps.view")
    image = next((i for i in images.list_images(recap_id)
                  if i["filename"] == filename), None)
    path = settings.UPLOADS / filename
    if image is None or not path.is_file():
        raise HTTPException(404, "No such Image")
    return FileResponse(path, media_type=image["content_type"],
                        headers={"X-Content-Type-Options": "nosniff"})


@router.post("/{recap_id}/images")
def upload_image(recap_id: int, request: Request,
                 account: Account = Depends(require("console.view")),
                 file: UploadFile | None = File(None), alt: str = Form("")):
    recap = _allowed_recap(recap_id, account, "recaps.edit")
    data = file.file.read(images.MAX_BYTES + 1) if file else None
    try:
        image = images.add_image(recap_id, data, alt, _editor_id(account))
    except images.ImageRefused as refusal:
        return _edit_form(request, account, recap, str(refusal), 400)
    if image is None:
        raise HTTPException(409, LOCKED_ERROR)
    return _edit_form(request, account, recap,
                      snippet=images.snippet(image["alt"], image["filename"]))


@router.post("/{recap_id}/images/{image_id}/delete")
def delete_image(recap_id: int, image_id: int,
                 account: Account = Depends(require("console.view"))):
    _allowed_recap(recap_id, account, "recaps.edit")
    image = images.get_image(image_id)
    if image is None or image["recap_id"] != recap_id:
        raise HTTPException(404, "No such Image")
    if not images.delete_image(image_id, recap_id, _editor_id(account)):
        raise HTTPException(409, LOCKED_ERROR)
    return RedirectResponse(f"/admin/recaps/{recap_id}", status_code=303)


@router.post("/{recap_id}/delete")
def delete_recap(recap_id: int,
                 account: Account = Depends(require("console.view"))):
    _allowed_recap(recap_id, account, "recaps.delete")
    try:
        recaps.delete_recap(recap_id, _editor_id(account))
    except recaps.RecapLocked:
        raise HTTPException(409, LOCKED_ERROR)
    return RedirectResponse("/admin/recaps", status_code=303)


def _image_urls(recap_id: int) -> set[str]:
    """The `images/<file>` references a Recap's Body may use."""
    return {f"images/{i['filename']}" for i in images.list_images(recap_id)}


def _form_values(trip_id, title, slug, body, byline_name, byline_class_year):
    return {"trip_id": trip_id, "title": title, "slug": slug, "body": body,
            "byline_name": byline_name, "byline_class_year": byline_class_year}


@router.post("/preview")
def preview_new_recap(request: Request,
                      account: Account = Depends(require("recaps.create")),
                      trip_id: str = Form(""), title: str = Form(""),
                      slug: str = Form(""), body: str = Form(""),
                      byline_name: str = Form(""),
                      byline_class_year: str = Form("")):
    values = _form_values(trip_id, title, slug, body, byline_name,
                          byline_class_year)
    return _form(request, account, values, "/admin/recaps", "New Recap",
                 preview_html=render_body(body))


@router.post("/{recap_id}/preview")
def preview_recap(recap_id: int, request: Request,
                  account: Account = Depends(require("console.view")),
                  trip_id: str = Form(""), title: str = Form(""),
                  slug: str = Form(""), body: str = Form(""),
                  byline_name: str = Form(""),
                  byline_class_year: str = Form("")):
    recap = _allowed_recap(recap_id, account, "recaps.edit")
    values = _form_values(trip_id, title, slug, body, byline_name,
                          byline_class_year)
    return _form(request, account, values, f"/admin/recaps/{recap_id}",
                 "Edit Recap", recap=recap,
                 preview_html=render_body(body, _image_urls(recap_id)))


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
                 lambda *fields: recaps.update_recap(
                     recap_id, *fields, editor_id=_editor_id(account)),
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
