import json

from bloggen.render.search_index import SearchEntry, extract_plain_text, render_search_index


def test_extract_plain_text_strips_tags():
    assert extract_plain_text("<p>Un <strong>gras</strong> et un lien.</p>") == "Un gras et un lien."


def test_extract_plain_text_separates_adjacent_block_elements():
    html = "<ul><li>un</li><li>deux</li></ul>"
    text = extract_plain_text(html)
    assert "undeux" not in text
    assert "un" in text and "deux" in text


def test_extract_plain_text_collapses_whitespace():
    assert extract_plain_text("<p>Un   texte\n\n  avec   des espaces.</p>") == "Un texte avec des espaces."


def test_extract_plain_text_empty_input():
    assert extract_plain_text("") == ""
    assert extract_plain_text("   ") == ""


def test_render_search_index_produces_valid_json_with_expected_fields():
    entries = [
        SearchEntry(title="Titre un", url="/billets/un/index.html", excerpt="Un extrait.", text="Un extrait complet."),
        SearchEntry(title="Titre deux", url="/deux/index.html", excerpt="Autre extrait.", text="Autre texte complet."),
    ]
    payload = json.loads(render_search_index(entries))
    assert payload == [
        {
            "title": "Titre un",
            "url": "/billets/un/index.html",
            "excerpt": "Un extrait.",
            "text": "Un extrait complet.",
        },
        {
            "title": "Titre deux",
            "url": "/deux/index.html",
            "excerpt": "Autre extrait.",
            "text": "Autre texte complet.",
        },
    ]


def test_render_search_index_empty_list():
    assert render_search_index([]) == "[]"
