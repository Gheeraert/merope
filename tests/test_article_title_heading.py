"""render_page_document must guarantee exactly one <h1> per page — the
page's own title. Previously the injected title fell back to <h2> unless
the content already had its own <h1> (a top-level TEI div heading), in
which case *that* stayed <h1> instead of the real title — so a page
could end up with zero or two <h1> elements depending on its content
structure, never a reliable single one.
"""

from __future__ import annotations

import re

from bloggen.config.models import ProjectConfig
from bloggen.render.html_templates import render_page_document


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
    assert "<h2>Titre interne</h2>" in html


def test_nested_heading_hierarchy_is_preserved_after_the_shift():
    html = _render(
        '<article class="tei-fragment">'
        "<section><h1>Section</h1>"
        "<section><h2>Sous-section</h2>"
        "<section><h3>Sous-sous-section</h3></section>"
        "</section></section>"
        "</article>"
    )
    assert "<h2>Section</h2>" in html
    assert "<h3>Sous-section</h3>" in html
    assert "<h4>Sous-sous-section</h4>" in html
    # Relative order/nesting is unaffected — only the levels shifted.
    assert html.index("<h2>Section</h2>") < html.index("<h3>Sous-section</h3>") < html.index(
        "<h4>Sous-sous-section</h4>"
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
    assert html.count("<h2>Premier</h2>") == 1
    assert html.count("<h2>Second</h2>") == 1


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
