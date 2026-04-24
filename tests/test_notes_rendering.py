from __future__ import annotations

from bloggen.render.margin_notes import apply_notes_rendering


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


def test_apply_notes_rendering_keeps_endnotes_and_adds_margin_excerpt():
    result = apply_notes_rendering(
        _fragment_with_note(),
        enable_margin_notes=True,
        enable_footnotes=True,
        excerpt_words=4,
        excerpt_chars=30,
        prefer_words=True,
    )

    assert result.footnotes_count == 1
    assert result.margin_notes_count == 1
    assert 'class="endnotes"' in result.html_fragment
    assert 'class="margin-notes"' in result.html_fragment
    assert 'id="margin-note-1"' in result.html_fragment
    assert "Une note assez longue…" in result.html_fragment


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
    assert result.margin_notes_count == 1
    assert 'class="endnotes"' not in result.html_fragment
    assert "Une note assez l…" in result.html_fragment
