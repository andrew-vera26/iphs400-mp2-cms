"""T06: Images.

Seams: the HTTP app through TestClient, and `app.publish.render_site(out)`.
Routes under test:

    POST /admin/recaps/{id}/images                    multipart: file, alt
    POST /admin/recaps/{id}/images/{image_id}/delete
    GET  /admin/recaps/{id}/images/{stored file}      the console's own copy

Uploads are stored flat in `settings.UPLOADS` (gitignored, outside `site/`).
After an upload the page shows a Markdown snippet `![alt](images/<file>)`.
A Published Recap's Images are copied next to its page by `render_site`.
"""
import html
import re

import pytest

from app import images, settings
from app.markdown import render_body
from app.publish import PublishRefused, render_site
from tests.conftest import csrf_from
from tests.test_t03 import (RECAPS, make_recap, make_trip, post, recap_form,
                            recap_row, rows, second_editor)
from tests import test_t05

MB = 1024 * 1024
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64 + b"\xff\xd9"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"\x00" * 64
WEBP = b"RIFF" + (60).to_bytes(4, "little") + b"WEBPVP8 " + b"\x00" * 52
GIF = b"GIF89a" + b"\x00" * 64
SAMPLES = {"jpg": JPEG, "png": PNG, "webp": WEBP}
CONTENT_TYPES = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}
STORED_NAME = re.compile(r"^[0-9a-f]{16,}\.(jpg|png|webp)$")
SNIPPET = re.compile(r"!\[([^\]]*)\]\((images/[^)\s]+)\)")
ALT = "A crowded committee room"


# ---- helpers --------------------------------------------------------------

@pytest.fixture(autouse=True)
def uploads(tmp_path, monkeypatch):
    """Each test stores uploads in its own empty folder."""
    folder = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOADS", folder)
    return folder


def stored(folder):
    return sorted(p for p in folder.rglob("*") if p.is_file()) \
        if folder.exists() else []


def upload(c, recap_id, data=PNG, filename="holiday.png",
           content_type="image/png", alt=ALT, token=True):
    fields = {"alt": alt}
    if token:
        fields["csrf_token"] = csrf_from(c.get("/admin"))
    return c.post(f"{RECAPS}/{recap_id}/images", data=fields,
                  files={"file": (filename, data, content_type)},
                  follow_redirects=False)


def editors_recap(client_as, status="draft"):
    """An Editor's Recap moved to `status`; returns (recap_id, editor client)."""
    trip_id = make_trip(client_as("admin"))
    editor = client_as("editor")
    recap_id = make_recap(editor, trip_id)
    if status in ("submitted", "published"):
        assert post(editor, f"{RECAPS}/{recap_id}/submit").status_code == 303
    if status == "published":
        assert post(client_as("admin"), f"{RECAPS}/{recap_id}/publish"
                    ).status_code == 303
    return recap_id, editor


def uploaded(client, recap_id, *args, **kwargs):
    """Upload through the route; return the stored file name."""
    before = set(stored(settings.UPLOADS))
    assert upload(client, recap_id, *args, **kwargs).status_code == 200
    (new,) = set(stored(settings.UPLOADS)) - before
    return new.name


def image_rows(recap_id):
    return rows("SELECT * FROM image WHERE recap_id = ?", recap_id)


def set_body(client, recap_id, body):
    r = post(client, f"{RECAPS}/{recap_id}", **recap_form(
        recap_row(recap_id)["trip_id"], body=body,
        byline_name="Contributor Name", byline_class_year="2027"))
    assert r.status_code == 303, r.text


def error_message(page):
    """The text of the page's error element, `<p role="alert">`. The form's own
    labels mention the same words, so the message must be read from here."""
    match = re.search(r'<p role="alert">(.*?)</p>', page, re.S)
    assert match, "page has no error element"
    return html.unescape(match.group(1))


def preview_region(html):
    match = re.search(r'<section id="preview">(.*?)</section>', html, re.S)
    assert match, "page has no <section id=\"preview\">"
    return match.group(1)


def preview(client, recap_id, body):
    r = post(client, f"{RECAPS}/{recap_id}/preview",
             **recap_form(recap_row(recap_id)["trip_id"], body=body))
    assert r.status_code == 200
    return preview_region(r.text)


# ---- accepted uploads -----------------------------------------------------

@pytest.mark.parametrize("kind", ["jpg", "png", "webp"])
def test_valid_image_is_stored_and_a_markdown_snippet_is_shown(
        client_as, uploads, kind):
    recap_id, editor = editors_recap(client_as)
    r = upload(editor, recap_id, SAMPLES[kind], f"holiday.{kind}",
               CONTENT_TYPES[kind])
    assert r.status_code == 200

    (path,) = stored(uploads)
    assert path.read_bytes() == SAMPLES[kind]
    assert path.suffix == f".{kind}"
    snippet = SNIPPET.search(r.text)
    assert snippet and snippet.group(1) == ALT
    assert snippet.group(2) == f"images/{path.name}"

    (row,) = image_rows(recap_id)
    assert row["filename"] == path.name and row["alt"] == ALT
    assert row["content_type"] == CONTENT_TYPES[kind]
    assert row["size"] == len(SAMPLES[kind])


def test_the_stored_name_is_generated_never_the_users(client_as, uploads):
    recap_id, editor = editors_recap(client_as)
    first = uploaded(editor, recap_id, filename="../../etc/holiday photo.png")
    second = uploaded(editor, recap_id, filename="../../etc/holiday photo.png")
    assert STORED_NAME.match(first) and STORED_NAME.match(second)
    assert first != second
    assert not [p for p in settings.UPLOADS.parent.rglob("*")
                if "holiday" in p.name]


def test_the_real_type_decides_not_the_extension_or_header(client_as, uploads):
    recap_id, editor = editors_recap(client_as)
    name = uploaded(editor, recap_id, JPEG, "scan.txt", "text/plain")
    assert name.endswith(".jpg")


def test_an_admin_can_upload_to_any_recap_even_a_published_one(client_as):
    recap_id, _ = editors_recap(client_as, "published")
    assert upload(client_as("admin"), recap_id).status_code == 200
    assert len(image_rows(recap_id)) == 1


# ---- refused uploads ------------------------------------------------------

@pytest.mark.parametrize("data,filename,content_type", [
    (b"just some text, not a picture", "photo.jpg", "image/jpeg"),
    (b"<script>alert(1)</script>", "photo.png", "image/png"),
    (GIF, "photo.png", "image/png"),
    (b"%PDF-1.7 " + b"\x00" * 64, "photo.webp", "image/webp"),
])
def test_a_file_of_the_wrong_type_is_refused_with_a_message(
        client_as, uploads, data, filename, content_type):
    recap_id, editor = editors_recap(client_as)
    r = upload(editor, recap_id, data, filename, content_type)
    assert r.status_code == 400
    assert error_message(r.text) == images.TYPE_ERROR
    assert stored(uploads) == [] and image_rows(recap_id) == []


def test_a_zero_byte_file_is_refused_with_a_message(client_as, uploads):
    recap_id, editor = editors_recap(client_as)
    r = upload(editor, recap_id, b"", "photo.png", "image/png")
    assert r.status_code == 400
    assert error_message(r.text) == images.FILE_ERROR
    assert stored(uploads) == [] and image_rows(recap_id) == []


def test_a_file_over_the_size_limit_is_refused_with_a_message(
        client_as, uploads):
    recap_id, editor = editors_recap(client_as)
    r = upload(editor, recap_id, PNG + b"\x00" * (5 * MB))
    assert r.status_code == 400
    assert error_message(r.text) == images.SIZE_ERROR
    assert stored(uploads) == [] and image_rows(recap_id) == []


def test_a_file_just_under_the_limit_is_accepted(client_as, uploads):
    recap_id, editor = editors_recap(client_as)
    assert upload(editor, recap_id, PNG + b"\x00" * (5 * MB - len(PNG) - 1)
                  ).status_code == 200


@pytest.mark.parametrize("alt", ["", "   ", "\t\n"])
def test_missing_alt_text_is_refused(client_as, uploads, alt):
    recap_id, editor = editors_recap(client_as)
    r = upload(editor, recap_id, alt=alt)
    assert r.status_code == 400
    assert error_message(r.text) == images.ALT_ERROR
    assert stored(uploads) == [] and image_rows(recap_id) == []


def test_an_upload_with_no_file_is_refused(client_as, uploads):
    recap_id, editor = editors_recap(client_as)
    r = editor.post(f"{RECAPS}/{recap_id}/images",
                    data={"alt": ALT, "csrf_token": csrf_from(editor.get("/admin"))},
                    follow_redirects=False)
    assert r.status_code in (400, 422)
    assert stored(uploads) == []


def test_the_alt_text_cannot_break_out_of_the_markdown_snippet(client_as):
    """Pasting the shown snippet into a Body gives one image carrying the whole
    alt text, and no link."""
    recap_id, editor = editors_recap(client_as)
    r = upload(editor, recap_id, alt="Jane [left] and\nRaj](https://evil.example)")
    assert r.status_code == 200
    (name,) = [p.name for p in stored(settings.UPLOADS)]
    snippet = re.search(r'<code id="snippet">(.*?)</code>', r.text, re.S)
    markdown = html.unescape(snippet.group(1))
    assert "\n" not in markdown
    rendered = render_body(markdown, {f"images/{name}"})
    assert rendered.count("<img") == 1 and "<a" not in rendered
    assert "href" not in rendered and 'alt="Jane' in rendered
    assert "Raj" in rendered  # the text after the stray bracket stayed in the alt


# ---- ownership and status -------------------------------------------------

def test_an_editor_cannot_upload_to_another_persons_recap(client_as, uploads):
    recap_id, _ = editors_recap(client_as)
    assert upload(second_editor(), recap_id).status_code == 403
    assert stored(uploads) == [] and image_rows(recap_id) == []


@pytest.mark.parametrize("status", ["submitted", "published"])
def test_an_editor_cannot_upload_after_submitting(client_as, uploads, status):
    recap_id, editor = editors_recap(client_as, status)
    assert upload(editor, recap_id).status_code == 403
    assert stored(uploads) == [] and image_rows(recap_id) == []


def test_uploading_to_a_missing_recap_is_a_404(client_as):
    recap_id, editor = editors_recap(client_as)
    assert upload(editor, recap_id).status_code == 200  # the route exists
    assert upload(editor, 9999).status_code == 404


def test_a_logged_out_visitor_is_sent_to_the_login_page(client_as, client):
    recap_id, _ = editors_recap(client_as)
    r = client.post(f"{RECAPS}/{recap_id}/images", data={"alt": ALT},
                    files={"file": ("a.png", PNG, "image/png")},
                    follow_redirects=False)
    assert r.status_code in (303, 403)
    assert image_rows(recap_id) == []


# ---- CSRF -----------------------------------------------------------------

def test_an_upload_without_a_csrf_token_is_refused(client_as, uploads):
    recap_id, editor = editors_recap(client_as)
    assert upload(editor, recap_id, token=False).status_code == 403
    assert stored(uploads) == []


def test_a_delete_without_a_csrf_token_is_refused(client_as, uploads):
    recap_id, editor = editors_recap(client_as)
    uploaded(editor, recap_id)
    (row,) = image_rows(recap_id)
    r = editor.post(f"{RECAPS}/{recap_id}/images/{row['id']}/delete",
                    follow_redirects=False)
    assert r.status_code == 403
    assert len(image_rows(recap_id)) == 1 and len(stored(uploads)) == 1


def test_the_upload_and_delete_forms_carry_a_csrf_token(client_as):
    recap_id, editor = editors_recap(client_as)
    uploaded(editor, recap_id)
    (row,) = image_rows(recap_id)
    page = editor.get(f"{RECAPS}/{recap_id}").text
    forms = {m.group(1): m.group(0) for m in re.finditer(
        r'<form[^>]*action="([^"]+)"[^>]*>.*?</form>', page, re.S)}
    upload_form = forms[f"{RECAPS}/{recap_id}/images"]
    assert 'enctype="multipart/form-data"' in upload_form
    assert 'type="file"' in upload_form and 'name="alt"' in upload_form
    assert 'name="csrf_token"' in upload_form
    assert 'name="csrf_token"' in forms[
        f"{RECAPS}/{recap_id}/images/{row['id']}/delete"]


# ---- deleting one Image ---------------------------------------------------

def test_an_editor_deletes_an_image_from_their_own_draft(client_as, uploads):
    recap_id, editor = editors_recap(client_as)
    uploaded(editor, recap_id)
    (row,) = image_rows(recap_id)
    r = post(editor, f"{RECAPS}/{recap_id}/images/{row['id']}/delete")
    assert r.status_code == 303
    assert image_rows(recap_id) == [] and stored(uploads) == []


def test_an_editor_cannot_delete_from_another_persons_recap(client_as, uploads):
    recap_id, editor = editors_recap(client_as)
    uploaded(editor, recap_id)
    (row,) = image_rows(recap_id)
    r = post(second_editor(), f"{RECAPS}/{recap_id}/images/{row['id']}/delete")
    assert r.status_code == 403
    assert len(image_rows(recap_id)) == 1 and len(stored(uploads)) == 1


@pytest.mark.parametrize("status", ["submitted", "published"])
def test_an_editor_cannot_delete_after_submitting(client_as, uploads, status):
    recap_id, editor = editors_recap(client_as)
    uploaded(editor, recap_id)
    (row,) = image_rows(recap_id)
    assert post(editor, f"{RECAPS}/{recap_id}/submit").status_code == 303
    if status == "published":
        assert post(client_as("admin"), f"{RECAPS}/{recap_id}/publish"
                    ).status_code == 303
    r = post(editor, f"{RECAPS}/{recap_id}/images/{row['id']}/delete")
    assert r.status_code == 403
    assert len(image_rows(recap_id)) == 1 and len(stored(uploads)) == 1


def test_an_admin_can_delete_an_image_from_any_recap(client_as, uploads):
    recap_id, editor = editors_recap(client_as, "published")
    uploaded(client_as("admin"), recap_id)
    (row,) = image_rows(recap_id)
    r = post(client_as("admin"), f"{RECAPS}/{recap_id}/images/{row['id']}/delete")
    assert r.status_code == 303
    assert image_rows(recap_id) == [] and stored(uploads) == []


def test_an_image_cannot_be_deleted_through_a_different_recap(client_as, uploads):
    trip_id = make_trip(client_as("admin"))
    editor = client_as("editor")
    mine = make_recap(editor, trip_id)
    theirs = make_recap(editor, trip_id, slug="other-recap", title="Other")
    uploaded(editor, theirs)
    (row,) = image_rows(theirs)
    r = post(editor, f"{RECAPS}/{mine}/images/{row['id']}/delete")
    assert r.status_code == 404
    assert len(image_rows(theirs)) == 1 and len(stored(uploads)) == 1


# ---- deleting a Recap -----------------------------------------------------

def test_deleting_a_recap_removes_its_images_from_storage(client_as, uploads):
    trip_id = make_trip(client_as("admin"))
    editor = client_as("editor")
    doomed = make_recap(editor, trip_id)
    kept = make_recap(editor, trip_id, slug="kept", title="Kept")
    uploaded(editor, doomed)
    uploaded(editor, doomed, JPEG, "b.jpg", "image/jpeg")
    kept_name = uploaded(editor, kept)

    assert post(editor, f"{RECAPS}/{doomed}/delete").status_code == 303
    assert image_rows(doomed) == []
    assert [p.name for p in stored(uploads)] == [kept_name]
    assert len(image_rows(kept)) == 1


def test_an_admin_deleting_a_recap_removes_its_images_too(client_as, uploads):
    recap_id, editor = editors_recap(client_as)
    uploaded(editor, recap_id)
    assert post(client_as("admin"), f"{RECAPS}/{recap_id}/delete"
                ).status_code == 303
    assert stored(uploads) == [] and image_rows(recap_id) == []


def test_a_refused_recap_delete_keeps_its_images(client_as, uploads):
    recap_id, editor = editors_recap(client_as)
    uploaded(editor, recap_id)
    assert post(second_editor(), f"{RECAPS}/{recap_id}/delete"
                ).status_code == 403
    assert len(stored(uploads)) == 1 and len(image_rows(recap_id)) == 1


# ---- Preview --------------------------------------------------------------

def test_preview_shows_the_recaps_own_uploaded_images(client_as):
    recap_id, editor = editors_recap(client_as)
    name = uploaded(editor, recap_id)
    html = preview(editor, recap_id, f"Look:\n\n![{ALT}](images/{name})")
    assert f'src="images/{name}"' in html and f'alt="{ALT}"' in html


def test_preview_still_strips_external_and_unknown_images(client_as):
    recap_id, editor = editors_recap(client_as)
    html = preview(editor, recap_id,
                   "![x](https://evil.example/p.png) ![y](images/not-mine.png) "
                   "![z](/admin/recaps/1/images/a.png) end")
    assert "<img" not in html and "evil.example" not in html
    assert "end" in html


def test_preview_does_not_show_another_recaps_image(client_as):
    trip_id = make_trip(client_as("admin"))
    editor = client_as("editor")
    mine = make_recap(editor, trip_id)
    theirs = make_recap(editor, trip_id, slug="other-recap", title="Other")
    name = uploaded(editor, theirs)
    assert "<img" not in preview(editor, mine, f"![{ALT}](images/{name})")


def test_preview_image_resolves_in_the_console(client_as):
    """Preview is served from .../{id}/preview, so `images/<file>` resolves to
    /admin/recaps/{id}/images/<file>."""
    recap_id, editor = editors_recap(client_as)
    name = uploaded(editor, recap_id, JPEG, "a.jpg", "image/jpeg")
    r = editor.get(f"{RECAPS}/{recap_id}/images/{name}")
    assert r.status_code == 200 and r.content == JPEG
    assert r.headers["content-type"].startswith("image/jpeg")


def test_console_image_is_only_for_people_who_may_view_the_recap(
        client_as, client):
    recap_id, editor = editors_recap(client_as)
    name = uploaded(editor, recap_id)
    path = f"{RECAPS}/{recap_id}/images/{name}"
    assert client_as("admin").get(path).status_code == 200
    assert second_editor().get(path).status_code == 403
    assert client.get(path, follow_redirects=False).status_code in (303, 403)
    assert editor.get(f"{RECAPS}/{recap_id}/images/unknown.png"
                      ).status_code == 404
    assert editor.get(f"{RECAPS}/{recap_id}/images/..%2F..%2Fcms.db"
                      ).status_code in (404, 422)


# ---- Publish refused while an image has no alt text -----------------------

@pytest.mark.parametrize("alt", ["", "   "])
def test_publish_is_refused_while_the_body_has_an_image_without_alt(
        client_as, alt):
    recap_id, editor = editors_recap(client_as)
    name = uploaded(editor, recap_id)
    set_body(editor, recap_id, f"Photo:\n\n![{alt}](images/{name})")
    r = post(client_as("admin"), f"{RECAPS}/{recap_id}/publish")
    assert r.status_code == 400
    assert recap_row(recap_id)["status"] == "draft"


def test_publish_succeeds_once_the_image_has_alt_text(client_as):
    recap_id, editor = editors_recap(client_as)
    name = uploaded(editor, recap_id)
    set_body(editor, recap_id, f"Photo:\n\n![{ALT}](images/{name})")
    assert post(client_as("admin"), f"{RECAPS}/{recap_id}/publish"
                ).status_code == 303
    assert recap_row(recap_id)["status"] == "published"


def test_publish_is_refused_for_a_submitted_recap_with_an_altless_image(
        client_as):
    recap_id, editor = editors_recap(client_as)
    name = uploaded(editor, recap_id)
    set_body(editor, recap_id, f"![](images/{name})")
    assert post(editor, f"{RECAPS}/{recap_id}/submit").status_code == 303
    assert post(client_as("admin"), f"{RECAPS}/{recap_id}/publish"
                ).status_code == 400
    assert recap_row(recap_id)["status"] == "submitted"


# ---- cms publish ----------------------------------------------------------

def published_recap_with_image(client_as, slug="food-crawl", status="published"):
    """A Recap in `status` whose Body places one uploaded Image; returns
    (trip_id, recap_id, stored name)."""
    trip_id = test_t05.make_trip("2026-chicago", "2026-03-01")
    recap_id = test_t05.make_recap(trip_id, slug, status="draft")
    name = uploaded(client_as("admin"), recap_id)
    with_image = f"Look:\n\n![{ALT}](images/{name})"
    from app import db, recaps
    with db.connect() as conn:
        conn.execute("UPDATE recap SET body = ? WHERE id = ?",
                     (with_image, recap_id))
    if status in ("submitted", "published"):
        recaps.transition(recap_id, "submit")
    if status == "published":
        recaps.transition(recap_id, "publish")
    return trip_id, recap_id, name


def test_a_published_recaps_image_is_copied_next_to_its_page(
        client_as, tmp_path):
    _, _, name = published_recap_with_image(client_as)
    out = render_site(tmp_path / "site")
    page = out / "trips/2026-chicago/food-crawl"
    assert (page / "images" / name).read_bytes() == PNG
    html = (page / "index.html").read_text()
    assert f'<img src="images/{name}" alt="{ALT}">' in html


def test_image_references_in_the_output_are_relative_and_resolve(
        client_as, tmp_path):
    published_recap_with_image(client_as)
    out = render_site(tmp_path / "site")
    for html_file in out.rglob("*.html"):
        for src in re.findall(r'src="([^"]*)"', html_file.read_text()):
            assert not src.startswith(("/", "http:", "https:", "//")), src
            assert (html_file.parent / src).is_file(), (html_file, src)


@pytest.mark.parametrize("status", ["draft", "submitted"])
def test_images_of_recaps_that_are_not_published_are_not_copied(
        client_as, tmp_path, status):
    _, _, name = published_recap_with_image(client_as, status=status)
    out = render_site(tmp_path / "site")
    assert not [p for p in out.rglob("*") if p.name == name]
    assert not [p for p in out.rglob("*") if p.suffix in (".png", ".jpg", ".webp")]


def test_only_the_published_recaps_images_are_copied(client_as, tmp_path):
    trip_id, _, live = published_recap_with_image(client_as)
    draft = test_t05.make_recap(trip_id, "draft-one", status="draft")
    hidden = uploaded(client_as("admin"), draft)
    out = render_site(tmp_path / "site")
    names = {p.name for p in out.rglob("*") if p.is_file()}
    assert live in names and hidden not in names


def test_an_unpublished_recaps_image_leaves_the_output(client_as, tmp_path):
    _, recap_id, name = published_recap_with_image(client_as)
    from app import recaps
    recaps.transition(recap_id, "unpublish")
    out = render_site(tmp_path / "site")
    assert not [p for p in out.rglob("*") if p.name == name]


def test_a_published_page_never_shows_an_external_or_foreign_image(
        client_as, tmp_path):
    trip_id = test_t05.make_trip("2026-chicago", "2026-03-01")
    test_t05.make_recap(trip_id, "hostile", body=test_t05.HOSTILE)
    other = test_t05.make_recap(trip_id, "other", status="draft")
    foreign = uploaded(client_as("admin"), other)
    from app import db
    with db.connect() as conn:
        conn.execute("UPDATE recap SET body = ? WHERE slug = 'hostile'",
                     (f"![x](images/{foreign}) ![y](https://evil.example/p.png)",))
    out = render_site(tmp_path / "site")
    html = (out / "trips/2026-chicago/hostile/index.html").read_text()
    assert "<img" not in html and "evil.example" not in html
    assert not [p for p in out.rglob("*") if p.name == foreign]


# ---- render_site refuses before it touches site/ --------------------------

def existing_site(tmp_path):
    """A previous render in `tmp_path/site`, with a marker to prove it survives."""
    out = tmp_path / "site"
    out.mkdir()
    (out / "marker.txt").write_text("previous render")
    return out


def test_render_site_refuses_a_published_body_with_an_altless_image(
        client_as, tmp_path):
    """The Publish gate only runs on the Publish action; an Admin can edit a
    Published Recap afterwards, so `render_site` checks again."""
    _, recap_id, name = published_recap_with_image(client_as)
    from app import db
    with db.connect() as conn:
        conn.execute("UPDATE recap SET body = ? WHERE id = ?",
                     (f"![](images/{name})", recap_id))
    out = existing_site(tmp_path)
    with pytest.raises(PublishRefused) as refused:
        render_site(out)
    assert "food-crawl" in str(refused.value)
    assert "alt text" in str(refused.value).lower()
    assert (out / "marker.txt").read_text() == "previous render"
    assert [p.name for p in out.iterdir()] == ["marker.txt"]


def test_render_site_ignores_altless_images_in_unpublished_recaps(
        client_as, tmp_path):
    trip_id, _, _ = published_recap_with_image(client_as)
    draft = test_t05.make_recap(trip_id, "draft-one", status="draft")
    name = uploaded(client_as("admin"), draft)
    from app import db
    with db.connect() as conn:
        conn.execute("UPDATE recap SET body = ? WHERE id = ?",
                     (f"![](images/{name})", draft))
    render_site(tmp_path / "site")


def test_render_site_refuses_when_an_image_file_is_missing_and_keeps_site(
        client_as, tmp_path):
    _, _, name = published_recap_with_image(client_as)
    (settings.UPLOADS / name).unlink()
    out = existing_site(tmp_path)
    with pytest.raises(PublishRefused) as refused:
        render_site(out)
    assert "food-crawl" in str(refused.value) and name in str(refused.value)
    assert (out / "marker.txt").read_text() == "previous render"
    assert [p.name for p in out.iterdir()] == ["marker.txt"]


def test_render_site_ignores_a_missing_file_of_an_unpublished_recap(
        client_as, tmp_path):
    _, _, name = published_recap_with_image(client_as, status="draft")
    (settings.UPLOADS / name).unlink()
    render_site(tmp_path / "site")
