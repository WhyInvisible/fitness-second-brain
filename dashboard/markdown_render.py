"""Markdown -> HTML rendering with relative-link rewriting.

The workspace uses relative links like `../concepts/foo.md` and `../MOCs/bar.md`.
The dashboard maps these to its own routes (`/concept/foo`, `/moc/bar`, etc).
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

import markdown
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from markdown.extensions.toc import TocExtension


# Map workspace folder names to dashboard URL prefixes
ROUTE_MAP = {
    "concepts": "/concept",
    "MOCs": "/moc",
    "exercises": "/exercise",
    "plans": "/plan",
    "logs": "/log",
    "references": "/reference",
    "inbox": "/inbox",
}


def _rewrite_md_url(url: str) -> str:
    """Turn workspace-relative .md links into dashboard route URLs.

    Examples:
      ../concepts/glute-amnesia.md           -> /concept/glute-amnesia
      ../MOCs/MOC-running-strength.md#hard   -> /moc/MOC-running-strength#hard
      ../exercises/foo.md                    -> /exercise/foo
      ../resources/garmin/details/1.json     -> (unchanged)
      https://example.com                    -> (unchanged)
      ../images/foo.png                      -> /file/images/foo.png
    """
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https", "mailto", "tel"}:
        return url
    # Anchor-only link
    if url.startswith("#"):
        return url
    # Strip leading ./ and ../ chains, get the meaningful path parts
    path_str = parsed.path or ""
    anchor = f"#{parsed.fragment}" if parsed.fragment else ""

    parts = [p for p in path_str.replace("\\", "/").split("/") if p and p != "."]
    # Drop ..  segments
    parts = [p for p in parts if p != ".."]
    if not parts:
        return url + anchor

    folder = parts[0]
    # .md link inside a known folder => route to dashboard view
    if folder in ROUTE_MAP and len(parts) >= 2 and parts[-1].endswith(".md"):
        slug = parts[-1][:-3]
        return f"{ROUTE_MAP[folder]}/{slug}{anchor}"
    # Non-.md asset (images / pdfs / json) => serve via /file
    if not parts[-1].endswith(".md"):
        return "/file/" + "/".join(parts) + anchor
    # Fall back unchanged
    return url + anchor


_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _rewrite_links_in_md(md_text: str) -> str:
    def repl(m: re.Match) -> str:
        label, url = m.group(1), m.group(2)
        new = _rewrite_md_url(url.strip())
        return f"[{label}]({new})"
    return _LINK_RE.sub(repl, md_text)


def render(md_text: str) -> str:
    """Render markdown to HTML with links rewritten."""
    rewritten = _rewrite_links_in_md(md_text)
    md = markdown.Markdown(extensions=[
        FencedCodeExtension(),
        TableExtension(),
        TocExtension(permalink=False),
        "sane_lists",
        "smarty",
    ])
    return md.convert(rewritten)


# Quick utility for tests
if __name__ == "__main__":
    sample = """# Hi
See [concept](../concepts/foo.md), [moc#anchor](../MOCs/bar.md#anchor),
[exercise](../exercises/baz.md), [image](../images/x.png),
[external](https://example.com).
"""
    print(render(sample))
