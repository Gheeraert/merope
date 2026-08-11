"""Tests for the search box markup injected by render_page_document."""

from __future__ import annotations

import re

from bloggen.config.models import MenuLink, ProjectConfig
from bloggen.render.html_templates import render_page_document


def _config(*, search_enabled: bool = True, with_top_menu: bool = False) -> ProjectConfig:
    config = ProjectConfig()
    config.search.enabled = search_enabled
    if with_top_menu:
        config.menus.top = [MenuLink(label="Accueil", target="/index.html")]
    return config


def test_search_box_present_when_enabled():
    html = render_page_document(
        config=_config(search_enabled=True),
        title="Titre",
        content_html="<p>Contenu</p>",
        current_path="/index.html",
        asset_prefix=".",
    )
    assert 'class="site-search"' in html
    assert 'data-index-href="search-index.json"' in html
    assert 'data-asset-prefix="."' in html
    assert "static/js/search.js" in html


def test_search_box_absent_when_disabled():
    html = render_page_document(
        config=_config(search_enabled=False),
        title="Titre",
        content_html="<p>Contenu</p>",
        current_path="/index.html",
        asset_prefix=".",
    )
    assert "site-search" not in html
    assert "search.js" not in html


def test_search_box_asset_prefix_reflects_page_depth():
    html = render_page_document(
        config=_config(search_enabled=True),
        title="Billet",
        content_html="<p>Contenu</p>",
        current_path="/billets/mon-billet/index.html",
        asset_prefix="../..",
    )
    assert 'data-index-href="../../search-index.json"' in html
    assert 'data-asset-prefix="../.."' in html


def test_search_placeholder_available_in_custom_template():
    html = render_page_document(
        config=_config(search_enabled=True),
        title="Titre",
        content_html="<p>Contenu</p>",
        current_path="/index.html",
        asset_prefix=".",
        custom_template="<div>$search</div><div>$content</div>",
    )
    assert 'class="site-search"' in html
    assert "<p>Contenu</p>" in html


def test_top_menu_and_search_share_one_masthead_bar():
    html = render_page_document(
        config=_config(search_enabled=True, with_top_menu=True),
        title="Titre",
        content_html="<p>Contenu</p>",
        current_path="/index.html",
        asset_prefix=".",
    )
    masthead_match = re.search(r'<div class="masthead">(.*?)</div>\s*<div class="page-layout', html, re.DOTALL)
    assert masthead_match is not None
    masthead_html = masthead_match.group(1)
    assert 'class="top-menu' in masthead_html
    assert 'class="site-search"' in masthead_html


def test_masthead_absent_when_no_top_menu_and_no_search():
    html = render_page_document(
        config=_config(search_enabled=False, with_top_menu=False),
        title="Titre",
        content_html="<p>Contenu</p>",
        current_path="/index.html",
        asset_prefix=".",
    )
    assert "masthead" not in html
