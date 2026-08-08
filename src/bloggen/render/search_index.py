"""Client-side static search index (search-index.json).

MEROPE generates a fully static site (no server, no database), so "search"
means: a small JSON index built at generation time, loaded and filtered
entirely in the visitor's browser (see resources/js/search.js). No new
dependency is needed — plain-text extraction reuses the same
``lxml.html`` idiom already used in :mod:`bloggen.render.margin_notes`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from lxml import html


@dataclass(slots=True)
class SearchEntry:
    title: str
    url: str
    excerpt: str
    text: str


def extract_plain_text(html_fragment: str) -> str:
    """Strip HTML tags and collapse whitespace, for indexing/search matching."""
    if not html_fragment.strip():
        return ""
    fragment = html.fromstring(f"<div>{html_fragment}</div>")
    # itertext() (joined with spaces), not text_content(), because
    # text_content() concatenates text nodes with no separator at all,
    # gluing e.g. adjacent <li>un</li><li>deux</li> into "undeux".
    return " ".join(" ".join(fragment.itertext()).split())


def render_search_index(entries: list[SearchEntry]) -> str:
    payload = [
        {"title": entry.title, "url": entry.url, "excerpt": entry.excerpt, "text": entry.text}
        for entry in entries
    ]
    return json.dumps(payload, ensure_ascii=False)
