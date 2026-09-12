import base64
from pathlib import Path

import pytest

from bloggen.markdown.html_paste_import import (
    UnsupportedHtmlStructureError,
    html_to_blocks,
)
from bloggen.markdown.note_shortcuts import convert_double_paren_notes_in_blocks
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_model import PARAGRAPH, Block
from bloggen.markdown.typography import CLOSING_GUILLEMET, NBSP, OPENING_GUILLEMET

_TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _export(html: str, **kwargs) -> str:
    return blocks_to_markdown(html_to_blocks(html, **kwargs))


def test_plain_paragraph():
    assert _export("<p>Un simple paragraphe.</p>") == "Un simple paragraphe.\n"


def test_strict_caller_can_reject_an_image_without_changing_default_behaviour():
    html = '<p>Avant<img src="cid:image">Après</p>'

    with pytest.raises(UnsupportedHtmlStructureError, match="<img>"):
        html_to_blocks(html, reject_tags={"img"})

    assert _export(html) == "AvantAprès\n"


def test_bold_and_italic_tags():
    assert _export("<p>Un <b>gras</b> et <i>italique</i>.</p>") == "Un **gras** et *italique*.\n"
    assert _export("<p>Un <strong>gras</strong> et <em>italique</em>.</p>") == "Un **gras** et *italique*.\n"


def test_strikethrough_tags():
    assert _export("<p>Du <s>barre</s> texte.</p>") == "Du ~~barre~~ texte.\n"
    assert _export("<p>Du <del>barre</del> texte.</p>") == "Du ~~barre~~ texte.\n"


def test_superscript_tag():
    assert _export("<p>Un <sup>exposant</sup> ici.</p>") == "Un ^exposant^ ici.\n"


def test_underline_tag_and_style_are_canonical():
    assert _export("<p><u>souligne</u></p>") == "[souligne]{.underline}\n"
    assert _export(
        '<p><span style="text-decoration: underline line-through">mixte</span></p>'
    ) == "[~~mixte~~]{.underline}\n"


def test_superscript_via_vertical_align_style_google_docs():
    html = '<p>texte<span style="vertical-align:super;font-size:xx-small">2</span> exposant.</p>'
    assert _export(html) == "texte^2^ exposant.\n"


def test_century_ordinal_auto_conversion_on_paste():
    assert _export("<p>Le XXIe siecle.</p>") == "Le XXI^e^ siecle.\n"
    assert _export("<p>Le Ier siecle.</p>") == "Le I^er^ siecle.\n"


def test_page_number_gets_non_breaking_space_on_paste():
    assert _export("<p>Voir p. 12.</p>") == f"Voir p.{NBSP}12.\n"
    assert _export("<p>Cf. pp. 12-15.</p>") == f"Cf. pp.{NBSP}12-15.\n"


def _export_with_notes(html: str) -> tuple[str, dict[str, str]]:
    """Mirrors exactly what the editor's paste handler
    (ContentEditorWindow._on_paste) does with rich HTML: parse, then
    convert any "((note))" shorthand, then export.
    """
    blocks = html_to_blocks(html)
    definitions: dict[str, str] = {}

    def register(runs) -> str:
        note_id = str(len(definitions) + 1)
        definitions[note_id] = "".join(run.text for run in runs)
        return note_id

    convert_double_paren_notes_in_blocks(blocks, register)
    return blocks_to_markdown(blocks), definitions


def test_double_paren_note_converts_on_paste():
    markdown, definitions = _export_with_notes(
        "<p>Un texte avec une note ((ceci est la note)) et la suite.</p>"
    )
    assert markdown == "Un texte avec une note [^1] et la suite.\n"
    assert definitions == {"1": "ceci est la note"}


def test_double_paren_note_glued_to_punctuation_converts_on_paste():
    # Regression: this is the exact case reported broken — a note placed
    # right before the sentence's closing period, pasted from a rich-text
    # source (Word/Google Docs), used to be silently left as literal text.
    markdown, definitions = _export_with_notes(
        "<p>Il a dit quelque chose ((une note explicative)). Suite du texte.</p>"
    )
    assert markdown == "Il a dit quelque chose [^1]. Suite du texte.\n"
    assert definitions == {"1": "une note explicative"}


def test_double_paren_note_containing_a_link_converts_on_paste():
    # Regression: a note containing a link (or any inline formatting) got
    # parsed as three separate runs (plain / link / plain), so "((" and
    # "))" never landed in the same run and the note was left untouched.
    markdown, definitions = _export_with_notes(
        '<p>Un texte avec une note ((voir <a href="https://example.org">ce lien</a> '
        "pour plus de details)) et la suite.</p>"
    )
    assert markdown == "Un texte avec une note [^1] et la suite.\n"
    assert definitions == {"1": "voir ce lien pour plus de details"}


def test_pre_existing_guillemets_keep_chevrons_but_get_nbsp_on_paste():
    html = f"<p>Il a dit {OPENING_GUILLEMET} bonjour {CLOSING_GUILLEMET} hier.</p>"
    result = _export(html)
    assert result == f"Il a dit {OPENING_GUILLEMET}{NBSP}bonjour{NBSP}{CLOSING_GUILLEMET} hier.\n"
    assert result.count(OPENING_GUILLEMET) == 1
    assert result.count(CLOSING_GUILLEMET) == 1


def test_pre_existing_guillemets_with_nbsp_already_are_unchanged_on_paste():
    html = f"<p>Il a dit {OPENING_GUILLEMET}{NBSP}bonjour{NBSP}{CLOSING_GUILLEMET} hier.</p>"
    assert _export(html) == f"Il a dit {OPENING_GUILLEMET}{NBSP}bonjour{NBSP}{CLOSING_GUILLEMET} hier.\n"


def test_link():
    assert _export('<p>Voir <a href="https://example.org">ce lien</a>.</p>') == (
        "Voir [ce lien](https://example.org).\n"
    )


def test_headings():
    assert _export("<h1>Titre</h1>") == "# Titre\n"
    assert _export("<h3>Sous-titre</h3>") == "### Sous-titre\n"
    # our model clamps to level 4 even for h5/h6
    assert _export("<h6>Tout petit titre</h6>") == "#### Tout petit titre\n"


def test_bullet_and_ordered_lists():
    assert _export("<ul><li>un</li><li>deux</li></ul>") == "- un\n- deux\n"
    assert _export("<ol><li>un</li><li>deux</li></ol>") == "1. un\n2. deux\n"


def test_list_items_wrapping_a_paragraph_google_docs_style():
    html = "<ul><li><p>Premier</p></li><li><p>Deuxieme</p></li></ul>"
    assert _export(html) == "- Premier\n- Deuxieme\n"


def test_nested_sublist_is_flattened_to_one_level():
    html = "<ul><li>un<ul><li>un-a</li><li>un-b</li></ul></li><li>deux</li></ul>"
    blocks = html_to_blocks(html)
    assert len(blocks) == 1
    assert blocks[0].kind == "bullet_list"
    assert len(blocks[0].children) == 4  # flattened: un, un-a, un-b, deux


def test_blockquote_merges_nested_paragraph():
    assert _export("<blockquote><p>Une citation.</p></blockquote>") == "> Une citation.\n"


def test_google_docs_wrapper_bold_override_does_not_bold_everything():
    # Google Docs wraps whole documents in <b style="font-weight:normal">,
    # which must NOT bold the entire pasted content.
    html = (
        '<b style="font-weight:normal" id="docs-internal-guid-x">'
        '<p><span style="font-weight:700">Titre en gras</span> et texte normal.</p>'
        "</b>"
    )
    assert _export(html) == "**Titre en gras** et texte normal.\n"


def test_word_mso_styles_and_comments_are_ignored_not_shown():
    html = (
        "<!--[if gte mso 9]><xml></xml><![endif]-->"
        "<p class=MsoNormal style='mso-margin-top-alt:auto'><b>Titre</b><o:p></o:p></p>"
        "<p>Texte <span style='mso-fareast-font-family:Calibri'>normal</span>.<o:p></o:p></p>"
    )
    result = _export(html)
    assert "mso" not in result
    assert "xml" not in result
    assert result == "**Titre**\n\nTexte normal.\n"


def test_unrecognized_tag_keeps_visible_text():
    assert _export("<customtag>Contenu conservé</customtag> normal.") == "Contenu conservé normal.\n"


def test_span_with_bold_style_google_docs():
    assert _export('<p><span style="font-weight:700">Gras</span> normal.</p>') == "**Gras** normal.\n"


def test_typography_curly_quotes_converted():
    html = "<p>Il a dit “bonjour” hier!</p>"
    result = _export(html)
    assert result == f"Il a dit {OPENING_GUILLEMET}{NBSP}bonjour{NBSP}{CLOSING_GUILLEMET} hier{NBSP}!\n"


def test_typography_straight_quote_parity_spans_bold_run():
    html = '<p>Un "debut <b>en gras</b> et fin" aussi.</p>'
    result = _export(html)
    assert result == f"Un {OPENING_GUILLEMET}{NBSP}debut **en gras** et fin{NBSP}{CLOSING_GUILLEMET} aussi.\n"


def test_data_uri_image_is_decoded_and_saved(tmp_path: Path):
    images_dir = tmp_path / "assets" / "images"
    html = f'<p><img src="data:image/png;base64,{_TINY_PNG_BASE64}" alt="Une image"></p>'
    result = _export(html, images_dir=images_dir, doc_dir=images_dir)
    assert result.startswith("![Une image](collage-")
    saved = list(images_dir.glob("*.png"))
    assert len(saved) == 1
    assert saved[0].read_bytes()  # non-empty


def test_data_uri_image_src_is_relative_to_doc_dir_not_images_dir(tmp_path: Path):
    """The Markdown src must be relative to the post's own directory (what
    the Pandoc/TEI/site-build pipeline resolves it against), not to
    images_dir's parent — the same bug class fixed in image_widget.py's
    copy_into_images_dir/save_clipboard_image.
    """
    images_dir = tmp_path / "assets" / "images"
    doc_dir = tmp_path / "content" / "posts"
    doc_dir.mkdir(parents=True)
    html = f'<p><img src="data:image/png;base64,{_TINY_PNG_BASE64}" alt="Une image"></p>'
    result = _export(html, images_dir=images_dir, doc_dir=doc_dir)
    assert result.startswith("![Une image](../../assets/images/collage-")


class _FakeHeaders:
    def __init__(self, content_type: str) -> None:
        self._content_type = content_type

    def get_content_type(self) -> str:
        return self._content_type


class _FakeResponse:
    def __init__(self, data: bytes, content_type: str = "image/jpeg") -> None:
        self._data = data
        self.headers = _FakeHeaders(content_type)

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            return self._data
        return self._data[:size]

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeOpener:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.opened_url: str | None = None

    def open(self, url, timeout=None):
        self.opened_url = url
        if self._error is not None:
            raise self._error
        return self._response


_FAKE_JPEG_BYTES = b"\xff\xd8\xfffake-image-bytes"


def test_http_image_is_downloaded_and_saved(tmp_path: Path, monkeypatch):
    from bloggen.markdown import html_paste_import as module

    opener = _FakeOpener(response=_FakeResponse(_FAKE_JPEG_BYTES, "image/jpeg"))
    monkeypatch.setattr(module, "_build_image_opener", lambda: opener)

    images_dir = tmp_path / "assets" / "images"
    html = '<p><img src="https://example.org/photo.jpg" alt="Distante"></p>'
    result = _export(html, images_dir=images_dir, doc_dir=images_dir)

    assert opener.opened_url == "https://example.org/photo.jpg"
    assert result.startswith("![Distante](collage-")
    saved = list(images_dir.glob("*.jpg"))
    assert len(saved) == 1
    assert saved[0].read_bytes() == _FAKE_JPEG_BYTES


def test_http_image_download_failure_falls_back_to_alt_text(tmp_path: Path, monkeypatch):
    from bloggen.markdown import html_paste_import as module

    monkeypatch.setattr(
        module, "_build_image_opener", lambda: _FakeOpener(error=OSError("network unavailable"))
    )

    images_dir = tmp_path / "assets" / "images"
    html = '<p><img src="https://example.org/photo.jpg" alt="Distante"></p>'
    assert _export(html, images_dir=images_dir) == f"\\[Image{NBSP}: Distante\\]\n"


def test_http_image_over_the_size_cap_falls_back_to_alt_text(tmp_path: Path, monkeypatch):
    from bloggen.markdown import html_paste_import as module

    oversized = b"x" * (module._MAX_IMAGE_BYTES + 1)
    opener = _FakeOpener(response=_FakeResponse(oversized, "image/jpeg"))
    monkeypatch.setattr(module, "_build_image_opener", lambda: opener)

    images_dir = tmp_path / "assets" / "images"
    html = '<p><img src="https://example.org/huge.jpg" alt="Enorme"></p>'
    assert _export(html, images_dir=images_dir) == f"\\[Image{NBSP}: Enorme\\]\n"
    assert list(images_dir.glob("*")) == []


def test_http_image_with_a_non_image_content_type_falls_back_to_alt_text(tmp_path: Path, monkeypatch):
    from bloggen.markdown import html_paste_import as module

    opener = _FakeOpener(response=_FakeResponse(b"<html>not an image</html>", "text/html"))
    monkeypatch.setattr(module, "_build_image_opener", lambda: opener)

    images_dir = tmp_path / "assets" / "images"
    html = '<p><img src="https://example.org/page.jpg" alt="FauxFormat"></p>'
    assert _export(html, images_dir=images_dir) == f"\\[Image{NBSP}: FauxFormat\\]\n"
    assert list(images_dir.glob("*")) == []


def test_http_image_pointing_at_a_local_address_is_never_fetched(tmp_path: Path, monkeypatch):
    """A pasted <img src> targeting a loopback/private/link-local address
    (e.g. a cloud metadata endpoint, or a local admin page) must be
    rejected before any connection is attempted — the classic SSRF
    surface a same-request hostname check exists to close."""
    from bloggen.markdown import html_paste_import as module

    opener = _FakeOpener(response=_FakeResponse(b"secret-local-content", "image/jpeg"))
    monkeypatch.setattr(module, "_build_image_opener", lambda: opener)

    images_dir = tmp_path / "assets" / "images"
    for url in (
        "http://127.0.0.1/img.jpg",
        "http://localhost/img.jpg",
        "http://169.254.169.254/latest/meta-data/img.jpg",
        "http://[::1]/img.jpg",
    ):
        html = f'<p><img src="{url}" alt="Locale"></p>'
        assert _export(html, images_dir=images_dir) == f"\\[Image{NBSP}: Locale\\]\n"

    assert opener.opened_url is None  # never even attempted a connection
    assert list(images_dir.glob("*")) == []


def test_no_redirect_handler_refuses_every_redirect():
    from bloggen.markdown.html_paste_import import _NoRedirectHandler

    handler = _NoRedirectHandler()
    assert (
        handler.redirect_request(
            req=object(),
            fp=None,
            code=302,
            msg="Found",
            headers={},
            newurl="http://169.254.169.254/img.jpg",
        )
        is None
    )


def test_http_image_content_not_matching_its_declared_content_type_is_rejected(
    tmp_path: Path, monkeypatch
):
    """A server claiming "image/png" while actually serving something
    else entirely (HTML, a script) must not be trusted on the header
    alone — the file's own magic bytes are checked too."""
    from bloggen.markdown import html_paste_import as module

    opener = _FakeOpener(
        response=_FakeResponse(b"<html><script>alert(1)</script></html>", "image/png")
    )
    monkeypatch.setattr(module, "_build_image_opener", lambda: opener)

    images_dir = tmp_path / "assets" / "images"
    html = '<p><img src="https://example.org/fake.png" alt="Faux"></p>'
    assert _export(html, images_dir=images_dir) == f"\\[Image{NBSP}: Faux\\]\n"
    assert list(images_dir.glob("*")) == []


def test_http_svg_is_rejected_outright(tmp_path: Path, monkeypatch):
    """SVG is active content (can embed <script>, on* handlers) — never
    accepted as a plain downloaded image, regardless of what magic bytes
    it has."""
    from bloggen.markdown import html_paste_import as module

    opener = _FakeOpener(
        response=_FakeResponse(b"<svg onload=alert(1)></svg>", "image/svg+xml")
    )
    monkeypatch.setattr(module, "_build_image_opener", lambda: opener)

    images_dir = tmp_path / "assets" / "images"
    html = '<p><img src="https://example.org/logo.svg" alt="Logo"></p>'
    assert _export(html, images_dir=images_dir) == f"\\[Image{NBSP}: Logo\\]\n"
    assert list(images_dir.glob("*")) == []


def test_data_uri_svg_is_rejected_outright(tmp_path: Path):
    images_dir = tmp_path / "assets" / "images"
    payload = base64.b64encode(b"<svg onload=alert(1)></svg>").decode()
    html = f'<p><img src="data:image/svg+xml;base64,{payload}" alt="Logo"></p>'
    assert _export(html, images_dir=images_dir) == f"\\[Image{NBSP}: Logo\\]\n"
    assert list(images_dir.glob("*")) == []


def test_data_uri_content_not_matching_its_declared_subtype_is_rejected(tmp_path: Path):
    """The subtype claimed in a data: URI is exactly as untrustworthy as
    an HTTP Content-Type header — checked against the file's own magic
    bytes the same way."""
    images_dir = tmp_path / "assets" / "images"
    payload = base64.b64encode(b"<html><script>alert(1)</script></html>").decode()
    html = f'<p><img src="data:image/png;base64,{payload}" alt="Faux"></p>'
    assert _export(html, images_dir=images_dir) == f"\\[Image{NBSP}: Faux\\]\n"
    assert list(images_dir.glob("*")) == []


def test_data_uri_over_the_size_cap_is_rejected(tmp_path: Path):
    """Unlike an http(s) download, a data: URI has no separate
    "read up to N+1 bytes" step — the whole payload arrives as one
    string. It must still be bounded, both before and after decoding."""
    from bloggen.markdown import html_paste_import as module

    images_dir = tmp_path / "assets" / "images"
    oversized = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * module._MAX_IMAGE_BYTES).decode()
    html = f'<p><img src="data:image/png;base64,{oversized}" alt="Enorme"></p>'
    assert _export(html, images_dir=images_dir) == f"\\[Image{NBSP}: Enorme\\]\n"
    assert list(images_dir.glob("*")) == []


def test_image_without_images_dir_falls_back_to_alt_text():
    # brackets are escaped by the exporter (avoids accidental Markdown link/
    # image syntax) and the colon gets the usual French-typography NBSP.
    html = '<p><img src="data:image/png;base64,abc" alt="Une image"></p>'
    assert _export(html) == f"\\[Image{NBSP}: Une image\\]\n"


def test_image_with_no_alt_and_unresolvable_src_is_dropped():
    assert _export('<p>Texte <img src="cid:something"> ici.</p>') == "Texte  ici.\n"


def test_opt_in_vml_image_resolver_preserves_dimensions_and_deduplicates():
    from bloggen.markdown.rich_text_model import InlineRun

    html = (
        '<p>Avant<img src="same" alt="Image" width="320" height="180">'
        '<v:shape><v:imagedata src="same"></v:imagedata></v:shape>Après</p>'
    )
    blocks = html_to_blocks(
        html,
        image_src_resolver=lambda src: "staged.png" if src == "same" else None,
        strict_images=True,
        allow_vml_images=True,
        preserve_image_dimensions=True,
        deduplicate_images=True,
    )

    assert blocks == [
        Block(
            kind=PARAGRAPH,
            runs=[
                InlineRun(text="Avant"),
                InlineRun(
                    image_src="staged.png",
                    image_alt="Image",
                    image_width="320",
                    image_height="180",
                ),
                InlineRun(text="Après"),
            ],
        )
    ]


def test_non_numeric_html_image_dimensions_are_ignored_in_opt_in_path():
    blocks = html_to_blocks(
        '<p><img src="x" width="50%" height="auto"></p>',
        image_src_resolver=lambda src: "staged.png",
        strict_images=True,
        preserve_image_dimensions=True,
    )
    image = blocks[0].runs[0]
    assert image.image_width is None
    assert image.image_height is None


def test_dimension_and_dedup_options_do_not_change_historical_defaults():
    blocks = html_to_blocks(
        '<p><img src="same" width="320"><img src="same" width="320"></p>',
        image_src_resolver=lambda src: "staged.png",
        strict_images=True,
    )
    assert len(blocks[0].runs) == 2
    assert all(run.image_width is None for run in blocks[0].runs)
