"""Tier 2 of the SEO audit: per-post author, Open Graph completeness, and
a richer JSON-LD payload — all previously either ignored (author) or
missing (og:site_name/locale/image:alt, dateModified, mainEntityOfPage,
inLanguage, publisher, and the generic "Article" type instead of the
more accurate "BlogPosting").
"""

from __future__ import annotations

import json
import re

from bloggen.config.models import ProjectConfig
from bloggen.render.html_templates import render_page_document


def _json_ld(html: str) -> dict:
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    assert match, "no JSON-LD script tag found"
    return json.loads(match.group(1))


def _render_post(config: ProjectConfig, **kwargs) -> str:
    return render_page_document(
        config=config,
        title="Mon billet",
        content_html="<article><p>Texte.</p></article>",
        current_path="/billets/mon-billet/index.html",
        asset_prefix="../..",
        article_date="2026-04-23",
        show_title_heading=True,
        **kwargs,
    )


def _base_config() -> ProjectConfig:
    config = ProjectConfig()
    config.site.base_url = "https://exemple.fr"
    config.site.title = "Mon Site"
    config.site.author = "Auteur du site"
    config.site.language = "fr"
    return config


def test_per_post_author_overrides_the_site_wide_author():
    html = _render_post(_base_config(), author="Marie Curie")
    assert '<meta name="author" content="Marie Curie">' in html
    assert '<meta property="article:author" content="Marie Curie">' in html
    assert "Auteur du site" not in html


def test_falls_back_to_the_site_wide_author_when_the_post_has_none():
    html = _render_post(_base_config(), author=None)
    assert '<meta name="author" content="Auteur du site">' in html


def test_og_site_name_and_locale_are_present():
    html = _render_post(_base_config())
    assert '<meta property="og:site_name" content="Mon Site">' in html
    assert '<meta property="og:locale" content="fr_FR">' in html


def test_og_locale_keeps_an_already_region_qualified_language():
    config = _base_config()
    config.site.language = "fr-CA"
    html = _render_post(config)
    assert '<meta property="og:locale" content="fr_CA">' in html


def test_og_image_alt_present_only_alongside_an_actual_image():
    config = _base_config()
    config.banner.image = "assets/banner/site-banner.jpg"
    config.banner.alt = "Bannière du site"
    html = _render_post(config)
    assert '<meta property="og:image" content="https://exemple.fr/assets/banner/site-banner.jpg">' in html
    assert '<meta property="og:image:alt" content="Bannière du site">' in html


def test_no_og_image_alt_without_an_image():
    html = _render_post(_base_config())
    assert "og:image" not in html
    assert "og:image:alt" not in html


def test_twitter_card_is_summary_large_image_only_with_a_banner_image():
    config = _base_config()
    config.banner.image = "assets/banner/site-banner.jpg"
    html = _render_post(config)
    assert '<meta name="twitter:card" content="summary_large_image">' in html


def test_twitter_card_is_plain_summary_without_a_banner_image():
    html = _render_post(_base_config())
    assert '<meta name="twitter:card" content="summary">' in html
    assert "summary_large_image" not in html


def test_json_ld_is_blog_posting_not_generic_article():
    html = _render_post(_base_config())
    data = _json_ld(html)
    assert data["@type"] == "BlogPosting"


def test_json_ld_includes_date_modified_main_entity_language_and_publisher():
    html = _render_post(_base_config(), modified_date="2026-05-01", author="Marie Curie")
    data = _json_ld(html)
    assert data["dateModified"] == "2026-05-01T00:00:00Z"
    assert data["datePublished"] == "2026-04-23T00:00:00Z"
    assert data["mainEntityOfPage"] == {
        "@type": "WebPage",
        "@id": "https://exemple.fr/billets/mon-billet/index.html",
    }
    assert data["inLanguage"] == "fr"
    assert data["publisher"] == {"@type": "Organization", "name": "Mon Site"}
    assert data["author"] == {"@type": "Person", "name": "Marie Curie"}


def test_json_ld_omits_date_modified_when_not_provided():
    html = _render_post(_base_config(), modified_date=None)
    data = _json_ld(html)
    assert "dateModified" not in data


def test_home_page_json_ld_website_also_gets_in_language():
    config = _base_config()
    html = render_page_document(
        config=config,
        title="Accueil",
        content_html="<article><p>Bienvenue.</p></article>",
        current_path="/index.html",
        asset_prefix=".",
    )
    data = _json_ld(html)
    assert data["@type"] == "WebSite"
    assert data["inLanguage"] == "fr"
