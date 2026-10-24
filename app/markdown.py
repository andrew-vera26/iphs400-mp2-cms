"""Body -> sanitized HTML. The only place a Body is turned into HTML.

Preview and `cms publish` both call `render_body`, so what the editor shows is
what readers get. markdown-it-py renders first, then nh3 enforces an allowlist.
"""
from __future__ import annotations

import re
from typing import Collection

import nh3
from markdown_it import MarkdownIt
from markdown_it.token import Token

ALLOWED_TAGS = {"a", "blockquote", "br", "code", "em", "h1", "h2", "h3", "h4",
                "h5", "h6", "hr", "img", "li", "ol", "p", "pre", "strong", "ul"}
ALLOWED_ATTRIBUTES = {"a": {"href"}, "img": {"src", "alt"}}

# markdown-it must parse raw HTML as HTML to tell it from text (with html=False
# it becomes escaped text instead). It is parsed only to be thrown away: every
# raw-HTML token is dropped before rendering, so none is ever rendered and none
# leaves text behind. nh3 below is the second layer, enforcing the allowlist on
# whatever markdown-it produced.
_markdown = MarkdownIt("commonmark", {"html": True})

_RAW_CONTENT_TAG = re.compile(r"<(/?)(script|style)\b", re.I)
_SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")
# nh3 leaves a bare <a> where it dropped the href, and an <img> with no src.
_BARE_LINK = re.compile(r"<a>(.*?)</a>", re.S)
_SRCLESS_IMG = re.compile(r"<img(?![^>]*\bsrc=)[^>]*>")


def is_relative(target: str) -> bool:
    """True for a path like ``../other/`` or ``images/a.jpg``. Anything with a
    scheme (http:, mailto:, javascript:), a host (//x) or a root (/x) is not."""
    target = re.sub(r"[\x00-\x20]", "", target).replace("\\", "/")
    return bool(target) and not _SCHEME.match(target) \
        and not target.startswith("/")


def _drop_inline_html(children: list[Token]) -> list[Token]:
    """`children` without raw inline tags, and without anything between an
    opening and closing <script> or <style> (their text is code, not prose)."""
    kept, inside = [], None
    for child in children:
        if child.type == "html_inline":
            found = _RAW_CONTENT_TAG.match(child.content)
            if inside and found and found.group(1) and found.group(2).lower() == inside:
                inside = None
            elif not inside and found and not found.group(1):
                inside = found.group(2).lower()
        elif not inside:
            kept.append(child)
    return kept


def _render_without_raw_html(body: str) -> str:
    tokens = [t for t in _markdown.parse(body) if t.type != "html_block"]
    for token in tokens:
        if token.type == "inline" and token.children:
            token.children = _drop_inline_html(token.children)
    return _markdown.renderer.render(tokens, _markdown.options, {})


def render_body(body: str, image_urls: Collection[str] = ()) -> str:
    """The sanitized HTML for a Markdown Body.

    Links survive only if relative. Images survive only if their source is one
    of `image_urls` (the Recap's own uploaded Images, as `images/<file>`). A removed
    link keeps its text; a removed image leaves nothing. Raw HTML in the Body is
    removed whole: a raw block disappears, a raw inline tag disappears and the
    Markdown text around it stays.
    """
    own = set(image_urls)

    def keep(tag: str, attr: str, value: str) -> str | None:
        if tag == "a" and attr == "href":
            return value if is_relative(value) else None
        if tag == "img" and attr == "src":
            return value if value in own else None
        return value

    html = nh3.clean(_render_without_raw_html(body), tags=ALLOWED_TAGS,
                     attributes=ALLOWED_ATTRIBUTES, url_schemes=set(),
                     link_rel=None, attribute_filter=keep)
    return _SRCLESS_IMG.sub("", _BARE_LINK.sub(r"\1", html))


_IMG_TAG = re.compile(r"<img\b[^>]*>")
_ALT = re.compile(r'\balt="([^"]*)"')


def images_without_alt(body: str, image_urls: Collection[str] = ()) -> int:
    """How many of the Body's kept images have blank alt text. Counted on the
    output of `render_body`, so only images that would be shown count."""
    return sum(1 for tag in _IMG_TAG.findall(render_body(body, image_urls))
               if not (m := _ALT.search(tag)) or not m.group(1).strip())
