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
    """Components of a video block recognized by :func:`parse_video_block`.

    ``caption`` is the best-effort *displayable* text (escaping undone),
    meant only for showing in the Qt edit dialog's text field. ``caption_source``
    is the exact, unmodified Markdown caption line as written in the
    document — the one byte-for-byte source of truth to put back verbatim
    when the dialog's caption field comes back unchanged (see
    bloggen.ui.qt_editor.video_structure.replace_video): a hand-written or
    externally produced caption was never necessarily produced by
    :func:`format_video_block`'s own escaping, so "unescape it" is not a
    safe way to recover what should be written back.
    """

    provider: str
    video_id: str
    caption: str
    caption_source: str
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

# The attributes parse_video_block() is willing to recognize on a Mérope
# video's opening fence — see _parse_video_attrs. Anything else on that
# line (an unknown attribute, a duplicate, or a shape this regex does not
# match at all) makes parse_video_block() refuse the whole block rather
# than editing it and silently dropping what it does not understand.
_KNOWN_VIDEO_ATTRS = frozenset({"data-provider", "data-video-id", "data-width"})

# Pandoc accepts a fenced div's attributes in any order and with varying
# whitespace between them; .merope-video itself must still come first,
# immediately after "{.", matching how format_video_block always writes
# it. Each attribute is `key="value"` with no escaped quote inside value
# (none of ours ever needs one).
_VIDEO_OPEN_ATTRS_RE = re.compile(
    r'^:::: \{\.merope-video(?P<attrs>(?:\s+[A-Za-z0-9_-]+="[^"]*")*)\s*\}$'
)
_VIDEO_ATTR_RE = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')

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


def _parse_video_attrs(line: str) -> dict[str, str] | None:
    """Order-independent ``{key: value}`` of a video opening fence's known
    attributes, or ``None`` if the line is not exactly that reserved shape.

    Deliberately conservative, not a general Pandoc attribute-list parser:
    a duplicate of a known attribute, any attribute this module does not
    know about, or anything else that does not fit
    ``:::: {.merope-video key="value" key="value" ...}`` (in any order,
    with flexible whitespace between attributes) is refused — ``None`` —
    rather than silently dropped. The Lua filter is the independent,
    authoritative barrier at publication time; this is only used to decide
    whether the Qt editor may safely offer to edit the block in place.
    """

    match = _VIDEO_OPEN_ATTRS_RE.match(line)
    if match is None:
        return None
    attrs: dict[str, str] = {}
    for key, value in _VIDEO_ATTR_RE.findall(match.group("attrs")):
        if key not in _KNOWN_VIDEO_ATTRS or key in attrs:
            return None
        attrs[key] = value
    return attrs


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


def _build_video_open_line(video_id: str, provider: str, width: int) -> str:
    """Validate and render the opening-fence line, with its canonical,
    fixed attribute order — the single validation barrier
    :func:`compose_video_block` (and so :func:`format_video_block`) funnels
    through. Raises ``ValueError`` for an unsupported provider, an invalid
    id or an invalid width."""

    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Fournisseur vidéo non pris en charge : {provider!r}")
    if not is_valid_youtube_id(video_id):
        raise ValueError(f"Identifiant vidéo YouTube invalide : {video_id!r}")
    width = normalize_width(width)

    open_line = f':::: {{.{VIDEO_CLASS} data-provider="{provider}" data-video-id="{video_id}"'
    if width != DEFAULT_WIDTH:
        open_line += f' data-width="{width}"'
    return open_line + "}"


def compose_video_block(
    video_id: str,
    *,
    provider: str = "youtube",
    width: int = DEFAULT_WIDTH,
    caption_source: str = "",
) -> str:
    """Render the reserved block with a caption line taken verbatim.

    Unlike :func:`format_video_block`, ``caption_source`` is never escaped
    or otherwise transformed: it is injected as-is between the opening and
    closing fence. Empty means no caption line. This is what lets the Qt
    "edit this video" dialog put back an existing, untouched caption
    byte-for-byte — including one written by hand or by another tool, that
    :func:`format_video_block`'s own escaping never produced in the first
    place — instead of re-deriving it from a lossy "displayable" form.
    Raises ``ValueError`` under the same conditions as
    :func:`format_video_block`.
    """

    open_line = _build_video_open_line(video_id, provider, width)
    if caption_source:
        return f"{open_line}\n{caption_source}\n{VIDEO_CLOSE}"
    return f"{open_line}\n{VIDEO_CLOSE}"


def format_video_block(
    video_id: str,
    caption: str = "",
    *,
    provider: str = "youtube",
    width: int = DEFAULT_WIDTH,
) -> str:
    """Render the reserved Mérope fenced-div Markdown for a validated video.

    ``caption`` is plain text: escaped systematically (see
    :func:`_escape_caption`) before being written as the caption line, and
    whitespace-normalized first. Raises ``ValueError`` for an unsupported
    provider, an invalid id or an invalid width — callers (the Qt
    insertion dialog, tests) are expected to have already validated the id
    via :func:`parse_youtube_url`.

    ``data-width`` is only written when ``width`` differs from
    :data:`DEFAULT_WIDTH`, so the attribute-less form — what every video
    block created before this feature already is — stays the canonical
    representation of the default case and existing documents keep
    round-tripping byte-for-byte.
    """

    normalized_caption = _escape_caption(" ".join(caption.split()))
    return compose_video_block(
        video_id, provider=provider, width=width, caption_source=normalized_caption
    )


def parse_video_block(raw_text: str) -> ParsedVideoBlock | None:
    """Parse a whole raw video block back into its components.

    Used by the Qt editor to recognize an existing Mérope video block under
    the cursor and prefill the edit dialog; returns ``None`` (never raises)
    for anything that is not exactly this reserved shape — an unsupported
    provider, an invalid id, an invalid or out-of-range width, a duplicated
    or unknown attribute (see :func:`_parse_video_attrs`), more than one
    caption line, or a missing/misplaced closing fence — since that simply
    means "not a video block to offer editing for", not an error to report.

    The opening fence's attributes are recognized in any order (Pandoc
    itself does not require a fixed order); :func:`format_video_block` and
    :func:`compose_video_block` keep writing them in the canonical order
    regardless.
    """

    lines = raw_text.split("\n")
    if len(lines) < 2 or lines[-1] != VIDEO_CLOSE:
        return None
    attrs = _parse_video_attrs(lines[0])
    if attrs is None:
        return None
    provider = attrs.get("data-provider")
    video_id = attrs.get("data-video-id")
    if provider is None or video_id is None:
        return None
    if provider not in SUPPORTED_PROVIDERS or not is_valid_youtube_id(video_id):
        return None
    try:
        width = parse_width_attribute(attrs.get("data-width"))
    except ValueError:
        return None
    caption_lines = lines[1:-1]
    if len(caption_lines) > 1:
        return None
    caption_source = caption_lines[0] if caption_lines else ""
    caption = _unescape_caption(caption_source) if caption_source else ""
    return ParsedVideoBlock(
        provider=provider,
        video_id=video_id,
        caption=caption,
        caption_source=caption_source,
        width=width,
    )
