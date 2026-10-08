from __future__ import annotations

from lxml import html as lxml_html

from bloggen.render.lightbox import apply_lightbox_markup
from bloggen.render.margin_notes import apply_notes_rendering


def _fragment_with_video_and_trailing_text() -> str:
    return (
        "<article>"
        '<figure class="video-embed">'
        '<div class="video-embed-frame">'
        '<iframe src="https://www.youtube-nocookie.com/embed/test"></iframe>'
        "</div>"
        "</figure>"
        "<p>Texte après</p>"
        "</article>"
    )


def test_apply_notes_rendering_never_self_closes_iframe():
    result = apply_notes_rendering(
        _fragment_with_video_and_trailing_text(),
        enable_margin_notes=False,
        enable_footnotes=True,
        excerpt_words=4,
        excerpt_chars=30,
        prefer_words=True,
    )

    assert "</iframe>" in result.html_fragment
    assert "/>" not in result.html_fragment

    document = lxml_html.fromstring(f"<div>{result.html_fragment}</div>")
    paragraphs = document.xpath("//p[text()='Texte après']")
    assert len(paragraphs) == 1
    assert paragraphs[0].xpath("ancestor::iframe") == []


def test_lightbox_then_notes_rendering_keep_iframe_explicitly_closed():
    lightbox_result = apply_lightbox_markup(
        _fragment_with_video_and_trailing_text(),
        enabled=True,
        group_name="essai",
        use_caption=False,
    )
    notes_result = apply_notes_rendering(
        lightbox_result.html_fragment,
        enable_margin_notes=False,
        enable_footnotes=True,
        excerpt_words=4,
        excerpt_chars=30,
        prefer_words=True,
    )

    assert "</iframe>" in notes_result.html_fragment
    assert "/>" not in notes_result.html_fragment

    document = lxml_html.fromstring(f"<div>{notes_result.html_fragment}</div>")
    paragraphs = document.xpath("//p[text()='Texte après']")
    assert len(paragraphs) == 1
    assert paragraphs[0].xpath("ancestor::iframe") == []


def _fragment_with_note() -> str:
    return (
        '<article class="tei-fragment">'
        '<p>Texte<sup class="note-call" id="note-call-1"><a href="#note-1">1</a></sup></p>'
        '<section class="endnotes" id="endnotes">'
        '<h2>Notes</h2><ol class="endnotes-list">'
        '<li id="note-1" data-note-number="1">Une note assez longue pour test<a class="note-backref" href="#note-call-1">↩</a></li>'
        '</ol></section>'
        '</article>'
    )


def test_apply_notes_rendering_keeps_endnotes():
    result = apply_notes_rendering(
        _fragment_with_note(),
        enable_margin_notes=True,
        enable_footnotes=True,
        excerpt_words=4,
        excerpt_chars=30,
        prefer_words=True,
    )

    assert result.footnotes_count == 1
    assert 'class="endnotes"' in result.html_fragment
    assert "Une note assez longue pour test" in result.html_fragment


def test_apply_notes_rendering_can_remove_endnotes():
    result = apply_notes_rendering(
        _fragment_with_note(),
        enable_margin_notes=True,
        enable_footnotes=False,
        excerpt_words=0,
        excerpt_chars=16,
        prefer_words=False,
    )

    assert result.footnotes_count == 0
    assert 'class="endnotes"' not in result.html_fragment


def test_margin_notes_are_not_implemented_regardless_of_the_flag():
    # See render/margin_notes.py: margin notes are unconditionally disabled
    # for now, even when the caller asks for enable_margin_notes=True.
    result = apply_notes_rendering(
        _fragment_with_note(),
        enable_margin_notes=True,
        enable_footnotes=True,
        excerpt_words=4,
        excerpt_chars=30,
        prefer_words=True,
    )

    assert result.margin_notes_count == 0
    assert 'class="margin-notes"' not in result.html_fragment
