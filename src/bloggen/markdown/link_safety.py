"""Shared destination-safety policy for ``InlineRun.link_href``.

A single ``sanitize_link_href`` is the one place that decides whether a
link destination is safe to keep as a structured, publishable link —
used by every path that can produce or serialize an ``InlineRun`` with a
``link_href`` (pasted HTML, Markdown import, Markdown export), so the
policy can't drift between them.

This is about link *destinations* only (``<a href>`` / Markdown link
targets). Image sources have their own, unrelated safety policy in
:mod:`bloggen.markdown.html_paste_import` and are not affected by this
module.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

# Deliberately small: only schemes that cannot execute code or embed
# arbitrary payloads in a browser context. Everything else (javascript:,
# data:, vbscript:, and any scheme not on this list) is refused rather than
# enumerated, since an allowlist here is the only way to be sure a new or
# obscure active scheme doesn't slip through unnoticed. A href with no
# scheme at all (relative path, ``#fragment``, ``//protocol-relative``) is
# always accepted, matching historical editorial link usage.
_ALLOWED_LINK_SCHEMES = {"http", "https", "mailto", "tel"}
# Trivial obfuscation (stray control characters within or around the
# scheme, e.g. "java\tscript:") is stripped before the scheme is judged, so
# that normalizing away the noise can't turn a rejected scheme into an
# accepted one.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_link_href(href: str | None) -> str | None:
    """Returns ``href`` if it's safe to keep as a link destination, else ``None``.

    The caller's job is to keep the run's visible text regardless of the
    outcome — only the ``link_href`` itself is ever dropped.
    """
    if not href:
        return None
    cleaned = _CONTROL_CHARS_RE.sub("", href).strip()
    if not cleaned:
        return None
    scheme = urlparse(cleaned).scheme.lower()
    if scheme and scheme not in _ALLOWED_LINK_SCHEMES:
        return None
    return cleaned
