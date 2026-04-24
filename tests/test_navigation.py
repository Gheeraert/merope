from bloggen.render.html_templates import render_archive_fragment
from bloggen.render.navigation import resolve_navigation_href


def test_resolve_navigation_href_keeps_external_and_anchor_links():
    assert resolve_navigation_href("https://example.org", current_path="/billets/post/index.html") == "https://example.org"
    assert resolve_navigation_href("mailto:test@example.org", current_path="/billets/post/index.html") == "mailto:test@example.org"
    assert resolve_navigation_href("#notes", current_path="/billets/post/index.html") == "#notes"


def test_resolve_navigation_href_converts_root_internal_links_to_relative():
    assert resolve_navigation_href("/index.html", current_path="/billets/premier-billet/index.html") == "../../index.html"
    assert resolve_navigation_href("/billets/index.html", current_path="/billets/premier-billet/index.html") == "../index.html"


def test_resolve_navigation_href_keeps_already_relative_links():
    assert resolve_navigation_href("../index.html", current_path="/billets/premier-billet/index.html") == "../index.html"


def test_render_archive_fragment_relativizes_only_internal_root_links():
    html = render_archive_fragment(
        "Archive",
        [
            ("Interne", "/billets/premier-billet/index.html"),
            ("Externe", "https://example.org/post"),
            ("Mail", "mailto:test@example.org"),
            ("Ancre", "#section"),
        ],
        current_path="/billets/index.html",
    )

    assert 'href="premier-billet/index.html"' in html
    assert 'href="/billets/premier-billet/index.html"' not in html
    assert 'href="https://example.org/post"' in html
    assert 'href="mailto:test@example.org"' in html
    assert 'href="#section"' in html
