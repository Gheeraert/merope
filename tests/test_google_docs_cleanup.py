from bloggen.markdown.google_docs_cleanup import cleanup_google_docs_markdown
from bloggen.markdown.typography import NBSP


def test_strips_junk_nbsp_between_words():
    assert cleanup_google_docs_markdown(f"Bonjour{NBSP}le monde") == "Bonjour le monde"


def test_strips_bom():
    assert cleanup_google_docs_markdown("﻿Texte") == "Texte"


def test_preserves_nbsp_before_double_punctuation():
    for char in ";:!?":
        text = f"Mot{NBSP}{char}"
        assert cleanup_google_docs_markdown(text) == text


def test_preserves_nbsp_around_guillemets():
    text = f"«{NBSP}citation{NBSP}»"
    assert cleanup_google_docs_markdown(text) == text


def test_preserves_typography_but_strips_junk_in_same_text():
    text = f"Il a dit «{NBSP}bonjour{NBSP}»{NBSP}! Puis il{NBSP}est parti."
    result = cleanup_google_docs_markdown(text)
    assert result == f"Il a dit «{NBSP}bonjour{NBSP}»{NBSP}! Puis il est parti."
