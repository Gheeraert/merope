"""render_page_document must guarantee exactly one <h1> per page — the
page's own title. Previously the injected title fell back to <h2> unless
the content already had its own <h1> (a top-level TEI div heading), in
which case *that* stayed <h1> instead of the real title — so a page
could end up with zero or two <h1> elements depending on its content
structure, never a reliable single one.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil

import pytest

from bloggen.build.site_builder import build_site
from bloggen.config.defaults import build_default_config
from bloggen.config.models import ProjectConfig
from bloggen.render.html_templates import render_page_document


_CSS_PATH = Path("src/bloggen/resources/css/site.css")
_EDITORIAL_LEVEL_ATTR = "data-content-heading-level"


def _h1_count(html: str) -> int:
    return len(re.findall(r"<h1[\s>]", html, flags=re.IGNORECASE))


def _render(content_html: str) -> str:
    return render_page_document(
        config=ProjectConfig(),
        title="Mon article",
        content_html=content_html,
        current_path="/billets/mon-article/index.html",
        asset_prefix="../..",
        show_title_heading=True,
    )


def test_exactly_one_h1_when_content_has_no_heading_at_all():
    html = _render('<article class="tei-fragment"><p>Texte simple.</p></article>')
    assert _h1_count(html) == 1
    assert '<h1 class="article-title">Mon article</h1>' in html


def test_exactly_one_h1_when_content_already_has_its_own_h1():
    """A top-level TEI div's <head> becomes <h1> in the fragment (see the
    XSLT) — that must never compete with, or replace, the real title."""
    html = _render(
        '<article class="tei-fragment"><section><h1>Titre interne</h1><p>Texte.</p></section></article>'
    )
    assert _h1_count(html) == 1
    assert '<h1 class="article-title">Mon article</h1>' in html
    # The content's own heading survives, demoted rather than dropped.
    assert '<h2 data-content-heading-level="1">Titre interne</h2>' in html


def test_nested_heading_hierarchy_is_preserved_after_the_shift():
    html = _render(
        '<article class="tei-fragment">'
        "<section><h1>Section</h1>"
        "<section><h2>Sous-section</h2>"
        "<section><h3>Sous-sous-section</h3></section>"
        "</section></section>"
        "</article>"
    )
    assert '<h2 data-content-heading-level="1">Section</h2>' in html
    assert '<h3 data-content-heading-level="2">Sous-section</h3>' in html
    assert '<h4 data-content-heading-level="3">Sous-sous-section</h4>' in html
    # Relative order/nesting is unaffected — only the levels shifted.
    assert html.index("Section</h2>") < html.index("Sous-section</h3>") < html.index(
        "Sous-sous-section</h4>"
    )


def test_two_top_level_headings_in_the_content_are_both_demoted():
    """A post whose Markdown source had two top-level (#) headings
    produces two top-level TEI divs, each becoming its own <h1> — both
    must be demoted, not just the first."""
    html = _render(
        '<article class="tei-fragment">'
        "<section><h1>Premier</h1><p>A</p></section>"
        "<section><h1>Second</h1><p>B</p></section>"
        "</article>"
    )
    assert _h1_count(html) == 1
    assert html.count('<h2 data-content-heading-level="1">Premier</h2>') == 1
    assert html.count('<h2 data-content-heading-level="1">Second</h2>') == 1


def test_heading_shift_marks_all_real_html_levels_without_generating_h7():
    html = _render(
        '<article class="tei-fragment">'
        "<h1>Un</h1><h2>Deux</h2><h3>Trois</h3>"
        "<h4>Quatre</h4><h5>Cinq</h5><h6>Six</h6>"
        "</article>"
    )

    expected = (
        (2, 1, "Un"),
        (3, 2, "Deux"),
        (4, 3, "Trois"),
        (5, 4, "Quatre"),
        (6, 5, "Cinq"),
        (6, 6, "Six"),
    )
    for html_level, editorial_level, text in expected:
        assert (
            f'<h{html_level} {_EDITORIAL_LEVEL_ATTR}="{editorial_level}">'
            f"{text}</h{html_level}>"
        ) in html
    assert "<h7" not in html.lower()


def test_heading_shift_preserves_existing_attributes_and_tag_case():
    html = _render(
        '<article class="tei-fragment">'
        '<H2 id="foo" class="bar" data-x="1">Titre</H2>'
        "</article>"
    )

    assert (
        '<h3 id="foo" class="bar" data-x="1" '
        'data-content-heading-level="2">Titre</h3>'
    ) in html


def test_no_heading_shift_when_show_title_heading_is_false():
    """Pages that don't ask for a title heading (e.g. the raw fragment
    reused elsewhere) must not have their content silently rewritten."""
    html = render_page_document(
        config=ProjectConfig(),
        title="Mon article",
        content_html='<article><h1>Titre interne</h1></article>',
        current_path="/billets/mon-article/index.html",
        asset_prefix="../..",
        show_title_heading=False,
    )
    assert "<h1>Titre interne</h1>" in html
    assert "article-title" not in html
    assert _EDITORIAL_LEVEL_ATTR not in html


def _css_rule(css: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>[^}}]*)\}}", css)
    assert match is not None, f"Règle CSS absente : {selector}"
    return match.group("body")


def test_builtin_css_styles_titles_by_editorial_level_not_shifted_tag():
    css = _CSS_PATH.read_text(encoding="utf-8")
    article = _css_rule(css, ".tei-fragment .article-title")
    level_1 = _css_rule(css, '.tei-fragment [data-content-heading-level="1"]')
    level_2 = _css_rule(css, '.tei-fragment [data-content-heading-level="2"]')
    level_3 = _css_rule(css, '.tei-fragment [data-content-heading-level="3"]')
    level_4 = _css_rule(css, '.tei-fragment [data-content-heading-level="4"]')

    assert "font-family: var(--font-body)" in article
    assert "font-weight: 400" in article
    assert "font-variant: small-caps" in article
    assert "font-size: calc(1.37rem + 2pt)" in article
    assert "margin-top: 1.6em" in article
    assert "margin-bottom: 1em" in article

    assert "font-family: var(--font-ui)" in level_1
    assert "font-weight: 900" in level_1
    assert "font-size: clamp(1.6rem, 2.6vw, 2rem)" in level_1

    assert "font-family: var(--font-body)" in level_2
    assert "font-weight: 400" in level_2
    assert "font-variant: small-caps" in level_2
    assert "font-size: calc(1.37rem + 2pt)" in level_2

    assert "font-family: var(--font-ui)" in level_3
    assert "font-weight: 400" in level_3
    assert "font-size: 1.37rem" in level_3
    assert "font-variant: normal" in level_3

    assert "font-family: var(--font-ui)" in level_4
    assert "font-size: 1rem" in level_4
    assert level_4 != level_3

    heading_rules = "\n".join((article, level_1, level_2, level_3, level_4)).lower()
    assert "georgia" not in heading_rules
    assert "times" not in heading_rules
    assert "--font-title" not in css


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="Pandoc non disponible")
def test_real_build_preserves_editorial_levels_h1_through_h4(tmp_path):
    project = tmp_path / "heading-hierarchy"
    pages = project / "content/pages"
    pages.mkdir(parents=True)
    (pages / "niveaux.md").write_text(
        '---\ntitle: "Titre metadata"\nslug: "niveaux"\ntype: "page"\n---\n\n'
        "# Niveau 1\n\n## Niveau 2\n\n### Niveau 3\n\n#### Niveau 4\n",
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/niveaux.md"
    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("{}", encoding="utf-8")

    report = build_site(config, config_path=config_path)

    assert report.success is True
    html = (project / "site/niveaux/index.html").read_text(encoding="utf-8")
    assert _h1_count(html) == 1
    assert '<h1 class="article-title">Titre metadata</h1>' in html
    for html_level, editorial_level, text in (
        (2, 1, "Niveau 1"),
        (3, 2, "Niveau 2"),
        (4, 3, "Niveau 3"),
        (5, 4, "Niveau 4"),
    ):
        assert (
            f'<h{html_level} data-content-heading-level="{editorial_level}">'
            f"{text}</h{html_level}>"
        ) in html
    assert (project / "site/static/css/site.css").read_bytes() == _CSS_PATH.read_bytes()
