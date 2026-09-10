"""Headless tests for the content editor's optional HTML preview
(bloggen.ui.content_editor.preview.PreviewMixin), which reuses the real
build pipeline (_build_single_item) against a scratch directory instead
of the project's real output directory.

Follows the monkeypatched-pandoc pattern from test_end_to_end.py: real
pandoc isn't assumed to be on PATH in the test environment, so
convert_markdown_file_to_tei is replaced with a fake that writes a fixed
TEI fixture instead of actually invoking pandoc.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

import pytest

from bloggen.config.io import load_config
from bloggen.tei.pandoc_converter import MarkdownToTeiResult
from bloggen.tei.validator import TeiValidationResult
from bloggen.ui.content_editor import ContentEditorWindow

_TEI_SAMPLE = (
    '<TEI xmlns="http://www.tei-c.org/ns/1.0">'
    '<teiHeader><fileDesc><titleStmt><title>Test</title></titleStmt>'
    '<publicationStmt><p>p</p></publicationStmt><sourceDesc><p>s</p></sourceDesc></fileDesc></teiHeader>'
    '<text><body><div><head>Titre</head>'
    '<p>Contenu d’aperçu</p>'
    '</div></body></text>'
    '</TEI>'
)


def _fake_convert(input_path, output_path, **_kwargs):
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_TEI_SAMPLE, encoding="utf-8")
    return MarkdownToTeiResult(
        source_file=Path(input_path),
        tei_file=out,
        command=["pandoc"],
        success=True,
        message="ok",
        validation=TeiValidationResult(valid=True),
    )


@pytest.fixture(scope="module")
def root(tk_root):
    return tk_root


@pytest.fixture
def project(tmp_path_factory):
    target = tmp_path_factory.mktemp("preview_project_") / f"proj_{uuid.uuid4().hex}"
    shutil.copytree(
        Path("examples/minimal_project"),
        target,
        ignore=shutil.ignore_patterns("site", "build", "__pycache__"),
    )
    config_path = target / "config/site.json"
    config = load_config(config_path)
    return target, config


@pytest.fixture
def editor(root, project, monkeypatch):
    target_project, config = project
    monkeypatch.setattr("bloggen.build.site_builder.convert_markdown_file_to_tei", _fake_convert)
    # showerror/showinfo would otherwise open a real blocking native dialog
    # in this headless test session (see test_content_editor_unsaved_changes.py
    # for the same pattern).
    monkeypatch.setattr("bloggen.ui.content_editor.preview.messagebox.showerror", lambda *a, **k: None)
    # _build_preview_html only checks "is pywebview installed at all" before
    # doing any real build work — the window itself is opened by a separate
    # method (_show_preview/_open_preview_window) that these tests don't
    # exercise, so a bare sentinel is enough regardless of whether the
    # optional pywebview dependency is actually installed in this env.
    monkeypatch.setattr("bloggen.ui.content_editor.preview.webview", object())

    pages_dir = (target_project / config.paths.pages_dir).resolve()
    posts_dir = (target_project / config.paths.posts_dir).resolve()
    images_dir = target_project / "assets" / "images"

    window = ContentEditorWindow(
        root,
        pages_dir=pages_dir,
        posts_dir=posts_dir,
        images_dir=images_dir,
        slugify_mode="ascii",
        project_root=target_project,
        get_config=lambda: config,
    )
    yield window
    window.destroy()


def test_preview_renders_through_the_real_build_pipeline(editor):
    editor.text.insert("insert", "Contenu de test pour l'aperçu")
    editor.metadata = {"title": "Page d'aperçu", "slug": "page-apercu", "type": "page"}

    html_path = editor._build_preview_html()

    assert html_path is not None
    assert html_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert "Contenu d’aperçu" in html


def test_preview_leaves_no_temp_markdown_file_behind(editor):
    editor.text.insert("insert", "Autre contenu")
    editor.metadata = {"title": "Autre page", "slug": "autre-page", "type": "page"}

    editor._build_preview_html()

    leftovers = list(editor.pages_dir.glob(".__preview__*"))
    assert leftovers == []


def test_preview_never_writes_into_the_real_output_directory(editor, project):
    target_project, _config = project
    editor.text.insert("insert", "Contenu")
    editor.metadata = {"title": "Page", "slug": "une-page", "type": "page"}

    editor._build_preview_html()

    real_output = target_project / "site"
    assert not real_output.exists()


def test_preview_uses_current_css_not_a_stale_real_build(editor, project):
    # Regression test: the preview used to mirror whatever CSS/JS already
    # sat in the project's real output/static/ folder (left there by a
    # previous "Générer le site" run), instead of regenerating it from the
    # package's current bundled resources the way the real build itself
    # does (copy_theme_resources, called from site_builder.py right before
    # _generate_pages). A real build predating a CSS fix — or never run at
    # all — left "Aperçu en direct" silently stuck showing the old styling
    # (e.g. the recent .article-figure image/caption alignment fix)
    # regardless of how current the editor's own code was.
    target_project, _config = project
    stale_css_dir = target_project / "site" / "static" / "css"
    stale_css_dir.mkdir(parents=True, exist_ok=True)
    (stale_css_dir / "site.css").write_text("/* stale css from an old build */", encoding="utf-8")

    editor.text.insert("insert", "Contenu")
    editor.metadata = {"title": "Page", "slug": "page-css", "type": "page"}
    editor._build_preview_html()

    scratch_css = editor._preview_scratch() / "static" / "css" / "site.css"
    current_css = Path("src/bloggen/resources/css/site.css").read_text(encoding="utf-8")
    assert scratch_css.read_text(encoding="utf-8") == current_css


def test_preview_copies_shared_assets_so_images_resolve(editor, project):
    # Regression test: _build_single_item rewrites <img src> pointing into
    # the project's shared assets/ folder on the assumption that
    # copy_project_assets() already ran — true for the real "Générer le
    # site" pipeline (site_builder.py, right before _generate_pages), false
    # for the preview, which calls _build_single_item directly. Without
    # syncing assets/ into the scratch dir first, the rewritten src pointed
    # at a file that was never actually copied there.
    editor.text.insert("insert", "Contenu de test pour l'aperçu")
    editor.metadata = {"title": "Page d'aperçu", "slug": "page-apercu", "type": "page"}

    html_path = editor._build_preview_html()
    assert html_path is not None

    target_project, config = project
    source_image = target_project / config.paths.assets_dir / "images" / "exemple.jpg"
    scratch_image = editor._preview_scratch() / config.paths.assets_dir / "images" / "exemple.jpg"
    assert source_image.exists()
    assert scratch_image.exists(), "preview never synced the project's shared assets/ folder"


def test_preview_reports_content_metadata_errors(editor):
    editor.text.insert("insert", "Contenu")
    editor.metadata = {"title": "Page", "slug": "Slug Invalide !", "type": "page"}

    html_path = editor._build_preview_html()

    assert html_path is None
