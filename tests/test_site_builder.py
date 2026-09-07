from __future__ import annotations

from pathlib import Path
import uuid

from bloggen.build.site_builder import build_site
from bloggen.config.defaults import build_default_config
from bloggen.tei.pandoc_converter import MarkdownToTeiResult
from bloggen.tei.validator import TeiValidationResult

RUNTIME_ROOT = Path("tests/.runtime")
RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)


TEI_SAMPLE = (
    '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
    '<teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt>'
    '<publicationStmt><p>p</p></publicationStmt><sourceDesc><p>s</p></sourceDesc></fileDesc></teiHeader>'
    '<text><body><div><head>Titre</head>'
    '<p>Contenu avec note<note>Note test</note></p>'
    '<figure><head>Légende test</head><graphic url="media/inline.jpg"/></figure>'
    '</div></body></text>'
    '</TEI>'
)


def test_site_builder_generates_illustrated_site(monkeypatch):
    project = RUNTIME_ROOT / f"site_builder_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts/media").mkdir(parents=True)
    (project / "assets/images").mkdir(parents=True)
    (project / "assets/banner").mkdir(parents=True)

    (project / "content/posts/media/inline.jpg").write_bytes(b"img")
    (project / "assets/images/pic.jpg").write_bytes(b"img")
    (project / "assets/banner/site-banner.jpg").write_bytes(b"img")

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n\nTexte.\n',
        encoding="utf-8",
    )
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier"\nslug: "premier-billet"\ntype: "post"\ndate: "2026-04-23"\n---\n\n# Premier\n\nImage ![Inline](media/inline.jpg)\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.content.copy_linked_assets = True
    config.media_handling.copy_media_to_output = True
    config.render.enable_lightbox = True
    config.notes_rendering.enable_margin_notes = True
    config.notes_rendering.enable_footnotes = True
    config.banner.enabled = True
    config.banner.image = "assets/banner/site-banner.jpg"
    config.banner.link = "/index.html"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    def fake_convert(input_path, output_path, **_kwargs):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(TEI_SAMPLE, encoding="utf-8")
        return MarkdownToTeiResult(
            source_file=Path(input_path),
            tei_file=out,
            command=["pandoc"],
            success=True,
            message="ok",
            validation=TeiValidationResult(valid=True),
        )

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert (project / "site/index.html").exists()
    assert (project / "site/accueil/index.html").exists()
    assert (project / "site/billets/index.html").exists()
    assert (project / "site/billets/premier-billet/index.html").exists()
    assert (project / "build/tei/pages/accueil.xml").exists()
    assert (project / "build/tei/posts/premier-billet.xml").exists()
    assert (project / "site/content-media/post/premier-billet/media/inline.jpg").exists()
    assert (project / "site/search-index.json").exists()

    # A permanent, usable TEI copy (full document, own teiHeader) is kept
    # next to each Markdown source, named after that source file itself
    # ("premier.md" here, not its "premier-billet" slug) rather than the
    # slug-keyed staging copy under build/tei/.
    content_page_tei = project / "content/pages/accueil.xml"
    content_post_tei = project / "content/posts/premier.xml"
    assert content_page_tei.exists()
    assert content_post_tei.exists()
    assert "teiHeader" in content_page_tei.read_text(encoding="utf-8")
    assert "teiHeader" in content_post_tei.read_text(encoding="utf-8")

    import json

    index_entries = json.loads((project / "site/search-index.json").read_text(encoding="utf-8"))
    assert len(index_entries) == 2  # accueil (page) + premier-billet (home/archive pages are not indexed)
    urls = {entry["url"] for entry in index_entries}
    assert "/billets/premier-billet/index.html" in urls

    post_html = (project / "site/billets/premier-billet/index.html").read_text(encoding="utf-8")
    index_html = (project / "site/index.html").read_text(encoding="utf-8")
    archive_html = (project / "site/billets/index.html").read_text(encoding="utf-8")
    home_html = (project / "site/accueil/index.html").read_text(encoding="utf-8")
    assert "lightbox-link" in post_html
    assert "data-lightbox-group" in post_html
    assert "endnotes" in post_html
    assert "margin-notes" not in post_html  # not implemented for now, see render/margin_notes.py
    assert '<p class="article-meta"><time datetime="2026-04-23">2026-04-23</time></p>' in post_html
    assert "top-nav" in post_html
    assert "side-nav" in post_html
    assert "article-content" in post_html
    assert 'href="../../index.html"' in post_html
    assert 'href="../index.html"' in post_html
    assert 'href="/index.html"' not in post_html
    assert '<header class="site-banner"' in post_html
    assert 'href="premier-billet/index.html"' in archive_html
    assert 'href="/billets/premier-billet/index.html"' not in archive_html
    assert "archive-date" in archive_html
    assert "article-content" in home_html
    assert '<p class="article-meta">' not in home_html
    assert 'href="/' not in index_html
    assert 'href="/' not in archive_html


def test_site_builder_home_page_can_list_recent_posts(monkeypatch):
    project = RUNTIME_ROOT / f"site_builder_home_recent_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier billet"\nslug: "premier-billet"\ntype: "post"\ndate: "2026-01-01"\n---\n\n# Premier\n',
        encoding="utf-8",
    )
    (project / "content/posts/second.md").write_text(
        '---\ntitle: "Second billet"\nslug: "second-billet"\ntype: "post"\ndate: "2026-04-23"\n---\n\n# Second\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.home.mode = "recent_posts"
    config.home.recent_posts_count = 1

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    def fake_convert(input_path, output_path, **_kwargs):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(TEI_SAMPLE, encoding="utf-8")
        return MarkdownToTeiResult(
            source_file=Path(input_path),
            tei_file=out,
            command=["pandoc"],
            success=True,
            message="ok",
            validation=TeiValidationResult(valid=True),
        )

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    home_html = (project / "site/index.html").read_text(encoding="utf-8")
    # No page-level "Derniers billets" heading: the individual post titles
    # already identify the content.
    assert "<h1>Derniers billets</h1>" not in home_html
    assert "Second billet" in home_html
    assert 'href="billets/second-billet/index.html"' in home_html
    # only the most recent post (recent_posts_count = 1) is listed
    assert "Premier billet" not in home_html


def test_site_builder_skips_search_index_when_disabled(monkeypatch):
    project = RUNTIME_ROOT / f"site_builder_nosearch_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.search.enabled = False

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    def fake_convert(input_path, output_path, **_kwargs):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(TEI_SAMPLE, encoding="utf-8")
        return MarkdownToTeiResult(
            source_file=Path(input_path),
            tei_file=out,
            command=["pandoc"],
            success=True,
            message="ok",
            validation=TeiValidationResult(valid=True),
        )

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert not (project / "site/search-index.json").exists()
    home_html = (project / "site/accueil/index.html").read_text(encoding="utf-8")
    assert "site-search" not in home_html


def test_site_builder_generates_iframe_page_for_external_menu_link(monkeypatch):
    project = RUNTIME_ROOT / f"site_builder_external_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )

    from bloggen.config.models import MenuLink

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.menus.top.append(
        MenuLink(label="Wikipédia", target="https://fr.wikipedia.org", target_type="external")
    )

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    def fake_convert(input_path, output_path, **_kwargs):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(TEI_SAMPLE, encoding="utf-8")
        return MarkdownToTeiResult(
            source_file=Path(input_path),
            tei_file=out,
            command=["pandoc"],
            success=True,
            message="ok",
            validation=TeiValidationResult(valid=True),
        )

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    # The original config object is never mutated by the build.
    assert config.menus.top[-1].target == "https://fr.wikipedia.org"

    wrapper = project / "site/liens-externes/wikipedia/index.html"
    assert wrapper.exists()
    wrapper_html = wrapper.read_text(encoding="utf-8")
    assert '<iframe class="external-embed-frame" src="https://fr.wikipedia.org"' in wrapper_html
    assert 'target="_blank"' in wrapper_html  # the plain fallback link, not the nav link

    home_html = (project / "site/index.html").read_text(encoding="utf-8")
    assert 'href="liens-externes/wikipedia/index.html"' in home_html
    assert "https://fr.wikipedia.org" not in home_html


def test_site_builder_generates_iframe_page_for_external_side_section(monkeypatch):
    project = RUNTIME_ROOT / f"site_builder_external_section_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )

    from bloggen.config.models import MenuLink, SideMenuSection

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.menus.side.append(
        SideMenuSection(
            label="Ressources",
            target="https://fr.wikipedia.org",
            target_type="external",
            children=[MenuLink(label="Accueil", target="/index.html")],
        )
    )

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    def fake_convert(input_path, output_path, **_kwargs):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(TEI_SAMPLE, encoding="utf-8")
        return MarkdownToTeiResult(
            source_file=Path(input_path),
            tei_file=out,
            command=["pandoc"],
            success=True,
            message="ok",
            validation=TeiValidationResult(valid=True),
        )

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert config.menus.side[-1].target == "https://fr.wikipedia.org"  # original untouched

    wrapper = project / "site/liens-externes/ressources/index.html"
    assert wrapper.exists()

    home_html = (project / "site/index.html").read_text(encoding="utf-8")
    assert 'class="side-menu-section-link" href="liens-externes/ressources/index.html"' in home_html
    # the section's own children still render alongside its own link
    assert "Accueil</a></li>" in home_html


def test_site_builder_renders_three_level_numbered_outline(monkeypatch):
    """Real end-to-end reproduction of the rhetoric-plan example that
    motivated the third menu level: I. Rhétorique / A. Bossuet et la
    rhétorique chrétienne / <billets>, generated through the actual
    Pandoc/TEI/XSLT pipeline, not just navigation.py in isolation."""
    project = RUNTIME_ROOT / f"site_builder_outline_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )

    from bloggen.config.models import MenuLink, SideMenuSection, SideMenuSubSection

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.menus.side.append(
        SideMenuSection(
            label="Rhétorique",
            numbered=True,
            subsections=[
                SideMenuSubSection(
                    label="Bossuet et la rhétorique chrétienne",
                    children=[
                        MenuLink(label="L'héritage de saint Augustin", target="/billets/a/index.html"),
                        MenuLink(label="La place de l'héritage profane", target="/billets/b/index.html"),
                    ],
                ),
                SideMenuSubSection(
                    label="Des figures pour convaincre",
                    children=[
                        MenuLink(label="Convaincre la raison", target="/billets/c/index.html"),
                        MenuLink(label="Persuader le coeur", target="/billets/d/index.html"),
                    ],
                ),
            ],
        )
    )

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    def fake_convert(input_path, output_path, **_kwargs):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(TEI_SAMPLE, encoding="utf-8")
        return MarkdownToTeiResult(
            source_file=Path(input_path),
            tei_file=out,
            command=["pandoc"],
            success=True,
            message="ok",
            validation=TeiValidationResult(valid=True),
        )

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    home_html = (project / "site/index.html").read_text(encoding="utf-8")
    assert "<h3>I. Rhétorique</h3>" in home_html
    assert "<h4>A. Bossuet et la rhétorique chrétienne</h4>" in home_html
    assert "<h4>B. Des figures pour convaincre</h4>" in home_html
    assert 'href="billets/a/index.html">L&#x27;héritage de saint Augustin</a>' in home_html
    assert 'href="billets/d/index.html">Persuader le coeur</a>' in home_html


def test_site_builder_disables_missing_banner_without_failing(monkeypatch):
    project = RUNTIME_ROOT / f"site_builder_banner_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.banner.enabled = True
    config.banner.image = "assets/banner/does-not-exist.jpg"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    def fake_convert(input_path, output_path, **_kwargs):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(TEI_SAMPLE, encoding="utf-8")
        return MarkdownToTeiResult(
            source_file=Path(input_path),
            tei_file=out,
            command=["pandoc"],
            success=True,
            message="ok",
            validation=TeiValidationResult(valid=True),
        )

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert any("Bannière désactivée" in warning for warning in report.warnings)
    index_html = (project / "site/index.html").read_text(encoding="utf-8")
    assert '<header class="site-banner"' not in index_html


def test_site_builder_skips_draft_posts(monkeypatch):
    project = RUNTIME_ROOT / f"site_builder_draft_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "content/posts/published.md").write_text(
        '---\ntitle: "Publie"\nslug: "publie"\ntype: "post"\ndate: "2026-04-23"\n---\n\n# Publie\n',
        encoding="utf-8",
    )
    (project / "content/posts/draft.md").write_text(
        '---\ntitle: "Brouillon"\nslug: "brouillon"\ntype: "post"\ndate: "2026-04-24"\ndraft: true\n---\n\n# Brouillon\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    def fake_convert(input_path, output_path, **_kwargs):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(TEI_SAMPLE, encoding="utf-8")
        return MarkdownToTeiResult(
            source_file=Path(input_path),
            tei_file=out,
            command=["pandoc"],
            success=True,
            message="ok",
            validation=TeiValidationResult(valid=True),
        )

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert any("Brouillon ignoré" in warning for warning in report.warnings)
    assert (project / "site/billets/publie/index.html").exists()
    assert not (project / "site/billets/brouillon/index.html").exists()
    assert (project / "build/tei/posts/publie.xml").exists()
    assert not (project / "build/tei/posts/brouillon.xml").exists()


def test_site_builder_fails_on_missing_front_matter():
    project = RUNTIME_ROOT / f"site_builder_missing_yaml_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text("# Accueil sans yaml\n", encoding="utf-8")

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    report = build_site(config, config_path=config_path)

    assert report.success is False
    assert any("Front matter YAML manquant" in error for error in report.errors)


def test_site_builder_refuses_to_clean_an_output_dir_that_is_the_project_root():
    project = RUNTIME_ROOT / f"site_builder_dangerous_output_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    marker = project / "content/pages/ne-pas-supprimer.md"
    marker.write_text("contenu precieux", encoding="utf-8")

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "."  # dangerous: same as the project root itself
    config.paths.tei_dir = "build/tei"
    config.build.clean_output_dir = True

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    report = build_site(config, config_path=config_path)

    assert report.success is False
    assert any("Dossier de sortie dangereux" in error for error in report.errors)
    assert marker.exists()  # the project must survive the attempted clean


def test_site_builder_refuses_to_clean_an_output_dir_that_is_content_dir():
    project = RUNTIME_ROOT / f"site_builder_dangerous_output_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    marker = project / "content/pages/ne-pas-supprimer.md"
    marker.write_text("contenu precieux", encoding="utf-8")

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    # dangerous: output_dir is exactly content_dir (a mistake distinct from
    # "output_dir == project_root", covered by the previous test).
    config.paths.output_dir = "content"
    config.paths.tei_dir = "build/tei"
    config.build.clean_output_dir = True

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    report = build_site(config, config_path=config_path)

    assert report.success is False
    assert any("Dossier de sortie dangereux" in error for error in report.errors)
    assert marker.exists()


def test_site_builder_refuses_an_output_dir_outside_the_project_via_absolute_path():
    project = RUNTIME_ROOT / f"site_builder_dangerous_output_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)

    outside = RUNTIME_ROOT / f"site_builder_outside_target_{uuid.uuid4().hex}"
    outside.mkdir(parents=True)
    unrelated = outside / "important-document.txt"
    unrelated.write_text("ne pas supprimer", encoding="utf-8")

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    # dangerous: an absolute path silently discards project_root when
    # joined (Path(project_root) / "C:/..." == "C:/...").
    config.paths.output_dir = str(outside.resolve())
    config.paths.tei_dir = "build/tei"
    config.build.clean_output_dir = True

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    report = build_site(config, config_path=config_path)

    assert report.success is False
    assert any("Dossier de sortie dangereux" in error for error in report.errors)
    assert unrelated.exists()  # the folder outside the project must survive


def test_site_builder_refuses_an_output_dir_outside_the_project_via_traversal():
    project = RUNTIME_ROOT / f"site_builder_dangerous_output_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)

    unrelated = RUNTIME_ROOT / "escaped-via-dotdot.txt"
    unrelated.write_text("ne pas supprimer", encoding="utf-8")

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    # dangerous: ".." climbs back out of the project root entirely.
    config.paths.output_dir = ".."
    config.paths.tei_dir = "build/tei"
    config.build.clean_output_dir = True

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    report = build_site(config, config_path=config_path)

    assert report.success is False
    assert any("Dossier de sortie dangereux" in error for error in report.errors)
    assert unrelated.exists()


def test_site_builder_disabling_blog_stops_post_generation_entirely():
    """The "Activer blog" checkbox's own tooltip promises "aucune page de
    blog ni d'archive n'est générée" when off — not just the archive/RSS —
    so individual posts must not be rendered, indexed for search, or
    listed in the sitemap either when blog.enabled is False."""
    project = RUNTIME_ROOT / f"site_builder_blog_disabled_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)

    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier"\nslug: "premier-billet"\ntype: "post"\ndate: "2026-04-23"\n---\n\n# Premier\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.blog.enabled = False

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert (project / "site/accueil/index.html").exists()
    assert not (project / "site/billets/premier-billet/index.html").exists()
    assert not (project / "site/billets/index.html").exists()
    assert not (project / "build/tei/posts/premier-billet.xml").exists()

    import json

    index_entries = json.loads((project / "site/search-index.json").read_text(encoding="utf-8"))
    urls = {entry["url"] for entry in index_entries}
    assert "/billets/premier-billet/index.html" not in urls


def test_site_builder_preserves_last_good_site_when_a_later_build_fails():
    """Reproduces the scenario flagged by the external audit: a build that
    fails partway through must not destroy the previously published site —
    the old commit-and-rmtree-up-front behaviour left nothing publishable
    until the next successful build."""
    project = RUNTIME_ROOT / f"site_builder_transactional_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)

    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier"\nslug: "premier-billet"\ntype: "post"\ndate: "2026-04-23"\n---\n\n# Premier\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.build.clean_output_dir = True
    config.home.mode = "recent_posts"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    first_report = build_site(config, config_path=config_path)
    assert first_report.success is True

    post_html = project / "site" / "billets" / "premier-billet" / "index.html"
    assert post_html.exists()
    good_content = post_html.read_text(encoding="utf-8")
    assert "Premier" in good_content

    # Break a second post's metadata so the second build fails partway
    # through content loading, after the first build already published
    # a good site.
    (project / "content/posts/second.md").write_text(
        '---\nslug: "second-billet"\ntype: "post"\ndate: "2026-04-24"\n---\n\n# Sans titre\n',
        encoding="utf-8",
    )

    second_report = build_site(config, config_path=config_path)

    assert second_report.success is False
    assert second_report.errors  # the missing-title error was captured

    # The site from the first, successful build must survive untouched.
    assert post_html.exists()
    assert post_html.read_text(encoding="utf-8") == good_content

    # No leftover staging directory from the aborted build.
    leftovers = list(project.glob(".site.building-*"))
    assert leftovers == []


def test_site_builder_allows_a_normal_output_dir_nested_under_project_root():
    """The default/typical layout (output_dir a plain subfolder of the
    project) must not be flagged by the new guard."""
    project = RUNTIME_ROOT / f"site_builder_safe_output_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "site").mkdir(parents=True)
    (project / "site" / "stale.html").write_text("old", encoding="utf-8")

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.build.clean_output_dir = True

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    report = build_site(config, config_path=config_path)

    # No pages/posts exist here, so the build itself produces no content
    # pages, but it must get past the cleanup step without error and
    # actually clean the stale file.
    assert not any("Dossier de sortie dangereux" in error for error in report.errors)
    assert not (project / "site" / "stale.html").exists()
