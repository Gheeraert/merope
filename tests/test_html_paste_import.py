from pathlib import Path

from bloggen.markdown.html_paste_import import html_to_blocks
from bloggen.markdown.note_shortcuts import convert_double_paren_notes_in_blocks
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.typography import CLOSING_GUILLEMET, NBSP, OPENING_GUILLEMET

_TINY_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _export(html: str, **kwargs) -> str:
    return blocks_to_markdown(html_to_blocks(html, **kwargs))


def test_plain_paragraph():
    assert _export("<p>Un simple paragraphe.</p>") == "Un simple paragraphe.\n"


def test_bold_and_italic_tags():
    assert _export("<p>Un <b>gras</b> et <i>italique</i>.</p>") == "Un **gras** et *italique*.\n"
    assert _export("<p>Un <strong>gras</strong> et <em>italique</em>.</p>") == "Un **gras** et *italique*.\n"


def test_strikethrough_tags():
    assert _export("<p>Du <s>barre</s> texte.</p>") == "Du ~~barre~~ texte.\n"
    assert _export("<p>Du <del>barre</del> texte.</p>") == "Du ~~barre~~ texte.\n"


def test_superscript_tag():
    assert _export("<p>Un <sup>exposant</sup> ici.</p>") == "Un ^exposant^ ici.\n"


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

    def register(text: str) -> str:
        note_id = str(len(definitions) + 1)
        definitions[note_id] = text
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
    result = _export(html, images_dir=images_dir)
    assert result.startswith("![Une image](images/collage-")
    saved = list(images_dir.glob("*.png"))
    assert len(saved) == 1
    assert saved[0].read_bytes()  # non-empty


def test_http_image_is_downloaded_and_saved(tmp_path: Path, monkeypatch):
    import io
    from bloggen.markdown import html_paste_import as module

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

    def fake_urlopen(url, timeout=None):
        assert url == "https://example.org/photo.jpg"
        return _FakeResponse(b"fake-image-bytes")

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    images_dir = tmp_path / "assets" / "images"
    html = '<p><img src="https://example.org/photo.jpg" alt="Distante"></p>'
    result = _export(html, images_dir=images_dir)

    assert result.startswith("![Distante](images/collage-")
    saved = list(images_dir.glob("*.jpg"))
    assert len(saved) == 1
    assert saved[0].read_bytes() == b"fake-image-bytes"


def test_http_image_download_failure_falls_back_to_alt_text(tmp_path: Path, monkeypatch):
    from bloggen.markdown import html_paste_import as module

    def fake_urlopen(url, timeout=None):
        raise OSError("network unavailable")

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    images_dir = tmp_path / "assets" / "images"
    html = '<p><img src="https://example.org/photo.jpg" alt="Distante"></p>'
    assert _export(html, images_dir=images_dir) == f"\\[Image{NBSP}: Distante\\]\n"


def test_image_without_images_dir_falls_back_to_alt_text():
    # brackets are escaped by the exporter (avoids accidental Markdown link/
    # image syntax) and the colon gets the usual French-typography NBSP.
    html = '<p><img src="data:image/png;base64,abc" alt="Une image"></p>'
    assert _export(html) == f"\\[Image{NBSP}: Une image\\]\n"


def test_image_with_no_alt_and_unresolvable_src_is_dropped():
    assert _export('<p>Texte <img src="cid:something"> ici.</p>') == "Texte  ici.\n"
