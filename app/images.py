"""Images: photos uploaded to a Recap and placed in its Body.

A file is accepted by what it is (its first bytes), never by its extension or
the Content-Type the browser sent. It is stored under a generated name in
`settings.UPLOADS`; the Body refers to it as `images/<file>`.
"""
from __future__ import annotations

import re
import secrets
import sqlite3

from app import db, settings

MAX_BYTES = 5 * 1024 * 1024

TYPE_ERROR = "Only JPEG, PNG or WebP images can be uploaded."
SIZE_ERROR = "That image is larger than 5 MB. Choose a smaller one."
ALT_ERROR = "Alt text is required: describe the photo for readers who cannot see it."
FILE_ERROR = "Choose an image file to upload."


class ImageRefused(ValueError):
    """The upload cannot be accepted; the message says why."""


def sniff(data: bytes) -> tuple[str, str] | None:
    """(extension, content type) from the file's own bytes, or None."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


def clean_alt(alt: str) -> str:
    """Alt text on one line with single spaces."""
    return " ".join(alt.split())


def snippet(alt: str, filename: str) -> str:
    """The Markdown to paste into a Body. Brackets and backslashes in the alt
    text are escaped so it cannot end the image early or open a link."""
    return f"![{re.sub(r'([\\\[\]])', r'\\\1', alt)}](images/{filename})"


def list_images(recap_id: int) -> list[sqlite3.Row]:
    with db.connect() as conn:
        return conn.execute("SELECT * FROM image WHERE recap_id = ? ORDER BY id",
                            (recap_id,)).fetchall()


# The write itself checks what the policy checked a moment earlier: an Editor
# may change a Recap's Images only while it is their own Draft.
_RECAP_OPEN = ("EXISTS (SELECT 1 FROM recap WHERE id = :recap_id AND "
               "(:editor_id IS NULL OR (status = 'draft' AND owner_id = :editor_id)))")


def _touch_recap(conn, recap_id: int) -> None:
    """An Image is part of its Recap, so adding or removing one is an edit."""
    conn.execute("UPDATE recap SET edited_at = "
                 "strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
                 (recap_id,))


def add_image(recap_id: int, data: bytes | None, alt: str,
              editor_id: int | None = None) -> sqlite3.Row | None:
    """Validate and store an upload; return its row. Raises ImageRefused with a
    message for the person. Returns None, storing nothing, if `editor_id` no
    longer owns a Draft Recap `recap_id`."""
    alt = clean_alt(alt)
    if not data:
        raise ImageRefused(FILE_ERROR)
    if not alt:
        raise ImageRefused(ALT_ERROR)
    if len(data) > MAX_BYTES:
        raise ImageRefused(SIZE_ERROR)
    kind = sniff(data)
    if kind is None:
        raise ImageRefused(TYPE_ERROR)
    extension, content_type = kind

    filename = f"{secrets.token_hex(16)}.{extension}"
    settings.UPLOADS.mkdir(parents=True, exist_ok=True)
    path = settings.UPLOADS / filename
    path.write_bytes(data)
    try:
        with db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO image (recap_id, filename, content_type, size, alt) "
                f"SELECT :recap_id, :filename, :content_type, :size, :alt "
                f"WHERE {_RECAP_OPEN}",
                {"recap_id": recap_id, "filename": filename, "editor_id": editor_id,
                 "content_type": content_type, "size": len(data), "alt": alt})
            if cur.rowcount == 0:
                path.unlink()
                return None
            _touch_recap(conn, recap_id)
            return conn.execute("SELECT * FROM image WHERE id = ?",
                                (cur.lastrowid,)).fetchone()
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def get_image(image_id: int) -> sqlite3.Row | None:
    with db.connect() as conn:
        return conn.execute("SELECT * FROM image WHERE id = ?",
                            (image_id,)).fetchone()


def remove_files(filenames: list[str]) -> None:
    for filename in filenames:
        (settings.UPLOADS / filename).unlink(missing_ok=True)


def delete_image(image_id: int, recap_id: int,
                 editor_id: int | None = None) -> bool:
    """Delete one Image of a Recap, row and file. False, deleting nothing, if
    `editor_id` no longer owns a Draft Recap `recap_id`."""
    with db.connect() as conn:
        row = conn.execute(
            f"SELECT filename FROM image WHERE id = :image_id "
            f"AND recap_id = :recap_id AND {_RECAP_OPEN}",
            {"image_id": image_id, "recap_id": recap_id,
             "editor_id": editor_id}).fetchone()
        if row is None:
            return False
        conn.execute("DELETE FROM image WHERE id = ?", (image_id,))
        _touch_recap(conn, recap_id)
    remove_files([row["filename"]])
    return True
