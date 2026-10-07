"""Reserved Markdown syntax of the Mérope embedded video block.

A video is a Pandoc fenced div carrying a Mérope-only class and two
attributes::

    :::: {.merope-video data-provider="youtube" data-video-id="dQw4w9WgXcQ"}
    Légende facultative de la vidéo.
    ::::

Deliberately written with no blank line between the opening fence, the
(optional) caption paragraph and the closing fence: the rich-text
importer (:mod:`bloggen.markdown.rich_text_import`) only splits chunks on
blank lines, so this whole span already reaches it as a single chunk —
and ``FENCED_DIV_LINE_RE`` (any line starting with three or more colons,
see :mod:`bloggen.markdown.box_syntax`) already forces that chunk to
``VERBATIM`` rather than being guessed at as a paragraph. No change to the
importer/exporter is needed for this block to round-trip byte-for-byte
and stay immune to the editors' ordinary formatting commands.

``data-provider`` carries the provider name so a second provider (e.g.
Vimeo) could be added later without changing this syntax; only
``"youtube"`` is accepted in this version. The Pandoc Lua filter shipped
in ``resources/pandoc/merope_video.lua`` turns this syntax into native
TEI Commons Publishing (a ``<figure>``/``<ref>``/``<figDesc>``
construction); the class name and attribute names below must stay in
sync with it, and the video id grammar must stay in sync with its own
(independent) validation of the same shape, since a hand-written or
externally produced Markdown file never goes through this module at all.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

VIDEO_CLASS = "merope-video"
VIDEO_CLOSE = "::::"

# The only provider accepted in this version. The syntax already carries
# a provider name so a future addition (e.g. "vimeo") does not need a
# format change — only this set, the URL parser, and the Lua filter's own
# validation would grow.
SUPPORTED_PROVIDERS = frozenset({"youtube"})

# YouTube video ids are always 11 characters from this exact alphabet.
_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

_VIDEO_OPEN_RE = re.compile(
    r'^:::: \{\.merope-video data-provider="(?P<provider>[^"]*)"'
    r' data-video-id="(?P<video_id>[^"]*)"\}$'
)

# Markdown inline-emphasis delimiters that must not be allowed to leak
# out of a plain-text caption typed into a dialog's single-line field.
_MD_ESCAPE_RE = re.compile(r"([\\`*_\[\]^~])")


def is_valid_youtube_id(video_id: str) -> bool:
    return bool(_YOUTUBE_ID_RE.match(video_id))


def parse_video_open_line(line: str) -> tuple[str, str] | None:
    """``(provider, video_id)`` if ``line`` has the reserved opening-fence
    shape, whatever their value — this only recognizes the *shape*, used by
    callers that need to spot the construction (e.g. tests); it never
    replaces the strict validation the Lua filter and
    :func:`parse_youtube_url` perform before any TEI/HTML is produced."""

    match = _VIDEO_OPEN_RE.match(line)
    if match is None:
        return None
    return match.group("provider"), match.group("video_id")


def parse_youtube_url(url: str) -> str | None:
    """Extract and strictly validate a canonical YouTube video id from a
    user-supplied URL, or ``None`` if it is not confidently recognized.

    Uses real URL parsing (never string replacement) and accepts only:

    - ``https://www.youtube.com/watch?v=ID`` (``www.`` optional, extra
      query parameters such as ``&t=`` or ``?si=`` are ignored)
    - ``https://youtu.be/ID``
    - ``https://www.youtube.com/embed/ID``
    - ``https://www.youtube.com/shorts/ID``

    Only ``http``/``https`` schemes are accepted, the hostname is checked
    against an exact allow-list (no look-alike or arbitrary subdomain is
    accepted), and the extracted id must match :func:`is_valid_youtube_id`
    — never returned otherwise.
    """

    if not isinstance(url, str) or not url.strip():
        return None
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https"):
        return None

    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[len("www."):]

    segments = [segment for segment in parsed.path.split("/") if segment]
    video_id: str | None = None

    if host == "youtu.be":
        if len(segments) == 1:
            video_id = segments[0]
    elif host == "youtube.com":
        if segments and segments[0] == "watch":
            values = parse_qs(parsed.query).get("v")
            if values:
                video_id = values[0]
        elif len(segments) == 2 and segments[0] in ("embed", "shorts"):
            video_id = segments[1]

    if video_id is None or not is_valid_youtube_id(video_id):
        return None
    return video_id


def youtube_watch_url(video_id: str) -> str:
    """Canonical watch-page URL built only from a validated id."""

    return f"https://www.youtube.com/watch?v={video_id}"


def _escape_caption(text: str) -> str:
    return _MD_ESCAPE_RE.sub(r"\\\1", text)


def format_video_block(video_id: str, caption: str = "", *, provider: str = "youtube") -> str:
    """Render the reserved Mérope fenced-div Markdown for a validated video.

    Raises ``ValueError`` for an unsupported provider or an invalid id —
    callers (the Qt insertion dialog, tests) are expected to have already
    validated the id via :func:`parse_youtube_url`.
    """

    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Fournisseur vidéo non pris en charge : {provider!r}")
    if not is_valid_youtube_id(video_id):
        raise ValueError(f"Identifiant vidéo YouTube invalide : {video_id!r}")

    open_line = f':::: {{.{VIDEO_CLASS} data-provider="{provider}" data-video-id="{video_id}"}}'
    normalized_caption = _escape_caption(" ".join(caption.split()))
    if normalized_caption:
        return f"{open_line}\n{normalized_caption}\n{VIDEO_CLOSE}"
    return f"{open_line}\n{VIDEO_CLOSE}"
