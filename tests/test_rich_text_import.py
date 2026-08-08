from pathlib import Path

from bloggen.markdown.front_matter import parse_front_matter
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import (
    BLOCKQUOTE,
    BULLET_LIST,
    FOOTNOTE_DEFINITION,
    HEADING,
    ORDERED_LIST,
    PARAGRAPH,
    TABLE,
    VERBATIM,
)

EXAMPLES_ROOT = Path(__file__).resolve().parent.parent / "examples" / "minimal_project" / "content"


def _roundtrip(markdown_body: str) -> str:
    return blocks_to_markdown(markdown_to_blocks(markdown_body))


def test_heading_roundtrip():
    assert _roundtrip("## Un titre\n").strip() == "## Un titre"


def test_paragraph_with_inline_formatting_roundtrip():
    body = "Un **gras**, *italique*, ***les deux***, ~~barre~~ et [un lien](https://example.org).\n"
    assert _roundtrip(body).strip() == body.strip()


def test_footnote_reference_and_definition_roundtrip():
    body = "Une phrase avec une note[^1].\n\n[^1]: Le texte de la note.\n"
    assert _roundtrip(body).strip() == body.strip()


def test_bullet_and_ordered_list_roundtrip():
    bullet = "- un\n- **deux**\n- trois\n"
    ordered = "1. premier\n2. deuxieme\n"
    assert _roundtrip(bullet).strip() == bullet.strip()
    assert _roundtrip(ordered).strip() == ordered.strip()


def test_blockquote_roundtrip():
    body = "> Une citation.\n"
    assert _roundtrip(body).strip() == body.strip()


def test_table_roundtrip():
    body = "| Élément | Valeur |\n| --- | --- |\n| A | 1 |\n| B | 2 |\n"
    assert _roundtrip(body).strip() == body.strip()


def test_image_roundtrip():
    body = "![Une image](assets/images/x.jpg)\n"
    assert _roundtrip(body).strip() == body.strip()


def test_image_with_attributes_roundtrip():
    body = "![Une image](assets/images/x.jpg){width=300 height=200 align=left}\n"
    blocks = markdown_to_blocks(body)
    run = blocks[0].runs[0]
    assert run.image_width == "300"
    assert run.image_height == "200"
    assert run.image_align == "left"
    assert _roundtrip(body).strip() == body.strip()


def test_unsupported_html_falls_back_to_verbatim_and_is_preserved():
    body = '<div class="weird">contenu <b>html</b> non supporte</div>'
    blocks = markdown_to_blocks(body)
    assert len(blocks) == 1
    assert blocks[0].kind == VERBATIM
    assert blocks[0].raw_text == body
    assert blocks_to_markdown(blocks).strip() == body


def test_block_kinds_are_classified_correctly():
    body = (
        "# Titre\n\n"
        "Un paragraphe.\n\n"
        "> Une citation.\n\n"
        "- un\n- deux\n\n"
        "1. un\n2. deux\n\n"
        "| A | B |\n| --- | --- |\n| 1 | 2 |\n\n"
        "[^1]: Une note.\n"
    )
    blocks = markdown_to_blocks(body)
    kinds = [b.kind for b in blocks]
    assert kinds == [
        HEADING,
        PARAGRAPH,
        BLOCKQUOTE,
        BULLET_LIST,
        ORDERED_LIST,
        TABLE,
        FOOTNOTE_DEFINITION,
    ]


def test_roundtrip_on_real_example_content_files():
    paths = sorted(EXAMPLES_ROOT.rglob("*.md"))
    assert paths, "les fichiers d'exemple sont introuvables, le test ne couvre rien"

    for path in paths:
        text = path.read_text(encoding="utf-8")
        result = parse_front_matter(text)
        assert result.has_front_matter, f"{path} devrait avoir un front matter"

        first_pass = blocks_to_markdown(markdown_to_blocks(result.body))
        second_pass = blocks_to_markdown(markdown_to_blocks(first_pass))
        assert first_pass == second_pass, f"{path} n'est pas stable au second aller-retour"
