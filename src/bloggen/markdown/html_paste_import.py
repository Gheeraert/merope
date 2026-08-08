"""Convert pasted HTML (from Word, Google Docs, browsers...) into the rich
text ``Block``/``InlineRun`` model, for the "paste with formatting" action
in the content editor.

Deliberately constrained, in the same spirit as
:mod:`bloggen.markdown.rich_text_import`: it recognizes a practical subset
of what these tools export (paragraphs, headings, bold/italic/strikethrough,
links, images, flat bullet/numbered lists, blockquotes) and degrades
gracefully — unrecognized markup is unwrapped to its visible text rather
than shown as raw HTML or dropped. This is not a general HTML renderer, and
it never touches the real Markdown -> TEI -> HTML build pipeline.
"""

from __future__ import annotations

import base64
import re
import urllib.request
import uuid
from html.parser import HTMLParser
from pathlib import Path

from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    HEADING,
    LIST_ITEM,
    ORDERED_LIST,
    PARAGRAPH,
    Block,
    InlineRun,
)
from bloggen.markdown.typography import (
    convert_curly_quotes_to_guillemets,
    convert_straight_quotes_stateful,
    fix_double_punctuation_spacing,
)

_BOLD_TAGS = {"b", "strong"}
_ITALIC_TAGS = {"i", "em"}
_STRIKE_TAGS = {"s", "strike", "del"}
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCK_TAGS = _HEADING_TAGS | {"p", "li", "blockquote", "ul", "ol"}
_LIST_TAGS = {"ul", "ol"}
_IMAGE_FETCH_TIMEOUT = 5
_WHITESPACE_RE = re.compile(r"\s+")
_BOLD_WEIGHTS = {"bold", "bolder", "600", "700", "800", "900"}


def html_to_blocks(html: str, *, images_dir: Path | None = None) -> list[Block]:
    """Parse a pasted HTML fragment into a list of ``Block``.

    ``images_dir`` is where any ``data:``/``http(s)://`` images found in the
    fragment are saved (skipped, with an alt-text placeholder, if not
    provided or on download failure).
    """
    builder = _HtmlBlockBuilder(images_dir=images_dir)
    builder.feed(html)
    builder.close()
    blocks = builder.finish()
    _normalize_typography(blocks)
    return blocks


class _Frame:
    __slots__ = ("tag", "runs", "items", "suppressed")

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.runs: list[InlineRun] = []
        self.items: list[Block] = []
        self.suppressed = False  # True once this <li>'s text has already been flushed early


class _HtmlBlockBuilder(HTMLParser):
    def __init__(self, *, images_dir: Path | None) -> None:
        super().__init__(convert_charrefs=True)
        self.images_dir = images_dir
        self.result: list[Block] = []
        self.frame_stack: list[_Frame] = []
        self.inline_stack: list[dict] = []

    # -- inline formatting state --------------------------------------

    def _push_inline(self, *, bold: bool = False, italic: bool = False, strike: bool = False, link_href: str | None = None) -> None:
        self.inline_stack.append({"bold": bold, "italic": italic, "strike": strike, "link_href": link_href})

    def _pop_inline(self) -> None:
        if self.inline_stack:
            self.inline_stack.pop()

    def _current_flags(self) -> dict:
        bold = any(f["bold"] for f in self.inline_stack)
        italic = any(f["italic"] for f in self.inline_stack)
        strike = any(f["strike"] for f in self.inline_stack)
        link_href = None
        for f in reversed(self.inline_stack):
            if f["link_href"]:
                link_href = f["link_href"]
                break
        return {"bold": bold, "italic": italic, "strike": strike, "link_href": link_href}

    # -- block/frame handling -------------------------------------------

    def _current_leaf_frame(self) -> _Frame | None:
        for frame in reversed(self.frame_stack):
            if frame.tag not in _LIST_TAGS:
                return frame
        return None

    def _open_implicit_paragraph_if_needed(self) -> _Frame:
        leaf = self._current_leaf_frame()
        if leaf is not None:
            return leaf
        frame = _Frame("p")
        self.frame_stack.append(frame)
        return frame

    def _open_block(self, tag: str) -> None:
        self.frame_stack.append(_Frame(tag))

    def _nearest_list_frame(self) -> _Frame | None:
        for frame in reversed(self.frame_stack):
            if frame.tag in _LIST_TAGS:
                return frame
        return None

    def _close_block(self, tag: str) -> None:
        if not self.frame_stack or self.frame_stack[-1].tag != tag:
            return
        frame = self.frame_stack.pop()
        parent = self.frame_stack[-1] if self.frame_stack else None

        if tag in _LIST_TAGS:
            block = Block(kind=BULLET_LIST if tag == "ul" else ORDERED_LIST, children=frame.items)
            if parent is not None and parent.tag == "li":
                # A sub-list nested inside a list item: this model only
                # supports one level of list, so its items are spliced in
                # as siblings of the enclosing item, in the nearest
                # ancestor list, rather than dropped or nested. The <li>
                # itself is NOT popped here: it stays open (its own closing
                # tag arrives later) but is flushed early so its own text
                # (e.g. "un" in "<li>un<ul>...</ul></li>") is not lost, and
                # marked "suppressed" so its real closing tag does not add
                # a second, now-empty, item.
                grandparent_list = self._nearest_list_frame()  # searches below the still-open <li>
                target = grandparent_list.items if grandparent_list is not None else None
                if parent.runs and target is not None:
                    target.append(Block(kind=LIST_ITEM, runs=parent.runs))
                if target is not None:
                    target.extend(frame.items)
                else:
                    self.result.append(block)
                parent.runs = []
                parent.suppressed = True
                return
            if parent is not None and parent.tag in _LIST_TAGS:
                parent.items.extend(frame.items)
            else:
                self.result.append(block)
            return

        if tag == "li":
            if frame.suppressed:
                return
            list_frame = self._nearest_list_frame()
            item = Block(kind=LIST_ITEM, runs=frame.runs or [InlineRun(text="")])
            if list_frame is not None:
                list_frame.items.append(item)
            else:
                self.result.append(Block(kind=PARAGRAPH, runs=item.runs))
            return

        if tag in _HEADING_TAGS:
            block = Block(kind=HEADING, level=min(int(tag[1]), 4), runs=frame.runs or [InlineRun(text="")])
        elif tag == "blockquote":
            block = Block(kind=BLOCKQUOTE, runs=frame.runs or [InlineRun(text="")])
        else:  # "p"
            if not frame.runs:
                return
            block = Block(kind=PARAGRAPH, runs=frame.runs)

        if parent is not None and parent.tag in ("li", "blockquote"):
            if parent.runs:
                parent.runs.append(InlineRun(text=" "))
            parent.runs.extend(block.runs)
        elif parent is not None and parent.tag in _LIST_TAGS:
            parent.items.append(Block(kind=LIST_ITEM, runs=block.runs))
        else:
            self.result.append(block)

    def _break_paragraph(self) -> None:
        leaf = self._current_leaf_frame()
        if leaf is not None and leaf.tag == "p" and leaf.runs:
            self._close_block("p")
            self._open_implicit_paragraph_if_needed()

    # -- text ----------------------------------------------------------

    def _emit_text(self, text: str) -> None:
        if not text:
            return
        frame = self._open_implicit_paragraph_if_needed()
        flags = self._current_flags()
        if frame.runs and _same_flags(frame.runs[-1], flags):
            frame.runs[-1].text += text
        else:
            frame.runs.append(
                InlineRun(
                    text=text,
                    bold=flags["bold"],
                    italic=flags["italic"],
                    strikethrough=flags["strike"],
                    link_href=flags["link_href"],
                )
            )

    def _emit_image(self, src: str, alt: str) -> None:
        frame = self._open_implicit_paragraph_if_needed()
        frame.runs.append(InlineRun(image_src=src, image_alt=alt))

    # -- HTMLParser hooks -------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._handle_start(tag, attrs, self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._handle_start(tag, attrs, self_closing=True)

    def _handle_start(self, tag: str, attrs: list[tuple[str, str | None]], *, self_closing: bool) -> None:
        attrs_dict = {k: (v or "") for k, v in attrs}

        if tag == "img":
            src = attrs_dict.get("src", "")
            alt = attrs_dict.get("alt", "")
            resolved = _resolve_image_src(src, self.images_dir)
            if resolved:
                self._emit_image(resolved, alt)
            elif alt:
                self._emit_text(f"[Image : {alt}]")
            return
        if tag == "br":
            self._break_paragraph()
            return
        if tag in _BLOCK_TAGS:
            self._open_block(tag)
            return
        if tag == "a":
            self._push_inline(link_href=attrs_dict.get("href") or None)
            return
        # Google Docs in particular wraps whole documents in a
        # `<b id="docs-internal-guid-..." style="font-weight:normal">`
        # purely as a container, with an inline style that *cancels* the
        # tag's own bold semantics. Any explicit style property always
        # overrides the tag-implied default, for every formatting-ish tag
        # (not just <span>) — otherwise that wrapper would bold the entire
        # pasted document.
        style = _parse_style(attrs_dict.get("style", ""))
        bold = _style_is_bold(style) if "font-weight" in style else tag in _BOLD_TAGS
        italic = _style_is_italic(style) if "font-style" in style else tag in _ITALIC_TAGS
        strike = _style_is_strike(style) if "text-decoration" in style else tag in _STRIKE_TAGS
        self._push_inline(bold=bold, italic=italic, strike=strike)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("img", "br"):
            return
        if tag in _BLOCK_TAGS:
            self._close_block(tag)
            return
        self._pop_inline()

    def handle_data(self, data: str) -> None:
        collapsed = _WHITESPACE_RE.sub(" ", data)
        if collapsed.strip() == "" and self._current_leaf_frame() is None:
            return
        self._emit_text(collapsed)

    def finish(self) -> list[Block]:
        while self.frame_stack:
            self._close_block(self.frame_stack[-1].tag)
        return self.result


def _same_flags(run: InlineRun, flags: dict) -> bool:
    return (
        run.image_src is None
        and run.footnote_ref is None
        and run.bold == flags["bold"]
        and run.italic == flags["italic"]
        and run.strikethrough == flags["strike"]
        and run.link_href == flags["link_href"]
    )


def _parse_style(style_text: str) -> dict[str, str]:
    style: dict[str, str] = {}
    for declaration in style_text.split(";"):
        if ":" not in declaration:
            continue
        key, _, value = declaration.partition(":")
        style[key.strip().lower()] = value.strip().lower()
    return style


def _style_is_bold(style: dict[str, str]) -> bool:
    return style.get("font-weight", "") in _BOLD_WEIGHTS


def _style_is_italic(style: dict[str, str]) -> bool:
    return style.get("font-style", "") == "italic"


def _style_is_strike(style: dict[str, str]) -> bool:
    return "line-through" in style.get("text-decoration", "")


def _resolve_image_src(src: str, images_dir: Path | None) -> str | None:
    if not src or images_dir is None:
        return None
    if src.startswith("data:"):
        return _save_data_uri_image(src, images_dir)
    if src.startswith("http://") or src.startswith("https://"):
        return _download_image(src, images_dir)
    return None


def _save_data_uri_image(data_uri: str, images_dir: Path) -> str | None:
    match = re.match(r"data:image/([a-zA-Z0-9.+-]+);base64,(.+)", data_uri, re.DOTALL)
    if not match:
        return None
    extension, payload = match.group(1).lower(), match.group(2)
    extension = "jpg" if extension in ("jpeg", "jpg") else extension
    try:
        data = base64.b64decode(payload, validate=False)
    except (ValueError, base64.binascii.Error):
        return None
    return _write_image_bytes(data, f"collage-{uuid.uuid4().hex[:8]}.{extension}", images_dir)


def _download_image(url: str, images_dir: Path) -> str | None:
    try:
        with urllib.request.urlopen(url, timeout=_IMAGE_FETCH_TIMEOUT) as response:
            data = response.read()
    except (OSError, ValueError):
        return None
    suffix = Path(url.split("?", 1)[0]).suffix.lstrip(".") or "jpg"
    return _write_image_bytes(data, f"collage-{uuid.uuid4().hex[:8]}.{suffix}", images_dir)


def _write_image_bytes(data: bytes, filename: str, images_dir: Path) -> str:
    images_dir.mkdir(parents=True, exist_ok=True)
    destination = images_dir / filename
    destination.write_bytes(data)
    try:
        return destination.relative_to(images_dir.parent).as_posix()
    except ValueError:
        return destination.as_posix()


def _normalize_typography(blocks: list[Block]) -> None:
    """Apply French typography rules to pasted plain text, in document
    order, sharing one quote-parity counter across the whole paste (a
    quote pair can span more than one run, e.g. around a bolded word).
    """
    opening_next = True
    for block in blocks:
        opening_next = _normalize_block(block, opening_next)


def _normalize_block(block: Block, opening_next: bool) -> bool:
    for run in block.runs:
        if run.image_src is not None or run.footnote_ref is not None:
            continue
        text = convert_curly_quotes_to_guillemets(run.text)
        text, opening_next = convert_straight_quotes_stateful(text, opening_next=opening_next)
        run.text = fix_double_punctuation_spacing(text)
    for child in block.children:
        opening_next = _normalize_block(child, opening_next)
    return opening_next
