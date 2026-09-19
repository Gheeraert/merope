"""Live-typing French typography in the Tkinter content editor
(``TypographyMixin`` / ``ContentEditorWindow.text``).

Drives the real ``tk.Text`` widget used in production, invoking
``_on_key_release`` directly with a duck-typed event (real synthetic
``<KeyRelease>`` events are unreliable to deliver headless — see
tests/test_qt_editor_typography.py for the Qt-side equivalent, which uses
real Qt key events instead).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bloggen.markdown.typography import NBSP
from bloggen.ui.content_editor import ContentEditorWindow


@pytest.fixture(scope="module")
def root(tk_root):
    return tk_root


@pytest.fixture
def editor(root, tmp_path):
    pages_dir = tmp_path / "content" / "pages"
    posts_dir = tmp_path / "content" / "posts"
    images_dir = tmp_path / "assets" / "images"
    pages_dir.mkdir(parents=True)
    posts_dir.mkdir(parents=True)

    window = ContentEditorWindow(
        root, pages_dir=pages_dir, posts_dir=posts_dir, images_dir=images_dir, slugify_mode="ascii"
    )
    yield window
    window.destroy()


def _type(editor: ContentEditorWindow, text: str) -> None:
    for char in text:
        editor.text.insert("insert", char)
        editor._on_key_release(SimpleNamespace(char=char))


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("Voir p. 12", f"Voir p.{NBSP}12"),
        ("Voir pp. 123", f"Voir pp.{NBSP}123"),
        ("Confessions, p.30", f"Confessions, p.{NBSP}30"),
        ("Confessions p.30", f"Confessions p.{NBSP}30"),
        ("Voir pp.12-15", f"Voir pp.{NBSP}12-15"),
    ],
)
def test_page_number_gets_nbsp_whether_or_not_a_space_was_typed(editor, typed, expected):
    _type(editor, typed)

    assert editor.text.get("1.0", "end-1c") == expected


@pytest.mark.parametrize("word", ["coup.", "stop.", "champ.", "app."])
def test_word_ending_in_p_period_is_not_touched(editor, word):
    _type(editor, word)

    assert editor.text.get("1.0", "end-1c") == word


@pytest.mark.parametrize("word", ["coup.30", "stop.30", "champ.30", "app.30"])
def test_word_ending_in_p_period_glued_to_a_number_is_not_touched(editor, word):
    _type(editor, word)

    assert editor.text.get("1.0", "end-1c") == word


def test_typing_a_space_right_after_the_auto_inserted_nbsp_does_not_double_the_gap(editor):
    _type(editor, "Voir p. 12")

    assert editor.text.get("1.0", "end-1c") == f"Voir p.{NBSP}12"
