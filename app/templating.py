"""The shared Jinja environment for the console."""
from fastapi.templating import Jinja2Templates

from app import settings
from app.flash import take_flashes
from app.security import csrf_token

CONSOLE_PREFIX = "/admin"


def admin_url(path: str = "") -> str:
    """A console link: admin_url() is /admin, admin_url("recaps/new") is
    /admin/recaps/new. Templates use it instead of writing "/admin/..." out."""
    return f"{CONSOLE_PREFIX}/{path}" if path else CONSOLE_PREFIX


templates = Jinja2Templates(directory=str(settings.TEMPLATES))
templates.env.globals["admin_url"] = admin_url  # {{ admin_url("recaps/new") }}
templates.env.globals["csrf_token"] = csrf_token  # {{ csrf_token(request) }}
templates.env.globals["take_flashes"] = take_flashes  # {{ take_flashes(request) }}
