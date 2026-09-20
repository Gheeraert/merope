"""Encadré: Pandoc characterization + Markdown -> TEI Commons Publishing."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from lxml import etree

from bloggen.tei.commons_publishing import validate_commons_publishing_file
from bloggen.tei.pandoc_converter import ENCADRE_LUA_FILTER, convert_markdown_file_to_tei

pytestmark = pytest.mark.skipif(shutil.which("pandoc") is None, reason="Pandoc requis")

TEI_NS = {"t": "http://www.tei-c.org/ns/1.0"}

BOX_MD = (
    ":::: {.merope-encadre}\n"
    "::: {.merope-encadre-titre}\nÀ *retenir*\n:::\n\n"
    "Premier paragraphe.\n\n"
    "Deuxième paragraphe.\n"
    "::::\n"
)


def _convert(tmp_path: Path, body: str) -> tuple[Path, etree._ElementTree]:
    source = tmp_path / "doc.md"
    source.write_text(f"---\ntitle: Essai\n---\n\n{body}", encoding="utf-8")
    result = convert_markdown_file_to_tei(source, tmp_path / "doc.xml")
    assert result.success, result.message
    return result.tei_file, etree.parse(str(result.tei_file))


def test_characterization_pandoc_alone_drops_the_fenced_div():
    """Documents why the Lua filter exists: with the exact command used by
    ``pandoc_converter`` minus our filter, the div's class vanishes and a
    heading inside it becomes a section swallowing what follows."""

    source = "::: {.merope-encadre}\n## Titre\n\nUn.\n\nDeux.\n:::\n\nAprès.\n"
    completed = subprocess.run(
        ["pandoc", "--from=markdown+footnotes+pipe_tables", "--to=tei", "--standalone", "-"],
        input=source,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    tei = completed.stdout
    assert "merope-encadre" not in tei
    assert "floatingText" not in tei
    assert "<div" in tei and "<head>Titre</head>" in tei
    # "Après." is swallowed by the section opened by the inner heading.
    assert tei.index("Après.") > tei.index("<head>Titre</head>")


def test_box_becomes_floating_text_body_and_validates(tmp_path):
    path, tree = _convert(tmp_path, BOX_MD)

    floating = tree.xpath("//t:floatingText", namespaces=TEI_NS)
    assert len(floating) == 1
    body = floating[0].xpath("t:body", namespaces=TEI_NS)
    assert len(body) == 1
    section = body[0].xpath("t:div[@type='section1']", namespaces=TEI_NS)
    assert len(section) == 1
    head = section[0].xpath("t:head", namespaces=TEI_NS)[0]
    assert "".join(head.itertext()).strip() == "À retenir"
    assert head.xpath("t:hi[@rendition='simple:italic']", namespaces=TEI_NS)
    paragraphs = ["".join(p.itertext()) for p in section[0].xpath("t:p", namespaces=TEI_NS)]
    assert paragraphs == ["Premier paragraphe.", "Deuxième paragraphe."]

    xml = path.read_text(encoding="utf-8")
    assert 'type="encadre"' not in xml and 'rend="encadre"' not in xml
    assert "<aside" not in xml and "<table" not in xml
    assert "merope-encadre" not in xml

    validation = validate_commons_publishing_file(path)
    assert validation.valid is True, validation.issues


def test_untitled_box_validates(tmp_path):
    path, tree = _convert(tmp_path, ":::: {.merope-encadre}\nSeul.\n::::\n")

    assert tree.xpath("//t:floatingText/t:body/t:div[@type='section1']/t:p", namespaces=TEI_NS)
    assert not tree.xpath("//t:floatingText//t:head", namespaces=TEI_NS)
    validation = validate_commons_publishing_file(path)
    assert validation.valid is True, validation.issues


def test_box_with_list_quote_and_note_validates(tmp_path):
    body = (
        ":::: {.merope-encadre}\n"
        "::: {.merope-encadre-titre}\nTitre\n:::\n\n"
        "Avec une note.[^1]\n\n- a\n- b\n\n> Une citation.\n"
        "::::\n\n[^1]: La note.\n"
    )
    path, tree = _convert(tmp_path, body)

    assert tree.xpath("//t:floatingText//t:list/t:item", namespaces=TEI_NS)
    assert tree.xpath("//t:floatingText//t:quote", namespaces=TEI_NS)
    validation = validate_commons_publishing_file(path)
    assert validation.valid is True, validation.issues


def test_box_does_not_disturb_heading_levels_of_the_document(tmp_path):
    body = (
        "## Section normale\n\n"
        + BOX_MD
        + "\n### Sous-section normale\n\nTexte.\n\n## Autre section\n\nFin.\n"
    )
    path, tree = _convert(tmp_path, body)

    outer = tree.xpath(
        "//t:div[@type][not(ancestor::t:floatingText)][t:head]", namespaces=TEI_NS
    )
    assert [(d.get("type"), "".join(d.xpath("t:head", namespaces=TEI_NS)[0].itertext())) for d in outer] == [
        ("section2", "Section normale"),
        ("section3", "Sous-section normale"),
        ("section2", "Autre section"),
    ]
    inner = tree.xpath("//t:floatingText//t:div", namespaces=TEI_NS)
    assert [d.get("type") for d in inner] == ["section1"]
    validation = validate_commons_publishing_file(path)
    assert validation.valid is True, validation.issues


def test_two_boxes_and_headings_before_and_after(tmp_path):
    body = "# Un\n\n" + BOX_MD + "\n## Deux\n\n" + BOX_MD + "\n### Trois\n\nX.\n"
    path, tree = _convert(tmp_path, body)

    assert len(tree.xpath("//t:floatingText", namespaces=TEI_NS)) == 2
    outer = tree.xpath(
        "//t:div[@type][not(ancestor::t:floatingText)][t:head]", namespaces=TEI_NS
    )
    assert [d.get("type") for d in outer] == ["section1", "section2", "section3"]
    assert validate_commons_publishing_file(path).valid is True


def test_heading_inside_a_hand_written_box_is_refused_not_flattened(tmp_path):
    source = tmp_path / "doc.md"
    source.write_text(":::: {.merope-encadre}\n## Interdit\n\nTexte.\n::::\n", encoding="utf-8")

    result = convert_markdown_file_to_tei(source, tmp_path / "doc.xml")

    assert result.success is False
    assert "Encadré Mérope" in result.message


def test_lua_filter_is_shipped_with_the_package():
    assert ENCADRE_LUA_FILTER.is_file()


def _render(tmp_path: Path, body: str) -> str:
    from bloggen.render.xslt_runner import render_tei_file_to_html_fragment

    path, _tree = _convert(tmp_path, body)
    return render_tei_file_to_html_fragment(path, parameters={"article_slug": "essai"})


def test_html_box_is_an_aside_with_a_class_titled_div_and_no_extra_h1(tmp_path):
    body = "# Titre du document\n\n" + BOX_MD + "\n## Suite\n\nFin.\n"
    html = _render(tmp_path, body)
    document = etree.HTML(html)

    asides = document.xpath("//aside[@class='encadre']")
    assert len(asides) == 1
    aside = asides[0]
    titles = aside.xpath("div[@class='encadre-titre']")
    assert len(titles) == 1
    assert "".join(titles[0].itertext()).strip() == "À retenir"
    assert titles[0].xpath("em")
    assert [ "".join(p.itertext()) for p in aside.xpath("p") ] == [
        "Premier paragraphe.",
        "Deuxième paragraphe.",
    ]
    # Exactly the document's own h1: the encadré title is never a heading.
    assert len(document.xpath("//h1")) == 1
    assert not aside.xpath(".//h1 | .//h2 | .//h3 | .//h4 | .//h5 | .//h6")
    # No technical wrapper for floatingText/body, no inline styling.
    assert not aside.xpath("section")
    assert "style=" not in html


def test_html_box_notes_stay_in_the_endnotes_list(tmp_path):
    body = ":::: {.merope-encadre}\nUne note.[^1]\n::::\n\n[^1]: La note.\n"
    document = etree.HTML(_render(tmp_path, body))

    assert len(document.xpath("//section[@id='endnotes']//li")) == 1


def test_theme_css_styles_the_box_without_inline_styles():
    css = (Path(ENCADRE_LUA_FILTER).parents[1] / "css" / "site.css").read_text(encoding="utf-8")

    assert ".encadre {" in css
    assert "border: 1px solid" in css
    assert "margin-inline: 8%" in css
    assert ".encadre-titre" in css and "text-align: center" in css
    assert "@media (max-width: 600px)" in css
