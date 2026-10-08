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
import string
from typing import NamedTuple
from urllib.parse import parse_qs, urlparse


class ParsedVideoBlock(NamedTuple):
    """Components of a video block recognized by :func:`parse_video_block`."""

    provider: str
    video_id: str
    caption: str
    width: int


VIDEO_CLASS = "merope-video"
VIDEO_CLOSE = "::::"

# The only provider accepted in this version. The syntax already carries
# a provider name so a future addition (e.g. "vimeo") does not need a
# format change — only this set, the URL parser, and the Lua filter's own
# validation would grow.
SUPPORTED_PROVIDERS = frozenset({"youtube"})

# YouTube video ids are always 11 characters from this exact alphabet.
_YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

# Display width, as a percentage of the content column. 100 % (the whole
# column) is both the default and the historical, pre-width behaviour, so
# it stays the only value that round-trips to the attribute-less form (see
# format_video_block). The Lua filter re-implements this exact rule
# (independently, see merope_video.lua) before it ever reaches the TEI.
DEFAULT_WIDTH = 100
MIN_WIDTH = 25
MAX_WIDTH = 100

_WIDTH_ATTR_RE = re.compile(r"^[0-9]+$")

_VIDEO_OPEN_RE = re.compile(
    r'^:::: \{\.merope-video data-provider="(?P<provider>[^"]*)"'
    r' data-video-id="(?P<video_id>[^"]*)"'
    r'(?: data-width="(?P<width>[^"]*)")?\}$'
)

# The caption is plain, single-line text (see format_video_block), then
# re-injected as literal Markdown *source* inside the fenced div. Escaping
# only the inline-emphasis delimiters (the previous, narrower version of
# this set) is not enough: Pandoc decides block type from the raw,
# unescaped line — "# Titre", "- item", "> quote", "1. first", "---" or
# "::::" at the start of that line become a heading, a list, a
# blockquote, a thematic break or (worse) a premature close of our own
# fenced div, never reaching the caption paragraph at all, and a bare
# "<tag>" can be parsed as raw HTML instead of literal text.
#
# Backslash-escaping *every* ASCII punctuation character sidesteps all of
# these at once, rather than special-casing each construct's leading
# character: CommonMark (and Pandoc's reader) decides block type on the
# literal, unescaped first character of a line, so prefixing any
# would-be marker with "\" removes it from consideration as a marker
# while still rendering as the literal punctuation character once Pandoc
# resolves the escape during inline parsing (verified against Pandoc's
# own JSON AST: every case below in this module's tests round-trips to a
# single Para whose text is exactly the original caption). Using
# string.punctuation keeps this a single systematic rule instead of an
# accumulation of per-construct special cases.
_MD_ESCAPE_RE = re.compile("([" + re.escape(string.punctuation) + "])")


def is_valid_youtube_id(video_id: str) -> bool:
    return bool(_YOUTUBE_ID_RE.match(video_id))


def is_valid_width(width: object) -> bool:
    """Whether ``width`` is a strict integer percentage in [MIN_WIDTH, MAX_WIDTH].

    A ``bool`` is rejected even though it is technically an ``int`` subclass
    in Python, and anything else that is not an ``int`` (a string, a float
    such as ``75.5``) is rejected too: the single canonical check both
    :func:`normalize_width` and the Qt spin box value are expected to pass.
    """

    return (
        isinstance(width, int)
        and not isinstance(width, bool)
        and MIN_WIDTH <= width <= MAX_WIDTH
    )


def normalize_width(width: int | None) -> int:
    """``DEFAULT_WIDTH`` for ``None``, else ``width`` if strictly valid.

    Raises ``ValueError`` otherwise. The single validation barrier every
    other width entry point (the Markdown attribute parser below, the Qt
    dialog, :func:`format_video_block`) funnels through.
    """

    if width is None:
        return DEFAULT_WIDTH
    if not is_valid_width(width):
        raise ValueError(f"Largeur vidéo invalide : {width!r}")
    return width


def parse_width_attribute(raw: str | None) -> int:
    """Parse the Markdown ``data-width`` attribute text (or its absence).

    ``raw`` is the attribute's raw string value, or ``None`` when the
    attribute itself is absent (interpreted as :data:`DEFAULT_WIDTH`).
    Anything other than a bare, unsigned integer string — ``"50%"``,
    ``"75.5"``, ``"abc"``, ``"-1"`` — is rejected, as is one that is
    syntactically a plain integer but out of range (``"0"``, ``"24"``,
    ``"101"``); see :func:`normalize_width` for the shared range check.
    """

    if raw is None:
        return DEFAULT_WIDTH
    if not isinstance(raw, str) or not _WIDTH_ATTR_RE.match(raw):
        raise ValueError(f"Largeur vidéo invalide : {raw!r}")
    return normalize_width(int(raw))


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


# The exact inverse of _escape_caption/_MD_ESCAPE_RE, used only to recover a
# caption's original text for the Qt "edit this video" dialog (see
# parse_video_block). Never used on the way to TEI/HTML: that path keeps
# reading the escaped Markdown caption as-is, exactly as before.
_MD_UNESCAPE_RE = re.compile(r"\\([" + re.escape(string.punctuation) + "])")


def _unescape_caption(text: str) -> str:
    return _MD_UNESCAPE_RE.sub(r"\1", text)


def format_video_block(
    video_id: str,
    caption: str = "",
    *,
    provider: str = "youtube",
    width: int = DEFAULT_WIDTH,
) -> str:
    """Render the reserved Mérope fenced-div Markdown for a validated video.

    Raises ``ValueError`` for an unsupported provider, an invalid id or an
    invalid width — callers (the Qt insertion dialog, tests) are expected
    to have already validated the id via :func:`parse_youtube_url`.

    ``data-width`` is only written when ``width`` differs from
    :data:`DEFAULT_WIDTH`, so the attribute-less form — what every video
    block created before this feature already is — stays the canonical
    representation of the default case and existing documents keep
    round-tripping byte-for-byte.
    """

    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Fournisseur vidéo non pris en charge : {provider!r}")
    if not is_valid_youtube_id(video_id):
        raise ValueError(f"Identifiant vidéo YouTube invalide : {video_id!r}")
    width = normalize_width(width)

    open_line = f':::: {{.{VIDEO_CLASS} data-provider="{provider}" data-video-id="{video_id}"'
    if width != DEFAULT_WIDTH:
        open_line += f' data-width="{width}"'
    open_line += "}"
    normalized_caption = _escape_caption(" ".join(caption.split()))
    if normalized_caption:
        return f"{open_line}\n{normalized_caption}\n{VIDEO_CLOSE}"
    return f"{open_line}\n{VIDEO_CLOSE}"


def parse_video_block(raw_text: str) -> ParsedVideoBlock | None:
    """Parse a whole raw video block back into its components.

    Used by the Qt editor to recognize an existing Mérope video block under
    the cursor and prefill the edit dialog; returns ``None`` (never raises)
    for anything that is not exactly this reserved shape — an unsupported
    provider, an invalid id, an invalid or out-of-range width, more than one
    caption line, or a missing/misplaced closing fence — since that simply
    means "not a video block to offer editing for", not an error to report.
    """

    lines = raw_text.split("\n")
    if len(lines) < 2 or lines[-1] != VIDEO_CLOSE:
        return None
    match = _VIDEO_OPEN_RE.match(lines[0])
    if match is None:
        return None
    provider = match.group("provider")
    video_id = match.group("video_id")
    if provider not in SUPPORTED_PROVIDERS or not is_valid_youtube_id(video_id):
        return None
    try:
        width = parse_width_attribute(match.group("width"))
    except ValueError:
        return None
    caption_lines = lines[1:-1]
    if len(caption_lines) > 1:
        return None
    caption = _unescape_caption(caption_lines[0]) if caption_lines else ""
    return ParsedVideoBlock(provider=provider, video_id=video_id, caption=caption, width=width)
