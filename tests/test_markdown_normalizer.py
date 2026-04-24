from __future__ import annotations

from bloggen.markdown.front_matter import parse_front_matter
from bloggen.markdown.normalizer import normalize_markdown_text


def test_normalize_markdown_simple():
    raw = "Line 1  \r\nLine 2\t\rLine 3"
    normalized = normalize_markdown_text(raw, google_docs_mode=False)
    assert normalized == "Line 1\nLine 2\nLine 3\n"


def test_normalization_preserves_footnote_markdown():
    raw = "Texte[^1].\r\n\r\n[^1]: Une note.\r\n"
    normalized = normalize_markdown_text(raw)
    assert "[^1]" in normalized
    assert "[^1]: Une note." in normalized


def test_extract_simple_front_matter():
    text = (
        "---\n"
        "title: \"Titre\"\n"
        "slug: \"titre\"\n"
        "type: \"post\"\n"
        "date: \"2026-04-24\"\n"
        "---\n"
        "# Contenu\n"
    )
    parsed = parse_front_matter(text)
    assert parsed.has_front_matter is True
    assert parsed.metadata["title"] == "Titre"
    assert parsed.metadata["slug"] == "titre"
    assert parsed.body.startswith("# Contenu")
