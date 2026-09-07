"""Static redirect stubs for content whose slug (hence URL) changed.

A slug rename doesn't rename the underlying .md file (see
content/writer.py: an existing file keeps its filename on save
regardless of its slug — only a brand-new document's filename is
derived from the slug), so the file's own path is a stable identity to
track across builds. This module keeps a small on-disk history of
every URL each source file has ever produced and, once a URL is no
longer current, writes a small HTML stub at the old address that
meta-refreshes to the new one — the closest a fully static site (no
server-side redirect capability) can get to a real redirect, so old
bookmarks, backlinks, and search engine index entries don't just 404.

Deliberately narrow: this handles *renames*, not deletions — content
with no current URL at all keeps no redirect (there is nothing sound
to redirect it to), and a page/post converted between page and post
(content/writer.py's write_content_file actually renames the file in
that one case) is treated as a fresh, unrelated file, same as any
other genuinely new content.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path


@dataclass(slots=True, frozen=True)
class RedirectPlan:
    stale_url: str
    target_url: str
    source_key: str


def load_url_history(history_path: Path) -> dict[str, list[str]]:
    if not history_path.exists():
        return {}
    try:
        data = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        key: [str(url) for url in urls]
        for key, urls in data.items()
        if isinstance(urls, list)
    }


def save_url_history(history_path: Path, history: dict[str, list[str]]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(history, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    history_path.write_text(payload, encoding="utf-8")


def update_history(history: dict[str, list[str]], current: dict[str, str]) -> dict[str, list[str]]:
    """Append-only: a URL already recorded for a source is never
    removed, so a slug changed twice (A -> B -> C) keeps both A and B
    redirecting through to whatever is current."""
    updated: dict[str, list[str]] = {key: list(urls) for key, urls in history.items()}
    for key, url in current.items():
        urls = updated.setdefault(key, [])
        if not urls or urls[-1] != url:
            urls.append(url)
    return updated


def plan_redirects(history: dict[str, list[str]], current: dict[str, str]) -> list[RedirectPlan]:
    """One plan per (source, stale url) pair — skipping a stale url that
    now happens to be some *other* source's real, current URL (never
    overwrite live content with a redirect stub)."""
    current_urls = set(current.values())
    plans: list[RedirectPlan] = []
    for key in sorted(history):
        target = current.get(key)
        if target is None:
            continue
        for stale in history[key]:
            if stale == target or stale in current_urls:
                continue
            plans.append(RedirectPlan(stale_url=stale, target_url=target, source_key=key))
    return plans


def render_redirect_html(href: str) -> str:
    escaped = escape(href)
    return (
        "<!doctype html>\n"
        "<html>\n"
        "  <head>\n"
        '    <meta charset="utf-8">\n'
        f'    <meta http-equiv="refresh" content="0; url={escaped}">\n'
        f'    <link rel="canonical" href="{escaped}">\n'
        '    <meta name="robots" content="noindex">\n'
        "    <title>Redirection</title>\n"
        "  </head>\n"
        "  <body>\n"
        f'    Cette page a été déplacée. <a href="{escaped}">Continuer vers la nouvelle adresse</a>.\n'
        "  </body>\n"
        "</html>\n"
    )
