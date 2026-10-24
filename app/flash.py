"""One-shot notices carried to the next page in the signed session cookie."""
from __future__ import annotations

from fastapi import Request

KEY = "flashes"


def flash(request: Request, message: str) -> None:
    """Queue `message` to show on the next page this session renders."""
    request.session[KEY] = [*request.session.get(KEY, []), message]


def take_flashes(request: Request) -> list[str]:
    """The queued notices, removed so each shows once."""
    return request.session.pop(KEY, [])
