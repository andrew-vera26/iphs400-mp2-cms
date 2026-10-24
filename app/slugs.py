"""Suggested Slugs. A suggestion is only a starting point; the Admin or Editor
can edit it, and uniqueness is checked when the form is saved."""
from __future__ import annotations

import re
import unicodedata

from app.trips import parse_date


def slugify(text: str) -> str:
    """URL-safe form of text: lowercase ASCII letters and digits, joined by
    single hyphens."""
    ascii_text = (unicodedata.normalize("NFKD", text)
                  .encode("ascii", "ignore").decode())
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def is_url_safe(slug: str) -> bool:
    """True if slug is what slugify could produce: lowercase ASCII letters and
    digits joined by single hyphens."""
    return re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug) is not None


def suggest_trip_slug(start_date: str, city: str) -> str:
    """Start year plus city, such as 2026-chicago; empty until the start date is
    a real date and the city is known."""
    start, city_slug = parse_date(start_date.strip()), slugify(city)
    return f"{start.year}-{city_slug}" if start and city_slug else ""
