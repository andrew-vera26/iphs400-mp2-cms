"""The FastAPI application.

The admin console lives under /admin, with /login and /logout beside it; the
public site answers at /. Add routes in their own modules under app/routes/ and
include them here. Keep this file small.
"""
from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware

from app import db, settings
from app.routes import accounts, auth, console, recaps, trips
from app.security import csrf_protect
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

    app.include_router(auth.router)
    app.include_router(console.router)
    app.include_router(accounts.router)
    app.include_router(trips.router)
    app.include_router(recaps.router)

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
