"""Tests for the search box markup injected by render_page_document."""

from __future__ import annotations

from bloggen.config.models import ProjectConfig
from bloggen.render.html_templates import render_page_document


def _config(*, search_enabled: bool = True) -> ProjectConfig:
    config = ProjectConfig()
    config.search.enabled = search_enabled
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
