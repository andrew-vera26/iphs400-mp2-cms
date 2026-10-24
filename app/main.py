"""The FastAPI application.

The admin console lives under /admin, with /login and /logout beside it; the
public site answers at /. Add routes in their own modules under app/routes/ and
include them here. Keep this file small.
"""
from __future__ import annotations

import logging

from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import db, settings
from app.routes import accounts, auth, console, pages, recaps, trips
from app.security import PermissionDenied, csrf_protect, current_account
from app.templating import templates


log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    if settings.SECRET_KEY_IS_DEV_DEFAULT:
        log.warning("CMS_SECRET_KEY is not set: sessions are signed with the "
                    "public development key. Development use only.")
    db.init_db()
    # csrf_protect runs on every route, so no state-changing route can skip it.
    app = FastAPI(title="IPHS 400 MP2 CMS", dependencies=[Depends(csrf_protect)])
    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY,
                       session_cookie="cms_session", same_site="lax",
                       https_only=False)

    # Only app/static/ is served; never the repo root, uploads or site/.
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"),
              name="static")

    @app.exception_handler(PermissionDenied)
    async def permission_denied(request: Request, exc: PermissionDenied):
        """A browser gets a styled page with a way back; anything else keeps
        the JSON body."""
        account = current_account(request)
        if "text/html" not in request.headers.get("accept", "") or account is None:
            return await http_exception_handler(request, exc)
        return templates.TemplateResponse(
            request, "admin/denied.html", {"title": "Not allowed", "account": account},
            status_code=403)

    app.include_router(auth.router)
    app.include_router(console.router)
    app.include_router(accounts.router)
    app.include_router(trips.router)
    app.include_router(recaps.router)
    app.include_router(pages.router)

    @app.get("/")
    def public_home(request: Request):
        return templates.TemplateResponse(
            request, "public/home.html",
            {"title": settings.SITE_TITLE, "site_title": settings.SITE_TITLE,
             "items": [], "css_path": "style.css", "home_path": "index.html",
             "instagram_url": settings.INSTAGRAM_URL},
        )

    return app


app = create_app()
