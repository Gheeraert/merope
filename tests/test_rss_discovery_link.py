"""The generated <head> must let feed readers/browsers auto-discover the
RSS feed via <link rel="alternate" type="application/rss+xml"> — the feed
file existed, but nothing in the page pointed to it."""

from __future__ import annotations

from bloggen.config.models import ProjectConfig
from bloggen.render.html_templates import render_page_document


def _render(config: ProjectConfig) -> str:
    return render_page_document(
        config=config,
        title="Un billet",
        content_html="<article><p>Texte.</p></article>",
        current_path="/billets/un-billet/index.html",
        asset_prefix="../..",
    )


def test_rss_link_present_when_feed_is_generated():
    config = ProjectConfig()
    config.site.base_url = "https://exemple.fr"
    config.site.title = "Mon Site"
    html = _render(config)
    assert (
        '<link rel="alternate" type="application/rss+xml" title="Mon Site" href="../../feed.xml">'
        in html
    )


def test_rss_link_absent_without_a_base_url():
    """feed.xml itself isn't generated without base_url (see
    _generate_feed_and_sitemap) — the <link> must not point at a file
    that doesn't exist."""
    config = ProjectConfig()
    config.site.base_url = ""
    html = _render(config)
    assert "application/rss+xml" not in html


def test_rss_link_absent_when_blog_is_disabled():
    config = ProjectConfig()
    config.site.base_url = "https://exemple.fr"
    config.blog.enabled = False
    html = _render(config)
    assert "application/rss+xml" not in html


def test_rss_link_absent_when_rss_generation_is_disabled():
    config = ProjectConfig()
    config.site.base_url = "https://exemple.fr"
    config.blog.generate_rss_feed = False
    html = _render(config)
    assert "application/rss+xml" not in html
