from bloggen.config.models import MenuLink, SideMenuSection
from bloggen.render.html_templates import render_archive_fragment
from bloggen.render.navigation import build_side_menu_html, resolve_navigation_href


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


def test_side_menu_section_without_target_renders_plain_heading():
    html = build_side_menu_html(
        [SideMenuSection(label="Navigation")], current_path="/index.html"
    )
    assert "<h3>Navigation</h3>" in html
    assert "side-menu-section-link" not in html


def test_side_menu_section_with_target_renders_clickable_heading():
    html = build_side_menu_html(
        [SideMenuSection(label="Présentation", target="/projet/index.html")],
        current_path="/billets/index.html",
    )
    assert '<h3><a class="side-menu-section-link" href="../projet/index.html">Présentation</a></h3>' in html


def test_side_menu_section_link_gets_active_class_on_its_own_page():
    html = build_side_menu_html(
        [SideMenuSection(label="Présentation", target="/projet/index.html")],
        current_path="/projet/index.html",
    )
    assert 'class="side-menu-section-link is-active"' in html


def test_side_menu_section_can_have_both_own_link_and_children():
    html = build_side_menu_html(
        [
            SideMenuSection(
                label="Le projet",
                target="/projet/index.html",
                children=[MenuLink(label="Corpus", target="/corpus/index.html")],
            )
        ],
        current_path="/billets/index.html",
    )
    assert 'href="../projet/index.html">Le projet</a></h3>' in html
    assert 'href="../corpus/index.html">Corpus</a>' in html
