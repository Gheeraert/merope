"""Responsive figures in a real Markdown site build."""

from __future__ import annotations

from pathlib import Path
import re
import shutil

from lxml import html as lxml_html
from PIL import Image
import pytest

from bloggen.build.site_builder import build_site
from bloggen.config.io import load_config


CSS_PATH = Path("src/bloggen/resources/css/site.css")


def _declarations(css: str, selector: str, *, after: str = "") -> str:
    source = css[css.index(after) :] if after else css
    match = re.search(rf"(?m)^\s*{re.escape(selector)}\s*\{{([^{{}}]*)\}}", source)
    assert match, selector
    return match.group(1)


def test_mobile_grid_and_figures_have_shrinkable_widths():
    css = CSS_PATH.read_text(encoding="utf-8")
    assert "grid-template-columns: minmax(220px, 260px) minmax(0, 1fr)" in (
        _declarations(css, ".page-layout")
    )
    mobile = "@media (max-width: 980px)"
    assert "grid-template-columns: minmax(0, 1fr)" in _declarations(
        css, ".page-layout", after=mobile
    )
    assert "min-width: 0" in _declarations(css, ".main-content", after=mobile)
    figure = _declarations(css, ".article-figure")
    assert "width: fit-content" in figure
    assert "max-width: 100%" in figure
    image_rules = re.findall(r"(?m)^\.article-figure img\s*\{([^{}]*)\}", css)
    image = image_rules[-1]
    assert "max-width: 100%" in image
    assert "height: auto" in image
    assert not re.search(r"(?m)^\s*width\s*:\s*100%", image)
    assert re.search(
        r"\.figure-image-link,\s*\.article-figure img\s*\{\s*display:\s*block",
        css,
    )
    caption = _declarations(css, ".article-figure figcaption")
    assert "width: 0" in caption
    assert "min-width: 100%" in caption
    assert "max-width: min(90vw, 1500px)" in _declarations(css, ".lightbox-image")
    for side in ("left", "right"):
        floated = _declarations(css, f".article-figure.align-{side}")
        assert f"float: {side}" in floated
        assert "max-width: 50%" in floated


def test_editorial_percentages_remain_limits_on_mobile():
    css = CSS_PATH.read_text(encoding="utf-8")
    assert not re.search(
        r"@media\s*\(max-width:\s*40rem\)\s*\{\s*"
        r"\.article-figure\[data-width\]\s*\{\s*"
        r"max-width:\s*100%\s*!important",
        css,
    )


@pytest.mark.skipif(shutil.which("pandoc") is None, reason="Pandoc non disponible")
@pytest.mark.parametrize("with_side_menu", [True, False])
def test_real_markdown_figures_and_builtin_css(tmp_path, with_side_menu):
    project = tmp_path / "site-with-images"
    shutil.copytree(
        Path("examples/minimal_project"),
        project,
        ignore=shutil.ignore_patterns("site", "build", "__pycache__"),
    )
    image_dir = project / "assets/images"
    image_dir.mkdir(parents=True, exist_ok=True)
    wide_names = (
        "wide-natural.png",
        "wide-25.png",
        "wide-50.png",
        "wide-100.png",
        "wide-800.png",
        "wide-1200.png",
        "wide-left.png",
        "wide-right.png",
    )
    for filename in wide_names:
        Image.new("RGB", (2400, 600), (75, 110, 150)).save(image_dir / filename)
    Image.new("RGB", (250, 125), (75, 110, 150)).save(image_dir / "small.png")

    caption = (
        "Légende longue qui doit rester dans la colonne et suivre "
        "la largeur de l'image affichée."
    )

    def image(name: str) -> str:
        return f"../../assets/images/{name}"

    body = "\n\nTexte entre les figures.\n\n".join(
        [
            f"![{caption}]({image('wide-natural.png')})",
            f"![Largeur 25]({image('wide-25.png')}){{width=25%}}",
            f"![Largeur 50]({image('wide-50.png')}){{width=50%}}",
            f"![Largeur 100]({image('wide-100.png')}){{width=100%}}",
            f"![Largeur 800]({image('wide-800.png')}){{width=800}}",
            f"![Largeur 1200]({image('wide-1200.png')}){{width=1200}}",
            f"![Petite image]({image('small.png')})",
            f"![Flottante gauche]({image('wide-left.png')}){{width=50% align=left}}",
            f"![Flottante droite]({image('wide-right.png')}){{width=800 align=right}}",
            "| Colonne A | Colonne B |\n|---|---|\n| Image et tableau | Distincts |",
        ]
    )
    (project / "content/pages/responsive.md").write_text(
        '---\ntitle: "Images responsives"\nslug: "responsive"\ntype: "page"\n---\n\n'
        + body
        + "\n",
        encoding="utf-8",
    )
    config_path = project / "config/site.json"
    config = load_config(config_path)
    if not with_side_menu:
        config.menus.side = []
    report = build_site(config, config_path=config_path)
    assert report.success, report.errors

    page = project / "site/responsive/index.html"
    document = lxml_html.parse(str(page))
    figures = document.xpath("//figure[contains(@class, 'article-figure')]")
    assert len(figures) == 9
    assert bool(document.xpath("//aside[contains(@class, 'side-menu')]")) == with_side_menu
    assert bool(document.xpath("//*[contains(@class, 'no-side-menu')]")) != with_side_menu
    assert len(document.xpath("//table[contains(@class, 'tei-table')]")) == 1
    assert len(document.xpath("//img[contains(@class, 'lightbox-image')]")) == 0
    assert len(document.xpath("//script[contains(@src, 'lightbox.js')]")) == 1

    for figure in figures:
        img = figure.xpath(".//img")[0]
        assert img.get("src")
        assert img.get("style") is None
        assert img.get("height") is None
        assert figure.xpath("./a[contains(@class, 'figure-image-link')]")
        assert figure.xpath("./a")[0].get("href")
        assert figure.xpath("./figcaption")
    for figure, width in zip(figures[1:4], ("25%", "50%", "100%")):
        assert figure.get("data-width") == width
        assert figure.get("style") == f"max-width:{width}"
        assert figure.xpath(".//img")[0].get("width") is None
    for figure, width in zip(figures[4:6], ("800", "1200")):
        assert figure.get("style") is None
        assert figure.xpath(".//img")[0].get("width") == width
    assert figures[0].xpath(".//img")[0].get("width") is None
    assert figures[6].xpath(".//img")[0].get("width") is None
    assert "align-left" in figures[7].get("class")
    assert "align-right" in figures[8].get("class")
    assert (project / "site/static/css/site.css").read_bytes() == CSS_PATH.read_bytes()
    for filename in wide_names:
        with Image.open(project / "site/assets/images" / filename) as actual:
            assert actual.size == (2400, 600)
    with Image.open(project / "site/assets/images/small.png") as actual:
        assert actual.size == (250, 125)
