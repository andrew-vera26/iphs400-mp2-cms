"""Configuration, read from the environment (never hard-code secrets)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
SITE = ROOT / "site"

# DEVELOPMENT ONLY: this fallback key is public, so anyone can forge a session
# cookie signed with it. It exists so `cms serve` starts with no .env. Set
# CMS_SECRET_KEY for anything real; create_app() logs a warning while it is used.
DEV_SECRET_KEY = "dev-only-not-for-production"
SECRET_KEY = os.environ.get("CMS_SECRET_KEY", DEV_SECRET_KEY)
SECRET_KEY_IS_DEV_DEFAULT = SECRET_KEY == DEV_SECRET_KEY
DATABASE_PATH = Path(os.environ.get("CMS_DATABASE", ROOT / "cms.db"))
SITE_TITLE = os.environ.get("CMS_SITE_TITLE", "My CMS")
# Set this to your Pages URL once you deploy, e.g.
# https://yourname.github.io/iphs400-mp2-cms/
BASE_PATH = os.environ.get("CMS_BASE_PATH", "")
# The club's Instagram, linked from every page's footer for discussion. A
# committed constant, not an environment variable: replace the placeholder.
INSTAGRAM_URL = "https://www.instagram.com/REPLACE-ME/"
# Uploaded Recap Images. Gitignored, and outside SITE: only the Images of
# Published Recaps are copied from here into the output.
UPLOADS = Path(os.environ.get("CMS_UPLOADS", ROOT / "uploads"))
