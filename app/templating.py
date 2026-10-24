"""The shared Jinja environment for the console."""
from fastapi.templating import Jinja2Templates

from app import settings
from app.flash import take_flashes
from app.security import csrf_token

templates = Jinja2Templates(directory=str(settings.TEMPLATES))
templates.env.globals["csrf_token"] = csrf_token  # {{ csrf_token(request) }}
templates.env.globals["take_flashes"] = take_flashes  # {{ take_flashes(request) }}
