from __future__ import annotations

from pathlib import Path
import re
import shutil
import uuid

import pytest

from bloggen.build.site_builder import build_site
from bloggen.config.defaults import build_default_config

RUNTIME_ROOT = Path("tests/.runtime")
RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)


def test_realistic_google_docs_corpus_with_real_pandoc_if_available():
    if shutil.which("pandoc") is None:
        pytest.skip("Pandoc non disponible dans l'environnement de test.")

    project = RUNTIME_ROOT / f"google_docs_realistic_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "assets/images").mkdir(parents=True)

    shutil.copy2("fixtures/markdown_google_docs/page_longue.md", project / "content/pages/page_longue.md")
    shutil.copy2("fixtures/markdown_google_docs/article_notes.md", project / "content/posts/article_notes.md")
    shutil.copy2("fixtures/markdown_google_docs/article_image.md", project / "content/posts/article_image.md")
    shutil.copy2("examples/minimal_project/assets/images/exemple.jpg", project / "assets/images/exemple.jpg")

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.content.markdown_origin = "google_docs_export"
    config.content.copy_linked_assets = True
    config.media_handling.copy_media_to_output = True
    config.render.enable_lightbox = True
    config.notes_rendering.enable_margin_notes = True
    config.notes_rendering.enable_footnotes = True
    config.home.source = "content/pages/page_longue.md"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    report = build_site(config, config_path=config_path)

    assert report.success is True

    page_html = (project / "site/page-longue/index.html").read_text(encoding="utf-8")
    notes_html = (project / "site/billets/article-notes/index.html").read_text(encoding="utf-8")
    image_html = (project / "site/billets/article-image/index.html").read_text(encoding="utf-8")
    index_html = (project / "site/index.html").read_text(encoding="utf-8")
    archive_html = (project / "site/billets/index.html").read_text(encoding="utf-8")

    assert re.search(r"<em>\s*texte en\s+italique\s*</em>", notes_html) is not None
    assert re.search(r"<strong>\s*texte en\s+gras\s*</strong>", notes_html) is not None
    assert "note-call" in notes_html
    assert "endnotes" in notes_html
    assert "<blockquote>" in notes_html
    assert '<p class="article-meta"><time datetime="2026-04-25">2026-04-25</time></p>' in notes_html

    assert '<figure class="article-figure">' in image_html
    assert "<figcaption>Légende image réaliste</figcaption>" in image_html
    assert "lightbox-link" in image_html
    assert '<p class="article-meta"><time datetime="2026-04-24">2026-04-24</time></p>' in image_html
    assert re.search(r"<p>\s*<figure", image_html) is None
    assert "<p>Légende image réaliste</p>" not in image_html

    assert '<table class="tei-table">' in page_html
    assert "<ul>" in page_html
    assert page_html.count("<li>") >= 5
    assert "<blockquote>" in page_html

    assert 'href="/' not in index_html
    assert 'href="/' not in archive_html
    assert 'href="/' not in notes_html
