"""The optional top banner stays separate from the editorial banner."""

from __future__ import annotations

import re
from pathlib import Path

from bloggen.config.models import ProjectConfig
from bloggen.render.html_templates import render_page_document


def _render(config: ProjectConfig, *, current_path: str = "/index.html", asset_prefix: str = ".", custom_template: str | None = None) -> str:
    return render_page_document(
        config=config,
        title="Accueil",
        content_html="<p>Contenu</p>",
        current_path=current_path,
        asset_prefix=asset_prefix,
        custom_template=custom_template,
    )


def test_disabled_or_empty_top_banner_renders_nothing():
    config = ProjectConfig()
    config.top_banner.image = "assets/top-banner/institution.png"
    assert 'class="top-banner"' not in _render(config)

    config.top_banner.enabled = True
    config.top_banner.image = ""
    assert 'class="top-banner"' not in _render(config)


def test_top_banner_without_link_has_image_and_empty_alt_but_no_anchor():
    config = ProjectConfig()
    config.top_banner.enabled = True
    config.top_banner.image = "assets/top-banner/institution.png"

    html = _render(config)

    assert '<div class="top-banner"><img class="top-banner-image" src="assets/top-banner/institution.png" alt=""></div>' in html
    assert 'class="top-banner-link"' not in html
    assert '<a href="">' not in html


def test_top_banner_link_escapes_attributes_and_resolves_internal_paths():
    config = ProjectConfig()
    config.top_banner.enabled = True
    config.top_banner.image = "assets/top-banner/institution.png"
    config.top_banner.alt = 'Université & "Institut"'
    config.top_banner.link = '/pages/profondes/index.html?x=1&y="2"'

    html = _render(config, current_path="/billets/mon-billet/index.html", asset_prefix="../..")

    assert '<div class="top-banner"><a class="top-banner-link" href="../../pages/profondes/index.html?x=1&amp;y=&quot;2&quot;">' in html
    assert 'src="../../assets/top-banner/institution.png"' in html
    assert 'alt="Université &amp; &quot;Institut&quot;"' in html
    assert '</a></div>' in html


def test_top_banner_accepts_external_link_and_precedes_banner_and_masthead():
    config = ProjectConfig()
    config.top_banner.enabled = True
    config.top_banner.image = "assets/top-banner/institution.png"
    config.top_banner.link = "https://example.org/?a=1&b=2"
    config.banner.enabled = True
    config.banner.image = "assets/banner/editorial.png"

    html = _render(config)

    assert 'href="https://example.org/?a=1&amp;b=2"' in html
    assert 'target="_blank"' not in html
    assert html.index('class="top-banner"') < html.index('class="site-banner"') < html.index('class="masthead"')


def test_custom_template_can_place_top_banner_and_legacy_template_still_works():
    config = ProjectConfig()
    config.top_banner.enabled = True
    config.top_banner.image = "assets/top-banner/institution.png"

    html = _render(config, custom_template="<body>${top_banner}<main>$content</main></body>")
    legacy_html = _render(config, custom_template="<body><main>$content</main></body>")

    assert 'class="top-banner"' in html
    assert '<p>Contenu</p>' in legacy_html
    assert 'class="top-banner"' not in legacy_html


def test_top_banner_css_preserves_natural_size_and_mobile_containment():
    css = Path("src/bloggen/resources/css/site.css").read_text(encoding="utf-8")

    def declarations(selector: str) -> str:
        match = re.search(rf"(?m)^\{selector}\s*\{{([^}}]+)\}}", css)
        assert match is not None
        return match.group(1)

    banner = declarations(".top-banner")
    image = declarations(".top-banner-image")
    link = declarations(".top-banner-link")

    assert re.search(r"background:\s*#fff\s*;", banner)
    assert re.search(r"max-width:\s*var\(--page-max-width\)\s*;", banner)
    assert re.search(r"max-width:\s*100%\s*;", link)
    assert re.search(r"max-width:\s*100%\s*;", image)
    assert re.search(r"max-height:\s*72px\s*;", image)
    assert re.search(r"width:\s*auto\s*;", image)
    assert re.search(r"height:\s*auto\s*;", image)
    assert "object-fit: cover" not in image
    assert not re.search(r"(?<!-)width:\s*100%\s*;", image)
    assert "@media (max-width: 640px) {\n  .top-banner {" in css
