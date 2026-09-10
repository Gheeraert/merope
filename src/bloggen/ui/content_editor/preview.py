"""Optional HTML preview of the content being edited — on click or live
while typing.

Reuses ``bloggen.build.site_builder._build_single_item`` (the same
function the real "Générer le site" pipeline calls for every page/post)
against an isolated scratch directory, so the preview is pixel-faithful
to a real build — same pandoc → TEI → XSLT → lightbox/notes → template
pipeline — without ever writing into the project's real output
directory. Rendered in a native window via ``pywebview`` (optional
dependency: the feature disables itself gracefully when it isn't
installed, same pattern as the optional ``keyring`` import in
``publish/ftp_credentials.py``).

The preview window itself runs in a dedicated subprocess
(``bloggen.ui.preview_process``), not an in-process thread: pywebview
6.x requires its event loop to run on the process's actual main thread,
which the Tkinter editor's own main thread already occupies. "Aperçu en
direct" works without the editor ever talking to that subprocess again
after launching it — both sides agree on one fixed HTML path per
document, the editor keeps overwriting it, and the subprocess watches
its mtime and reloads on its own (see preview_process.py).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from tkinter import messagebox
from typing import Callable

from bloggen.build.assets import copy_project_assets
from bloggen.build.reports import BuildReport
from bloggen.build.site_builder import _build_single_item
from bloggen.config.models import ProjectConfig
from bloggen.content.assets import collect_linked_assets
from bloggen.content.loader import ContentItem
from bloggen.content.metadata import ContentMetadataError, build_content_metadata
from bloggen.content.writer import write_content_file
from bloggen.markdown.front_matter import parse_front_matter
from bloggen.markdown.normalizer import normalize_markdown_text
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.tei.pandoc_converter import PandocUnavailableError

try:
    import webview
except ImportError:  # pragma: no cover - exercised via the webview=None branch
    webview = None

# Debounce for "aperçu en direct": how long to wait after the last edit
# before regenerating, so a burst of keystrokes triggers one pandoc/XSLT
# pass instead of one per character.
_LIVE_PREVIEW_DEBOUNCE_MS = 900

# Config-provider signature: PreviewMixin doesn't own a ProjectConfig
# itself (only main_window's live form does), so window.py hands it a
# callable resolved lazily at preview time — same pattern already used by
# main_window._list_menu_link_targets / _resolve_assets_root for the same
# reason (the form can change at any time).
ConfigProvider = Callable[[], "ProjectConfig | None"]


class PreviewMixin:
    """Adds an optional on-click / live HTML preview window."""

    def _init_preview(self, get_config: ConfigProvider | None) -> None:
        self._preview_get_config = get_config or self._preview_config_unavailable
        self._preview_scratch_dir: Path | None = None
        self._preview_process: subprocess.Popen | None = None
        self._preview_process_path: Path | None = None
        self._preview_live_var = None  # set by window.py once the checkbox exists
        self._preview_after_id: str | None = None
        self._preview_stale = True
        self._preview_building = False
        self._preview_revision = 0
        self._preview_assets_synced = False

    # -- staleness tracking -------------------------------------------------

    def _mark_preview_stale(self, _event=None) -> None:
        self._preview_stale = True

    @staticmethod
    def _preview_config_unavailable() -> None:
        messagebox.showerror(
            "Aperçu HTML",
            "La configuration du projet n'est pas accessible depuis cet éditeur.",
        )
        return None

    # -- scratch directory ----------------------------------------------------

    def _preview_scratch(self) -> Path:
        if self._preview_scratch_dir is None:
            self._preview_scratch_dir = Path(tempfile.mkdtemp(prefix="bloggen-preview-"))
        return self._preview_scratch_dir

    def _sync_preview_static_assets(self, config: ProjectConfig) -> None:
        """Mirrors the real build's static/ folder into the scratch dir once
        per editor session, so the preview's CSS/JS resolve without ever
        touching the real output directory. Only runs if the site has
        already been generated at least once — otherwise the preview is
        shown unstyled rather than blocking on a missing directory.
        """
        scratch_static = self._preview_scratch() / "static"
        if scratch_static.exists():
            return
        real_output = (self.project_root / config.paths.output_dir).resolve()
        real_static = real_output / "static"
        if real_static.is_dir():
            shutil.copytree(real_static, scratch_static)

    def _sync_preview_project_assets(self, config: ProjectConfig) -> None:
        """Mirrors the real build's project-wide assets/ folder into the
        scratch dir once per editor session.

        ``_build_single_item`` rewrites image URLs on the assumption that
        ``copy_project_assets`` already ran, exactly as it does in the real
        "Générer le site" pipeline (``site_builder.py``, right before
        ``_generate_pages``/``_generate_posts``) — the preview must run the
        same step itself, since it calls ``_build_single_item`` directly
        without going through that pipeline. Skipping it left the rewritten
        `<img src>` pointing at files that were never copied into the
        scratch dir, so every image referenced from the shared assets
        folder rendered as a broken link in the preview.
        """
        if self._preview_assets_synced or not config.build.copy_assets:
            return
        copy_project_assets(self.project_root, config.paths.assets_dir, self._preview_scratch())
        self._preview_assets_synced = True

    # -- build ----------------------------------------------------------------

    def _build_preview_html(self) -> Path | None:
        if webview is None:
            messagebox.showerror(
                "Aperçu HTML",
                "La bibliothèque optionnelle « pywebview » n'est pas installée.\n"
                "Installez-la avec : pip install pywebview",
            )
            return None

        if not self.metadata.get("title") or not self.metadata.get("slug"):
            if self._edit_metadata() is None:
                return None

        config = self._preview_get_config()
        if config is None:
            return None

        kind = self.metadata.get("type") or self.current_kind or "page"
        directory = self.pages_dir if kind == "page" else self.posts_dir
        directory.mkdir(parents=True, exist_ok=True)

        self._renumber_footnotes()
        body = blocks_to_markdown(self.extract_blocks())

        # Written next to the real content files (not to a temp dir
        # elsewhere) so image paths written relative to the markdown file
        # keep resolving exactly as they would for the real, saved file.
        # Removed again in the ``finally`` below regardless of outcome, so
        # a real build never sees it.
        temp_path = directory / f".__preview__.{kind}.md"
        try:
            write_content_file(directory, temp_path.name, self.metadata, body)
            html_path = self._render_temp_content_file(temp_path, kind=kind, config=config)
        finally:
            temp_path.unlink(missing_ok=True)

        return html_path

    def _render_temp_content_file(self, temp_path: Path, *, kind: str, config: ProjectConfig) -> Path | None:
        raw_markdown = temp_path.read_text(encoding="utf-8")
        parsed = parse_front_matter(raw_markdown)
        normalized = normalize_markdown_text(
            parsed.body,
            google_docs_mode=(config.content.markdown_origin == "google_docs_export"),
        )
        try:
            item_metadata = build_content_metadata(
                front_matter=parsed.metadata,
                kind=kind,
                default_layout=(
                    config.content.default_page_layout
                    if kind == "page"
                    else config.content.default_post_layout
                ),
                source_path=str(temp_path),
            )
        except ContentMetadataError as exc:
            messagebox.showerror("Aperçu HTML", str(exc))
            return None

        linked_assets = collect_linked_assets(temp_path, normalized, project_root=self.project_root)
        item = ContentItem(
            source_path=temp_path,
            kind=kind,
            metadata=item_metadata,
            front_matter=parsed.metadata,
            raw_markdown=raw_markdown,
            normalized_markdown=normalized,
            linked_assets=linked_assets,
        )

        self._sync_preview_static_assets(config)
        self._sync_preview_project_assets(config)
        scratch = self._preview_scratch()

        if kind == "page":
            url = f"/{item_metadata.slug}/index.html"
            item_dir = scratch / item_metadata.slug
        else:
            archive_path = config.blog.archive_path.strip("/") or "billets"
            url = f"/{archive_path}/{item_metadata.slug}/index.html"
            item_dir = scratch / archive_path / item_metadata.slug
        tei_path = scratch / "tei" / f"{item_metadata.slug}.xml"

        # Every rebuild gets its own filename rather than overwriting a
        # fixed index.html: WebView2 caches a file:// URL by its exact
        # path, so reloading the same URL after the content changed on
        # disk silently keeps showing the old version (observed while
        # testing "aperçu en direct") — a query string to bust that cache
        # doesn't work either, WebView2 treats it as literally part of the
        # file path and fails with ERR_FILE_NOT_FOUND. Previous revisions
        # are swept up right before each new one is written.
        for stale in item_dir.glob("index.*.html"):
            stale.unlink(missing_ok=True)
        self._preview_revision += 1
        html_path = item_dir / f"index.{self._preview_revision}.html"

        report = BuildReport(success=True, output_dir=scratch, tei_dir=scratch / "tei")
        try:
            built = _build_single_item(
                item,
                config=config,
                project_root=self.project_root,
                output_root=scratch,
                html_path=html_path,
                tei_path=tei_path,
                url=url,
                report=report,
            )
        except PandocUnavailableError as exc:
            messagebox.showerror("Aperçu HTML", str(exc))
            return None

        if built is None:
            messagebox.showerror(
                "Aperçu HTML",
                "\n".join(report.errors) or "Échec de la génération de l'aperçu.",
            )
            return None

        # The pointer file is the one stable path across revisions: the
        # preview_process subprocess (spawned once, long-lived) watches it
        # to learn which actual (freshly-named) HTML file to load next.
        (item_dir / "_current.txt").write_text(str(html_path), encoding="utf-8")
        return html_path

    # -- window lifecycle -------------------------------------------------

    def _show_preview(self) -> None:
        if self._preview_building:
            return
        self._preview_building = True
        try:
            html_path = self._build_preview_html()
        finally:
            self._preview_building = False
        if html_path is None:
            return
        self._preview_stale = False
        self._open_preview_window(html_path)

    def _open_preview_window(self, html_path: Path) -> None:
        # The subprocess watches the pointer file's *contents* (see
        # preview_process.py and the "_current.txt" write above) and
        # reloads whenever it names a new revision file — as long as it's
        # still running and pointed at the same pointer, rebuilding is all
        # "aperçu en direct" needs, nothing to push here. A slug change
        # moves the target (page/post URL, hence the pointer's directory)
        # mid-session, which the running subprocess has no way to learn
        # about — restart it in that case.
        pointer_path = html_path.parent / "_current.txt"
        running = self._preview_process is not None and self._preview_process.poll() is None
        if running and self._preview_process_path == pointer_path:
            return
        if running:
            self._preview_process.terminate()
        self._preview_process = subprocess.Popen(
            [sys.executable, "-m", "bloggen.ui.preview_process", str(pointer_path)]
        )
        self._preview_process_path = pointer_path

    # -- live preview toggle ------------------------------------------------

    def _toggle_live_preview(self) -> None:
        if self._preview_live_var.get():
            self._show_preview()
            self._schedule_live_preview()
        else:
            self._cancel_live_preview()

    def _schedule_live_preview(self) -> None:
        self._cancel_live_preview()
        self._preview_after_id = self.after(_LIVE_PREVIEW_DEBOUNCE_MS, self._live_preview_tick)

    def _cancel_live_preview(self) -> None:
        if self._preview_after_id is not None:
            self.after_cancel(self._preview_after_id)
            self._preview_after_id = None

    def _live_preview_tick(self) -> None:
        if self._preview_live_var is None or not self._preview_live_var.get():
            return
        if self._preview_stale:
            self._show_preview()
        self._preview_after_id = self.after(_LIVE_PREVIEW_DEBOUNCE_MS, self._live_preview_tick)

    # -- teardown -------------------------------------------------------------

    def destroy(self) -> None:
        # See AutosaveMixin.destroy: reached both via _on_close_request and
        # any direct .destroy() call that bypasses it (tests, parent
        # teardown) — a pending live-preview callback must never fire
        # against a widget that no longer exists.
        self._close_preview()
        super().destroy()

    def _close_preview(self) -> None:
        self._cancel_live_preview()
        if self._preview_process is not None and self._preview_process.poll() is None:
            self._preview_process.terminate()
        self._preview_process = None
        self._preview_process_path = None
        if self._preview_scratch_dir is not None:
            shutil.rmtree(self._preview_scratch_dir, ignore_errors=True)
            self._preview_scratch_dir = None
        self._preview_assets_synced = False
