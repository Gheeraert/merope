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
    # premier-billet only: accueil is the home.source page, duplicated
    # onto /index.html and excluded from the on-site search index the
    # same way it's excluded from the sitemap (see noindex handling).
    assert len(index_entries) == 1
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


def test_recent_posts_mode_shows_an_excerpt_not_the_full_body(monkeypatch):
    """Third external audit finding: "derniers billets" mode duplicated
    every recent post's *entire* content onto /index.html, both URLs
    fully indexable. The home page must now show only a short excerpt
    and a link — the full text stays exclusively on the post's own page."""
    project = RUNTIME_ROOT / f"recent_posts_excerpt_{uuid.uuid4().hex}"
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

    long_paragraph = "Phrase significative répétée pour dépasser la longueur d'extrait. " * 10
    long_tei = (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
        '<teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt>'
        '<publicationStmt><p>p</p></publicationStmt><sourceDesc><p>s</p></sourceDesc></fileDesc></teiHeader>'
        f'<text><body><div><head>Titre</head><p>{long_paragraph}</p></div></body></text>'
        '</TEI>'
    )

    def fake_convert(input_path, output_path, **_kwargs):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(long_tei, encoding="utf-8")
        return MarkdownToTeiResult(
            source_file=Path(input_path),
            tei_file=out,
            command=["pandoc"],
            success=True,
            message="ok",
            validation=TeiValidationResult(valid=True),
        )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.home.mode = "recent_posts"
    config.home.recent_posts_excerpt_length = 60

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", fake_convert)

    report = build_site(config, config_path=config_path)
    assert report.success is True

    home_html = (project / "site/index.html").read_text(encoding="utf-8")
    post_html = (project / "site/billets/premier-billet/index.html").read_text(encoding="utf-8")

    assert long_paragraph.strip() in post_html  # full text still lives on the post's own page
    assert long_paragraph.strip() not in home_html  # but not duplicated onto the home page
    assert 'class="recent-post-excerpt"' in home_html
    assert 'class="recent-post-more" href="billets/premier-billet/index.html"' in home_html


def test_recent_posts_excerpt_prefers_the_authored_description(monkeypatch):
    project = RUNTIME_ROOT / f"recent_posts_description_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier billet"\nslug: "premier-billet"\ntype: "post"\ndate: "2026-01-01"\n'
        'description: "Résumé rédigé à la main pour ce billet."\n---\n\n# Premier\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.home.mode = "recent_posts"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)
    assert report.success is True

    home_html = (project / "site/index.html").read_text(encoding="utf-8")
    assert "Résumé rédigé à la main pour ce billet." in home_html


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


def test_noindexed_home_source_page_is_excluded_from_the_search_index(monkeypatch):
    """Third external audit finding: the home.source page (duplicated
    onto /index.html, marked noindex, excluded from the sitemap) still
    turned up as its own separate result in the on-site search index."""
    project = RUNTIME_ROOT / f"search_index_noindex_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "content/pages/autre.md").write_text(
        '---\ntitle: "Autre page"\nslug: "autre"\ntype: "page"\n---\n\n# Autre page\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)
    assert report.success is True

    import json

    index_entries = json.loads((project / "site/search-index.json").read_text(encoding="utf-8"))
    urls = {entry["url"] for entry in index_entries}
    assert "/accueil/index.html" not in urls
    assert "/autre/index.html" in urls  # an ordinary, non-noindexed page stays indexed


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
    assert any("Chemin dangereux" in error for error in report.errors)
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
    assert any("Chemin dangereux" in error for error in report.errors)
    assert unrelated.exists()


def test_site_builder_refuses_a_not_yet_existing_external_output_dir():
    """Third external audit finding: the containment check only ran when
    clean_output_dir was on AND the directory already existed — a first
    build to a not-yet-created external path was never checked.
    Confirmed exploitable before this fix."""
    project = RUNTIME_ROOT / f"site_builder_ext_nonexistent_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )

    external_target = RUNTIME_ROOT.resolve() / f"external_target_{uuid.uuid4().hex}"
    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = str(external_target)
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.build.clean_output_dir = True

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    report = build_site(config, config_path=config_path)

    assert report.success is False
    assert any("Chemin dangereux" in error for error in report.errors)
    assert not external_target.exists()


def test_site_builder_refuses_an_external_output_dir_even_with_clean_output_dir_off():
    """Fourth finding: with clean_output_dir=False the containment check
    was never called at all, regardless of whether the directory existed.
    Confirmed exploitable before this fix."""
    project = RUNTIME_ROOT / f"site_builder_ext_noclean_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )

    external_target = RUNTIME_ROOT.resolve() / f"external_target_noclean_{uuid.uuid4().hex}"
    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = str(external_target)
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.build.clean_output_dir = False

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    report = build_site(config, config_path=config_path)

    assert report.success is False
    assert any("Chemin dangereux" in error for error in report.errors)
    assert not external_target.exists()


def test_site_builder_refuses_an_external_assets_dir():
    """assets_dir pointed outside the project would have
    copy_project_assets publish an unrelated folder's contents into the
    generated site."""
    project = RUNTIME_ROOT / f"site_builder_ext_assets_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )

    outside_assets = RUNTIME_ROOT.resolve() / f"outside_assets_{uuid.uuid4().hex}"
    outside_assets.mkdir(parents=True)
    (outside_assets / "private.txt").write_text("confidentiel", encoding="utf-8")

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = str(outside_assets)
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    report = build_site(config, config_path=config_path)

    assert report.success is False
    assert any("Chemin dangereux" in error for error in report.errors)
    assert not (project / "site").exists()


def test_blog_archive_path_traversal_is_rejected():
    """blog.archive_path is joined straight into an output path and was
    never passed through slugify() — confirmed exploitable before this
    fix: a build with archive_path="../../../escaped" actually wrote a
    file outside the project."""
    project = RUNTIME_ROOT / f"archive_path_traversal_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier"\nslug: "premier"\ntype: "post"\ndate: "2026-01-01"\n---\n\n# Premier\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.blog.archive_path = "../../../escaped-via-archive-path"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    report = build_site(config, config_path=config_path)

    assert report.success is False
    assert any("Chemin d'archive dangereux" in error for error in report.errors)
    escaped = project.resolve().parent.parent / "escaped-via-archive-path"
    assert not escaped.exists()


def test_blog_archive_path_allows_multiple_safe_segments(monkeypatch):
    project = RUNTIME_ROOT / f"archive_path_multi_segment_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier"\nslug: "premier"\ntype: "post"\ndate: "2026-01-01"\n---\n\n# Premier\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.blog.archive_path = "archives/billets"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert (project / "site/archives/billets/premier/index.html").exists()


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


def test_site_builder_survives_a_non_permission_error_during_the_final_swap(monkeypatch):
    """A second external audit flagged that the swap wasn't actually
    atomic: the old rmtree-then-rename approach only retried
    PermissionError, so any other rename failure (a stray external
    delete, a same-volume race, ...) after the old site was already
    deleted left nothing in its place — confirmed exploitable before
    this fix by forcing exactly that failure mode."""
    project = RUNTIME_ROOT / f"site_builder_swap_failure_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "site").mkdir(parents=True)
    (project / "site" / "old.html").write_text("ancien site valide", encoding="utf-8")

    config = build_default_config()
    config.paths.project_root = "."
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

    original_rename = Path.rename

    def failing_rename(self, target):
        if ".building-" in self.name:
            raise OSError("simulated non-permission rename failure")
        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", failing_rename)

    report = build_site(config, config_path=config_path)

    assert report.success is False
    # The old site must survive intact — not silently deleted with
    # nothing to replace it.
    assert (project / "site").exists()
    assert (project / "site" / "old.html").read_text(encoding="utf-8") == "ancien site valide"


def test_site_builder_does_not_leak_partial_tei_when_a_later_post_fails(monkeypatch):
    """Second external audit finding: build/tei (the "Conserver TEI"
    output) sat outside the staging/swap protection given to the HTML
    site — a post that failed to convert after an earlier one succeeded
    left that earlier post's .xml sitting in build/tei despite the
    overall build failing. Confirmed exploitable before this fix."""
    project = RUNTIME_ROOT / f"tei_staging_partial_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier"\nslug: "premier"\ntype: "post"\ndate: "2026-01-01"\n---\n\n# Premier\n',
        encoding="utf-8",
    )
    (project / "content/posts/second.md").write_text(
        '---\ntitle: "Second"\nslug: "second"\ntype: "post"\ndate: "2026-01-02"\n---\n\n# Second\n',
        encoding="utf-8",
    )

    def flaky_convert(input_path, output_path, **_kwargs):
        if "second" in str(input_path):
            return MarkdownToTeiResult(
                source_file=Path(input_path),
                tei_file=Path(output_path),
                command=["pandoc"],
                success=False,
                message="echec pandoc simule",
                validation=TeiValidationResult(valid=False),
            )
        return _fake_convert(input_path, output_path, **_kwargs)

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.render.generate_tei_files = True

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", flaky_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is False
    assert not (project / "build/tei").exists()


def test_site_builder_does_not_leak_a_sidecar_xml_when_a_later_post_fails(monkeypatch):
    """Third finding from the second external audit: the permanent
    content/*.xml copy kept next to each Markdown source (independent of
    "Conserver TEI") was written immediately, per item, regardless of
    whether the overall build later failed — a successfully-converted
    post's sidecar .xml still landed in the content/ source directory
    even though the build as a whole never succeeded. Confirmed
    exploitable before this fix."""
    project = RUNTIME_ROOT / f"sidecar_xml_partial_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier"\nslug: "premier"\ntype: "post"\ndate: "2026-01-01"\n---\n\n# Premier\n',
        encoding="utf-8",
    )
    (project / "content/posts/second.md").write_text(
        '---\ntitle: "Second"\nslug: "second"\ntype: "post"\ndate: "2026-01-02"\n---\n\n# Second\n',
        encoding="utf-8",
    )

    def flaky_convert(input_path, output_path, **_kwargs):
        if "second" in str(input_path):
            return MarkdownToTeiResult(
                source_file=Path(input_path),
                tei_file=Path(output_path),
                command=["pandoc"],
                success=False,
                message="echec pandoc simule",
                validation=TeiValidationResult(valid=False),
            )
        return _fake_convert(input_path, output_path, **_kwargs)

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", flaky_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is False
    assert not (project / "content/posts/premier.xml").exists()
    assert not (project / "content/pages/accueil.xml").exists()


def test_site_builder_preserves_a_good_tei_dir_when_a_later_build_fails(monkeypatch):
    project = RUNTIME_ROOT / f"tei_staging_preserve_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier"\nslug: "premier"\ntype: "post"\ndate: "2026-01-01"\n---\n\n# Premier\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.render.generate_tei_files = True

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    first_report = build_site(config, config_path=config_path)
    assert first_report.success is True
    good_tei = (project / "build/tei/posts/premier.xml").read_text(encoding="utf-8")

    (project / "content/posts/second.md").write_text(
        '---\nslug: "second"\ntype: "post"\ndate: "2026-01-02"\n---\n\n# Sans titre\n',
        encoding="utf-8",
    )

    second_report = build_site(config, config_path=config_path)
    assert second_report.success is False

    assert (project / "build/tei/posts/premier.xml").read_text(encoding="utf-8") == good_tei


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


def _build_project_with_n_posts(name: str, count: int):
    project = RUNTIME_ROOT / f"{name}_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    for i in range(1, count + 1):
        (project / f"content/posts/billet-{i:02d}.md").write_text(
            f'---\ntitle: "Billet {i}"\nslug: "billet-{i}"\ntype: "post"\n'
            f'date: "2026-01-{i:02d}"\n---\n\n# Billet {i}\n',
            encoding="utf-8",
        )
    return project


def _config_for_pagination(project: Path, posts_per_page: int):
    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.blog.posts_per_page = posts_per_page
    return config


def _fake_convert(input_path, output_path, **_kwargs):
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


def test_archive_pagination_splits_posts_across_several_pages(monkeypatch):
    """"Billets par page" (config.blog.posts_per_page) was displayed in the
    UI but never applied — the archive always listed every post on a
    single page. 5 posts with posts_per_page=2 must produce 3 pages."""
    project = _build_project_with_n_posts("archive_pagination", 5)
    config = _config_for_pagination(project, posts_per_page=2)

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)
    assert report.success is True

    page1 = (project / "site/billets/index.html").read_text(encoding="utf-8")
    page2 = (project / "site/billets/page/2/index.html").read_text(encoding="utf-8")
    page3 = (project / "site/billets/page/3/index.html").read_text(encoding="utf-8")
    assert not (project / "site/billets/page/4/index.html").exists()

    # Most recent first (sort_descending_by_date, the default): billet-05,
    # billet-04 on page 1; billet-03, billet-02 on page 2; billet-01 alone
    # on page 3.
    assert "Billet 5" in page1 and "Billet 4" in page1
    assert "Billet 3" not in page1
    assert "Billet 3" in page2 and "Billet 2" in page2
    assert "Billet 5" not in page2
    assert "Billet 1" in page3
    assert "Billet 2" not in page3

    assert "Page 1 / 3" in page1
    assert "Page 2 / 3" in page2
    assert "Page 3 / 3" in page3

    # page 1 has no "previous" page; page 3 has no "next" page.
    assert "archive-pagination-prev archive-pagination-disabled" in page1
    assert 'href="page/2/index.html"' in page1
    assert 'href="../../index.html"' in page2  # page 2's "previous" is page 1
    assert 'href="../3/index.html"' in page2
    assert "archive-pagination-next archive-pagination-disabled" in page3


def test_archive_pagination_shows_everything_on_one_page_when_posts_per_page_is_zero(monkeypatch):
    project = _build_project_with_n_posts("archive_no_pagination", 5)
    config = _config_for_pagination(project, posts_per_page=0)

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)
    assert report.success is True

    assert not (project / "site/billets/page/2/index.html").exists()
    page1 = (project / "site/billets/index.html").read_text(encoding="utf-8")
    for i in range(1, 6):
        assert f"Billet {i}" in page1
    assert "archive-pagination" not in page1  # a single page needs no pager


def test_archive_pagination_urls_are_all_listed_in_the_sitemap(monkeypatch):
    project = _build_project_with_n_posts("archive_pagination_sitemap", 5)
    config = _config_for_pagination(project, posts_per_page=2)
    config.site.base_url = "https://example.org"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)
    assert report.success is True

    sitemap = (project / "site/sitemap.xml").read_text(encoding="utf-8")
    assert "<loc>https://example.org/billets/index.html</loc>" in sitemap
    assert "<loc>https://example.org/billets/page/2/index.html</loc>" in sitemap
    assert "<loc>https://example.org/billets/page/3/index.html</loc>" in sitemap


def test_a_post_with_no_incoming_link_anywhere_is_reported_orphan(monkeypatch):
    """The archive page normally links every post — with it disabled, and
    the home page not featuring recent posts either, a real post is
    generated but genuinely unreachable by browsing the site."""
    project = RUNTIME_ROOT / f"orphan_post_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier"\nslug: "premier"\ntype: "post"\ndate: "2026-01-01"\n---\n\n# Premier\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.home.mode = "page"
    config.blog.generate_archive_page = False

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert any("orphelines" in warning and "premier" in warning for warning in report.warnings)


def _project_with_stale_menu_link(name: str) -> Path:
    from bloggen.config.models import MenuLink

    project = RUNTIME_ROOT / f"{name}_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    return project


def test_broken_internal_menu_link_is_reported_as_a_warning_by_default(monkeypatch):
    from bloggen.config.models import MenuLink

    project = _project_with_stale_menu_link("link_checker_warning")
    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    # A menu link left pointing at a slug that no longer exists — e.g.
    # renamed without updating this link (the exact scenario the audit
    # flagged: no mechanism catches this).
    config.menus.top.append(
        MenuLink(label="Ancien lien", target="/billets/slug-renomme/index.html", target_type="internal")
    )

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert any("slug-renomme" in warning for warning in report.warnings)
    assert not any("slug-renomme" in error for error in report.errors)


def test_broken_internal_menu_link_fails_the_build_when_configured_to(monkeypatch):
    from bloggen.config.models import MenuLink

    project = _project_with_stale_menu_link("link_checker_fail")
    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.build.fail_on_broken_links = True
    config.menus.top.append(
        MenuLink(label="Ancien lien", target="/billets/slug-renomme/index.html", target_type="internal")
    )

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is False
    assert any("slug-renomme" in error for error in report.errors)


def test_broken_link_check_can_be_disabled(monkeypatch):
    from bloggen.config.models import MenuLink

    project = _project_with_stale_menu_link("link_checker_disabled")
    config = build_default_config()
    config.paths.project_root = "."
    config.paths.content_dir = "content"
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.build.check_broken_links = False
    config.menus.top.append(
        MenuLink(label="Ancien lien", target="/billets/slug-renomme/index.html", target_type="internal")
    )

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert not any("slug-renomme" in warning for warning in report.warnings)


def test_renaming_a_post_slug_generates_a_redirect_from_the_old_url(monkeypatch):
    """The scenario the audit flagged: renaming a slug just makes the old
    URL 404 forever, with no mechanism to redirect old bookmarks/backlinks
    to the new address. A slug edit does not rename the .md file itself
    (see content/writer.py), so the same file, rebuilt with a new slug,
    must produce a redirect stub at its old URL."""
    project = RUNTIME_ROOT / f"redirect_rename_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    post_path = project / "content/posts/premier.md"
    post_path.write_text(
        '---\ntitle: "Premier"\nslug: "ancien-slug"\ntype: "post"\ndate: "2026-04-23"\n---\n\n# Premier\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    first_report = build_site(config, config_path=config_path)
    assert first_report.success is True
    assert (project / "site/billets/ancien-slug/index.html").exists()
    assert not (project / "site/billets/nouveau-slug/index.html").exists()

    # Rename the slug — same file (premier.md), new URL.
    post_path.write_text(
        '---\ntitle: "Premier"\nslug: "nouveau-slug"\ntype: "post"\ndate: "2026-04-23"\n---\n\n# Premier\n',
        encoding="utf-8",
    )

    second_report = build_site(config, config_path=config_path)
    assert second_report.success is True

    # New URL has the real content; old URL now redirects to it.
    new_page = (project / "site/billets/nouveau-slug/index.html").read_text(encoding="utf-8")
    assert "Premier" in new_page

    redirect_stub = project / "site/billets/ancien-slug/index.html"
    assert redirect_stub.exists()
    redirect_html = redirect_stub.read_text(encoding="utf-8")
    assert 'meta http-equiv="refresh" content="0; url=../nouveau-slug/index.html"' in redirect_html
    assert 'name="robots" content="noindex"' in redirect_html

    assert any("Redirections générées" in warning for warning in second_report.warnings)

    # The history file persisted across the two builds.
    history_path = project / ".merope-redirects.json"
    assert history_path.exists()
    import json

    history = json.loads(history_path.read_text(encoding="utf-8"))
    assert history["content/posts/premier.md"] == [
        "/billets/ancien-slug/index.html",
        "/billets/nouveau-slug/index.html",
    ]


def test_redirect_generation_can_be_disabled(monkeypatch):
    project = RUNTIME_ROOT / f"redirect_disabled_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    post_path = project / "content/posts/premier.md"
    post_path.write_text(
        '---\ntitle: "Premier"\nslug: "ancien-slug"\ntype: "post"\ndate: "2026-04-23"\n---\n\n# Premier\n',
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.build.generate_redirects = False

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)

    build_site(config, config_path=config_path)

    post_path.write_text(
        '---\ntitle: "Premier"\nslug: "nouveau-slug"\ntype: "post"\ndate: "2026-04-23"\n---\n\n# Premier\n',
        encoding="utf-8",
    )
    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert not (project / "site/billets/ancien-slug/index.html").exists()
    assert not (project / ".merope-redirects.json").exists()


def test_commons_publishing_diagnostic_reports_non_conformant_tei_without_failing_the_build():
    """Real Pandoc conversion (not the TEI_SAMPLE fake used elsewhere in
    this file): its own generic TEI output does not conform to the
    Commons Publishing profile yet (see bloggen.tei.commons_publishing's
    module docstring) — the diagnostic must surface that as a warning
    without affecting report.success."""
    project = RUNTIME_ROOT / f"commons_publishing_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier"\nslug: "premier"\ntype: "post"\ndate: "2026-01-01"\n---\n\n'
        "# Premier\n\nUn paragraphe.\n\n## Une section\n\nUn autre paragraphe.\n",
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
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

    assert report.success is True
    assert any("Commons Publishing" in warning for warning in report.warnings)


def test_commons_publishing_diagnostic_can_be_disabled():
    project = RUNTIME_ROOT / f"commons_publishing_disabled_{uuid.uuid4().hex}"
    (project / "content/pages").mkdir(parents=True)
    (project / "content/posts").mkdir(parents=True)
    (project / "content/pages/accueil.md").write_text(
        '---\ntitle: "Accueil"\nslug: "accueil"\ntype: "page"\n---\n\n# Accueil\n',
        encoding="utf-8",
    )
    (project / "content/posts/premier.md").write_text(
        '---\ntitle: "Premier"\nslug: "premier"\ntype: "post"\ndate: "2026-01-01"\n---\n\n'
        "# Premier\n\nUn paragraphe.\n\n## Une section\n\nUn autre paragraphe.\n",
        encoding="utf-8",
    )

    config = build_default_config()
    config.paths.project_root = "."
    config.paths.pages_dir = "content/pages"
    config.paths.posts_dir = "content/posts"
    config.paths.assets_dir = "assets"
    config.paths.output_dir = "site"
    config.paths.tei_dir = "build/tei"
    config.home.source = "content/pages/accueil.md"
    config.render.validate_commons_publishing = False

    config_path = project / "config/site.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("{}", encoding="utf-8")

    report = build_site(config, config_path=config_path)

    assert report.success is True
    assert not any("Commons Publishing" in warning for warning in report.warnings)
