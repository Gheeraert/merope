"""Fenetre d'observation autonome du prototype d'editeur Qt."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import QByteArray, QSettings, QTimer, Qt, QUrl
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QCloseEvent,
    QGuiApplication,
    QImageReader,
    QKeySequence,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bloggen.config.models import ProjectConfig
from bloggen.content.catalog import (
    ContentCatalogEntry,
    determine_content_kind,
    scan_content_catalog,
    validate_editor_metadata,
)
from bloggen.content.footnotes import (
    FootnoteDefinitions,
    footnote_definition_blocks,
    footnote_reference_counts,
    footnote_reference_order,
    plan_footnote_renumbering,
)
from bloggen.content.image_service import (
    copy_into_images_dir,
    crop_is_identity,
    edited_size,
    probe_image,
    write_cropped_copy,
)
from bloggen.content.versioning import (
    convert_content_file,
    purge_versions,
    versions_to_purge,
)
from bloggen.content.writer import default_filename, scan_existing_slugs
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_model import (
    BULLET_LIST,
    ORDERED_LIST,
    PARAGRAPH,
    TABLE,
    TABLE_CELL,
    TABLE_ROW,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedDocumentError,
    caption_block_for_selection,
    extract_blocks,
    inline_format_enabled,
    insert_footnote_reference,
    insert_blocks,
    populate_document,
    renumber_footnote_references,
)
from bloggen.ui.qt_editor.content_browser import ContentBrowser
from bloggen.ui.qt_editor.file_io import (
    apply_prepared_content,
    directory_base_url,
    prepare_content_document,
    save_content_document,
)
from bloggen.ui.qt_editor.formatting import (
    clear_formatting,
    set_alignment,
    set_blockquote,
    set_heading,
    set_link,
    set_list,
    set_paragraph,
    toggle_bold,
    toggle_italic,
    toggle_justify,
    toggle_strikethrough,
    toggle_superscript,
    toggle_underline,
)
from bloggen.ui.qt_editor.find_replace_dialog import FindReplaceDialog
from bloggen.ui.editor_recovery import (
    RecoveryDraft,
    clear_draft,
    load_draft,
    save_draft,
)
from bloggen.ui.qt_editor.footnote_editor import (
    FootnoteEditorDialog,
    footnote_runs_semantically_equal,
    validate_footnote_runs,
)
from bloggen.ui.qt_editor.footnote_panel import FootnotePanel
from bloggen.ui.qt_editor.footnote_store import (
    FootnoteStore,
    FootnoteStoreSnapshot,
)
from bloggen.ui.qt_editor.image_crop import validate_source_box
from bloggen.ui.qt_editor.image_crop_dialog import CropImageDialog
from bloggen.ui.qt_editor.image_dialog import ImageMetadataDialog
from bloggen.ui.qt_editor.image_selection import (
    ImageTarget,
    replace_merope_image,
    targeted_merope_image,
)
from bloggen.ui.qt_editor.ipc import QtEditorIpcBridge
from bloggen.ui.qt_editor.metadata_dialog import ContentMetadataDialog
from bloggen.ui.qt_editor.preview import (
    PreviewArtifact,
    PreviewBuildError,
    PreviewSnapshot,
    build_preview_artifact,
    launch_preview_process,
    pywebview_available,
    remove_preview_artifact,
)
from bloggen.ui.qt_editor.preview_startup import PreviewStartupMonitor
from bloggen.ui.qt_editor.recovery import (
    AUTOSAVE_INTERVAL_MS,
    build_recovery_draft,
    prepare_recovery_draft,
)
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor.toolbar_icons import toolbar_icon
from bloggen.ui.qt_editor.wrapping_toolbar import WrappingButtonRow, WrappingToolBar
from bloggen.ui.qt_editor.constants import (
    BOLD_PROPERTY,
    ITALIC_PROPERTY,
    STRIKETHROUGH_PROPERTY,
    SUPERSCRIPT_PROPERTY,
    UNDERLINE_PROPERTY,
)
from bloggen.ui.qt_editor_protocol import emit_event


@dataclass(frozen=True, slots=True)
class _RenumberSaveSnapshot:
    body_blocks: list[Block]
    store: FootnoteStoreSnapshot
    body_modified: bool
    cursor_position: int
    cursor_anchor: int


CONTENT_DOCK_WIDTH = 230
FOOTNOTE_DOCK_WIDTH = 230
DEFAULT_WINDOW_MAX_WIDTH = 1600
DEFAULT_WINDOW_MAX_HEIGHT = 1000
# Bump when docks are added/renamed so an old saved layout is ignored.
LAYOUT_STATE_VERSION = 1
_GEOMETRY_KEY = "fenetre/geometrie"
_STATE_KEY = "fenetre/panneaux"


def editor_layout_settings() -> QSettings:
    """Per-user INI file (not the registry) holding the editor's layout."""

    return QSettings(
        QSettings.Format.IniFormat,
        QSettings.Scope.UserScope,
        "Merope",
        "editeur-qt",
    )


def _run_for_new_bitmap(run: InlineRun, src: str) -> InlineRun:
    """Point an image at a new bitmap (crop, rotation, replacement).

    The display width is kept, but a stored height belonged to the former
    proportions and would distort the new picture, so it is dropped.
    """

    return replace(run, image_src=src, image_height=None)


class QtEditorWindow(QMainWindow):
    """Standalone editor limited to content the Qt adapter can preserve."""

    def __init__(
        self,
        markdown_path: Path | None = None,
        *,
        project_root: Path | None = None,
        initial_directory: Path | None = None,
        pages_dir: Path | None = None,
        posts_dir: Path | None = None,
        images_dir: Path | None = None,
        slugify_mode: str = "ascii",
        ipc: bool = False,
    ) -> None:
        super().__init__()
        self.current_path: Path | None = None
        self.current_kind: str | None = None
        self.metadata: dict[str, str] = {}
        self._clean_metadata: dict[str, str] = {}
        self._session_unsaved = False
        self.footnote_store = FootnoteStore(self)
        self.project_root = Path(project_root) if project_root is not None else None
        self.pages_dir = Path(pages_dir) if pages_dir is not None else None
        self.posts_dir = Path(posts_dir) if posts_dir is not None else None
        self.initial_directory = (
            Path(initial_directory)
            if initial_directory
            else self.pages_dir if self.pages_dir is not None else Path.cwd()
        )
        self.images_dir = Path(images_dir) if images_dir is not None else None
        self.slugify_mode = slugify_mode
        self.ipc = ipc
        self._pending_preview_request_id: int | None = None
        self._pending_preview_snapshots: dict[int, PreviewSnapshot] = {}
        self._preview_artifact: PreviewArtifact | None = None
        self._preview_process: subprocess.Popen | None = None
        self._preview_monitor: PreviewStartupMonitor | None = None
        self._preview_candidate_artifact: PreviewArtifact | None = None
        self._preview_candidate_process: subprocess.Popen | None = None
        self._preview_candidate_monitor: PreviewStartupMonitor | None = None
        self._find_replace_dialog: FindReplaceDialog | None = None
        self.ipc_bridge = QtEditorIpcBridge(enabled=ipc, parent=self)
        self.ipc_bridge.configReady.connect(self._on_preview_config_ready)
        self.ipc_bridge.configFailed.connect(self._on_preview_config_failed)
        self.ipc_bridge.protocolError.connect(self._on_preview_protocol_error)
        self.resize(920, 700)
        self.editor = MeropeTextEdit(self)
        self._update_external_paste_context()
        self.editor.pasteRefused.connect(self._show_paste_refused)
        self.editor.clipboardRefused.connect(self._show_clipboard_refused)
        self.editor.imageMetadataRequested.connect(self._edit_targeted_image)
        populate_document(self.editor.document(), [])
        self.editor.document().setModified(False)
        self._create_toolbar()
        self._create_content_browser()
        self._create_footnote_panel()
        self._add_panel_toggles()
        # Start with slim side panels; the text column gets the rest. The
        # user's own widths are restored later by ``restore_layout``.
        self.resizeDocks(
            [self.content_dock, self.footnote_dock],
            [CONTENT_DOCK_WIDTH, FOOTNOTE_DOCK_WIDTH],
            Qt.Orientation.Horizontal,
        )
        self._layout_settings: QSettings | None = None
        self.footnote_store.changed.connect(self._refresh_footnote_panel)
        self.footnote_store.modifiedChanged.connect(self._update_window_title)
        self.editor.footnoteActivated.connect(self.footnote_panel.select_note)
        self.editor.cursorPositionChanged.connect(self._update_image_action)
        self.editor.selectionChanged.connect(self._update_image_action)
        self.editor.document().modificationChanged.connect(self._update_window_title)
        if markdown_path is not None:
            self.load_markdown(markdown_path)
        self._offer_crash_recovery()
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(AUTOSAVE_INTERVAL_MS)
        self.autosave_timer.timeout.connect(self._autosave_tick)
        if self.project_root is not None:
            self.autosave_timer.start()
        self._update_window_title()
        self._update_image_action()
        self._update_project_actions()

    def load_markdown(self, path: Path) -> None:
        prepared = prepare_content_document(path)
        kind = determine_content_kind(
            prepared.path,
            prepared.metadata,
            pages_dir=self.pages_dir,
            posts_dir=self.posts_dir,
        )
        apply_prepared_content(prepared, self.editor.document())
        self.current_path = prepared.path
        self._update_external_paste_context()
        self.current_kind = kind
        self.metadata = dict(prepared.metadata)
        self._clean_metadata = dict(prepared.metadata)
        self._session_unsaved = False
        self.footnote_store.load(prepared.footnote_definitions)
        self._update_project_actions()
        self.content_browser.select_path(prepared.path)
        self._update_window_title()
        self._update_image_action()
        self._emit("opened", path=prepared.path)

    def open_document(self, path: Path) -> bool:
        if not self._confirm_unsaved_changes():
            return False
        try:
            self.load_markdown(path)
        except (OSError, ValueError) as exc:
            self._emit("open_refused", path=path, message=str(exc))
            QMessageBox.critical(
                self,
                "Ouverture impossible",
                f"Ce fichier n’a pas été ouvert et le document courant reste intact.\n\n{exc}",
            )
            return False
        self._clear_recovery_draft()
        return True

    def _save_with_confirmation(self) -> bool:
        response = QMessageBox.question(
            self,
            "Enregistrer",
            "Enregistrer les modifications ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if response != QMessageBox.StandardButton.Yes:
            return False
        return self.save_document()

    def save_document(self) -> bool:
        if self.current_path is None and not self._can_first_save:
            QMessageBox.warning(
                self,
                "Enregistrer",
                "Ce document n’est pas rattaché à un projet Mérope complet.",
            )
            return False
        if not self._ensure_valid_metadata_for_save():
            return False
        target_path = self.current_path
        if target_path is None:
            assert self.current_kind is not None
            directory = self.pages_dir if self.current_kind == "page" else self.posts_dir
            assert directory is not None
            target_path = directory / default_filename(
                self.current_kind,
                self.metadata["slug"],
                date=self.metadata.get("date"),
            )
            if target_path.exists():
                QMessageBox.critical(
                    self,
                    "Enregistrement impossible",
                    f"Le fichier cible existe déjà :\n{target_path}",
                )
                return False
        renumber_snapshot: _RenumberSaveSnapshot | None = None
        try:
            renumber_snapshot = self._renumber_footnotes_for_save()
            result = save_content_document(
                target_path,
                self.metadata,
                self.editor.document(),
                self.footnote_store.definitions,
            )
        except (OSError, ValueError) as exc:
            if renumber_snapshot is not None:
                self._restore_renumber_save_snapshot(renumber_snapshot)
            self._emit("error", message=f"Enregistrement impossible : {exc}")
            QMessageBox.critical(self, "Enregistrement impossible", str(exc))
            return False

        self.current_path = result.path
        self.editor.document().setBaseUrl(directory_base_url(result.path.parent))
        self._update_external_paste_context()
        if renumber_snapshot is not None:
            self.editor.document().clearUndoRedoStacks()
            self.editor.document().setModified(False)
        self.footnote_store.mark_clean()
        self._clean_metadata = dict(self.metadata)
        self._session_unsaved = False
        self._clear_recovery_draft()
        self.refresh_content_browser()
        self.content_browser.select_path(result.path)
        self._update_project_actions()
        self._update_window_title()
        self._emit("saved", path=result.path)
        self._offer_version_purge(result.archive)
        return True

    def _autosave_tick(self) -> None:
        """Persist only a crash-recovery draft, never the Markdown file."""

        if self.project_root is None or not self.document_has_unsaved_changes:
            return
        try:
            draft = build_recovery_draft(
                self.editor.document(),
                self.footnote_store.definitions,
                self.metadata,
                project_root=self.project_root,
                current_path=self.current_path,
                current_kind=self.current_kind,
            )
            save_draft(self.project_root, draft)
        except Exception as exc:  # noqa: BLE001 - recovery must be fail-safe
            print(f"Autosauvegarde de récupération impossible : {exc}", file=sys.stderr)

    def _offer_crash_recovery(self) -> bool:
        """Offer one shared Tk/Qt draft and apply it only after validation."""

        if self.project_root is None:
            return False
        draft = load_draft(self.project_root)
        if draft is None:
            return False
        answer = QMessageBox.question(
            self,
            "Récupération après incident",
            "Un brouillon non enregistré a été retrouvé, probablement après "
            "une fermeture inattendue. Le restaurer ?\n\n"
            "Choisissez Non pour l’ignorer et le supprimer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._clear_recovery_draft()
            return False
        try:
            self.restore_recovery_draft(draft)
        except Exception as exc:  # noqa: BLE001 - invalid drafts must not replace the UI
            QMessageBox.warning(
                self,
                "Récupération impossible",
                "Le brouillon n’a pas été restauré afin d’éviter une perte de "
                f"données. Le document courant reste intact.\n\n{exc}",
            )
            return False
        return True

    def restore_recovery_draft(self, draft: RecoveryDraft) -> None:
        """Apply one fully validated draft and leave it explicitly dirty."""

        if self.project_root is None:
            raise ValueError("La récupération nécessite la racine explicite du projet.")
        prepared = prepare_recovery_draft(self.project_root, draft)
        restored_kind = prepared.current_kind
        if restored_kind is not None and restored_kind not in {"page", "post"}:
            raise ValueError("Le brouillon contient un type de document invalide.")
        if prepared.current_path is not None:
            detected = determine_content_kind(
                prepared.current_path,
                prepared.metadata,
                pages_dir=self.pages_dir,
                posts_dir=self.posts_dir,
            )
            if (
                restored_kind is not None
                and detected is not None
                and restored_kind != detected
            ):
                raise ValueError("Le type du brouillon contredit son fichier d’origine.")
            restored_kind = detected or restored_kind
        document = self.editor.document()
        document.setBaseUrl(directory_base_url(prepared.resource_directory))
        populate_document(document, prepared.body_blocks)
        self.footnote_store.load(prepared.footnote_definitions)
        self.metadata = prepared.metadata
        self._clean_metadata = dict(prepared.metadata)
        self._session_unsaved = True
        self.current_path = prepared.current_path
        self._update_external_paste_context()
        self.current_kind = restored_kind
        self._update_project_actions()
        document.setModified(True)
        self._update_window_title()
        self._update_image_action()

    def _clear_recovery_draft(self) -> None:
        if self.project_root is not None:
            clear_draft(self.project_root)

    def _update_external_paste_context(self) -> None:
        if self.current_path is None or self.images_dir is None:
            self.editor.set_external_paste_context()
            return
        self.editor.set_external_paste_context(
            images_dir=self.images_dir,
            doc_dir=self.current_path.parent,
        )

    def show_reconstructed_markdown(self) -> None:
        try:
            blocks = extract_blocks(self.editor.document()) + footnote_definition_blocks(
                self.footnote_store.definitions
            )
            markdown = blocks_to_markdown(blocks)
        except UnsupportedDocumentError as exc:
            QMessageBox.critical(self, "Round-trip impossible", str(exc))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Markdown reconstruit - non enregistre")
        layout = QVBoxLayout(dialog)
        preview = QPlainTextEdit(dialog)
        preview.setReadOnly(True)
        preview.setPlainText(markdown)
        layout.addWidget(preview)
        dialog.resize(760, 520)
        dialog.exec()

    def _create_toolbar(self) -> None:
        self.toolbar = WrappingToolBar(self)
        # QMainWindow's menu-widget slot spans the full window above both
        # docks. Keeping the responsive strip there avoids forcing it into
        # the much narrower document column between Contenus and Notes.
        self.setMenuWidget(self.toolbar)
        self.setCentralWidget(self.editor)
        toolbar = self.toolbar

        self._add_action(
            toolbar, "Ouvrir", self._open_from_dialog, "Ctrl+O", icon_key="open"
        )
        self.save_action = self._add_action(
            toolbar,
            "Enregistrer",
            self._save_with_confirmation,
            "Ctrl+S",
            icon_key="save",
        )
        self.save_action.setEnabled(False)
        self.metadata_action = self._add_action(
            toolbar,
            "Métadonnées...",
            self._edit_metadata_from_dialog,
            icon_key="metadata",
        )
        self.preview_action = self._add_action(
            toolbar,
            "Aperçu HTML",
            self._request_html_preview,
            icon_key="preview",
        )
        toolbar.add_separator()
        self._add_action(
            toolbar,
            "Annuler",
            self.editor.undo,
            shortcuts=["Ctrl+Z"],
            icon_key="undo",
        )
        self._add_action(
            toolbar,
            "Retablir",
            self.editor.redo,
            shortcuts=["Ctrl+Y", "Ctrl+Shift+Z"],
            icon_key="redo",
            tooltip="Rétablir — Ctrl+Y / Ctrl+Maj+Z",
        )
        self._add_action(
            toolbar,
            "Couper",
            self.editor.cut,
            "Ctrl+X",
            icon_key="cut",
        )
        self._add_action(
            toolbar,
            "Copier",
            self.editor.copy,
            "Ctrl+C",
            icon_key="copy",
        )
        self._add_action(
            toolbar,
            "Coller",
            self.editor.paste,
            "Ctrl+V",
            icon_key="paste",
        )
        self._add_action(
            toolbar,
            "Coller en texte brut",
            lambda: self.editor.paste_plain_text(),
            "Ctrl+Shift+V",
            icon_key="plain_paste",
            tooltip="Coller en texte brut — Ctrl+Maj+V",
        )
        self._add_action(
            toolbar,
            "Effacer la mise en forme",
            lambda: clear_formatting(self.editor),
            "Ctrl+Shift+Space",
            icon_key="clear_format",
            tooltip="Effacer la mise en forme — Ctrl+Maj+Espace",
        )
        toolbar.add_separator()
        nbsp_action = self._add_action(
            toolbar,
            "Espace insécable",
            self.editor.insert_nbsp,
            icon_key="nbsp",
            tooltip="Espace insécable — Ctrl+Espace / Alt+Espace",
        )
        nbsp_action.setShortcuts(
            [QKeySequence("Ctrl+Space"), QKeySequence("Alt+Space")]
        )
        self.bold_action = self._add_action(
            toolbar,
            "Gras",
            lambda: toggle_bold(self.editor),
            shortcuts=["Ctrl+G", "Ctrl+B"],
            icon_key="bold",
            tooltip="Gras — Ctrl+G / Ctrl+B",
            checkable=True,
        )
        self.italic_action = self._add_action(
            toolbar,
            "Italique",
            lambda: toggle_italic(self.editor),
            "Ctrl+I",
            icon_key="italic",
            checkable=True,
        )
        self.underline_action = self._add_action(
            toolbar,
            "Souligné",
            lambda: toggle_underline(self.editor),
            "Ctrl+U",
            icon_key="underline",
            checkable=True,
        )
        self.strike_action = self._add_action(
            toolbar,
            "Barre",
            lambda: toggle_strikethrough(self.editor),
            "Ctrl+Shift+S",
            icon_key="strike",
            tooltip="Barré — Ctrl+Maj+S",
            checkable=True,
        )
        self.superscript_action = self._add_action(
            toolbar,
            "Exposant",
            lambda: toggle_superscript(self.editor),
            "Ctrl+Shift+=",
            icon_key="superscript",
            tooltip="Exposant — Ctrl+Maj+=",
            checkable=True,
        )
        self._add_action(
            toolbar, "Lien", self._prompt_for_link, "Ctrl+K", icon_key="link"
        )
        toolbar.add_separator()

        self._add_action(
            toolbar,
            "Insérer une note...",
            self._insert_footnote_from_dialog,
            icon_key="note",
        )
        self._add_action(
            toolbar,
            "Renuméroter les notes",
            self.save_document,
            icon_key="renumber",
        )
        self._add_action(
            toolbar,
            "Insérer une image...",
            self._insert_image_from_dialog,
            icon_key="image",
        )
        self.image_action = self._add_action(
            toolbar,
            "Image...",
            self._edit_targeted_image,
            icon_key="image_edit",
        )
        self.image_action.setEnabled(False)
        self.replace_image_action = self._add_action(
            toolbar,
            "Remplacer l’image...",
            self._replace_image_from_dialog,
            icon_key="image_replace",
        )
        self.replace_image_action.setEnabled(False)
        self.crop_image_action = self._add_action(
            toolbar,
            "Recadrer...",
            self._crop_image_from_dialog,
            icon_key="crop",
        )
        self.crop_image_action.setEnabled(False)
        toolbar.add_separator()

        block_group = QActionGroup(self)
        for label, icon_key, callback in [
            ("Paragraphe", "paragraph", lambda: set_paragraph(self.editor)),
            ("H1", "h1", lambda: set_heading(self.editor, 1)),
            ("H2", "h2", lambda: set_heading(self.editor, 2)),
            ("H3", "h3", lambda: set_heading(self.editor, 3)),
            ("H4", "h4", lambda: set_heading(self.editor, 4)),
            ("Citation", "quote", lambda: set_blockquote(self.editor)),
        ]:
            action = self._add_action(
                toolbar, label, callback, icon_key=icon_key, checkable=True
            )
            block_group.addAction(action)

        toolbar.add_separator()
        self._add_action(
            toolbar,
            "Liste a puces",
            lambda: set_list(self.editor, BULLET_LIST),
            icon_key="bullets",
        )
        self._add_action(
            toolbar,
            "Liste numerotee",
            lambda: set_list(self.editor, ORDERED_LIST),
            icon_key="numbered",
        )
        self._add_action(
            toolbar, "Tableau...", self._insert_table_from_dialog, icon_key="table"
        )
        toolbar.add_separator()
        for label, alignment, icon_key in [
            ("Gauche", "left", "left"),
            ("Centre", "center", "center"),
            ("Droite", "right", "right"),
            ("Justifie", "justify", "justify"),
        ]:
            self._add_action(
                toolbar,
                label,
                lambda checked=False, value=alignment: set_alignment(self.editor, value),
                icon_key=icon_key,
            )
        self._add_action(
            toolbar,
            "Justifier gauche/plein",
            lambda: toggle_justify(self.editor),
            "Alt+J",
            icon_key="justify",
        )
        toolbar.add_separator()
        self._add_action(
            toolbar, "Rechercher", self._show_find_dialog, "Ctrl+F", icon_key="find"
        )
        self._add_action(
            toolbar,
            "Remplacer",
            self._show_replace_dialog,
            "Ctrl+H",
            icon_key="replace",
        )
        self._add_action(
            toolbar,
            "Typographie",
            self.editor.apply_typography_to_selection,
            icon_key="typography",
        )
        self._add_action(
            toolbar,
            "Voir Markdown",
            self.show_reconstructed_markdown,
            icon_key="markdown",
        )
        self.editor.cursorPositionChanged.connect(self._sync_inline_format_actions)
        self.editor.selectionChanged.connect(self._sync_inline_format_actions)
        self.editor.document().contentsChanged.connect(self._sync_inline_format_actions)
        self._sync_inline_format_actions()

    def _sync_inline_format_actions(self) -> None:
        char_format = self.editor.textCursor().charFormat()
        for action, property_id in (
            (self.bold_action, BOLD_PROPERTY),
            (self.italic_action, ITALIC_PROPERTY),
            (self.underline_action, UNDERLINE_PROPERTY),
            (self.strike_action, STRIKETHROUGH_PROPERTY),
            (self.superscript_action, SUPERSCRIPT_PROPERTY),
        ):
            action.setChecked(inline_format_enabled(char_format, property_id))

    def _show_find_dialog(self) -> None:
        self._open_find_replace_dialog(show_replace=False)

    def _show_replace_dialog(self) -> None:
        self._open_find_replace_dialog(show_replace=True)

    def _open_find_replace_dialog(self, *, show_replace: bool) -> None:
        dialog = self._find_replace_dialog
        if dialog is None:
            dialog = FindReplaceDialog(
                self.editor,
                self,
                show_replace=show_replace,
            )
            dialog.destroyed.connect(self._clear_find_replace_dialog)
            self._find_replace_dialog = dialog
        else:
            dialog.set_replace_visible(show_replace)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.focus_search()

    def _clear_find_replace_dialog(self, *_args) -> None:
        self._find_replace_dialog = None

    def _create_content_browser(self) -> None:
        self.content_dock = QDockWidget("Contenus", self)
        self.content_dock.setObjectName("meropeContentDock")
        self.content_browser = ContentBrowser(self.content_dock)
        self.content_browser.newPageRequested.connect(lambda: self.new_document("page"))
        self.content_browser.newPostRequested.connect(lambda: self.new_document("post"))
        self.content_browser.openRequested.connect(self._open_selected_content)
        self.content_browser.importRequested.connect(self._import_from_dialog)
        self.content_browser.convertRequested.connect(self._convert_selected_content)
        self.content_browser.deleteRequested.connect(self._delete_selected_content)
        self.content_browser.refreshRequested.connect(self.refresh_content_browser)
        self.content_dock.setWidget(self.content_browser)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.content_dock)
        self.refresh_content_browser()

    def _create_footnote_panel(self) -> None:
        self.footnote_dock = QDockWidget("Notes", self)
        self.footnote_dock.setObjectName("meropeFootnoteDock")
        container = QWidget(self.footnote_dock)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        self.footnote_panel = FootnotePanel(container)
        layout.addWidget(self.footnote_panel)
        buttons = WrappingButtonRow(container)
        self.edit_footnote_button = QPushButton("Modifier...", buttons)
        self.delete_footnote_button = QPushButton("Supprimer...", buttons)
        self.edit_footnote_button.clicked.connect(self._edit_selected_footnote)
        self.delete_footnote_button.clicked.connect(self._delete_selected_footnote)
        buttons.add_button(self.edit_footnote_button)
        buttons.add_button(self.delete_footnote_button)
        layout.addWidget(buttons)
        self.footnote_panel.noteSelected.connect(self._update_footnote_actions)
        self.footnote_dock.setWidget(container)
        self.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea,
            self.footnote_dock,
        )
        self.footnote_panel.set_definitions(self.footnote_store.definitions)
        self._update_footnote_actions()

    def _add_panel_toggles(self) -> None:
        """Always offer a way back to a closed panel.

        The action strip is not a QToolBar, so once both docks are closed no
        title bar remains for Qt's native right-click menu; and the layout is
        remembered between sessions.
        """

        self.toolbar.add_separator()
        self.panel_actions: dict[str, QAction] = {}
        for key, dock, label, shortcut in (
            ("contents", self.content_dock, "Panneau Contenus", "F8"),
            ("notes", self.footnote_dock, "Panneau Notes", "F9"),
        ):
            action = dock.toggleViewAction()
            action.setIcon(toolbar_icon(self, f"panel_{key}"))
            action.setText(label)
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            tooltip = f"Afficher ou masquer le {label.lower()} — {shortcut}"
            action.setToolTip(tooltip)
            action.setStatusTip(tooltip)
            self.toolbar.add_action(action)
            self.panel_actions[key] = action

    @property
    def footnote_definitions(self) -> FootnoteDefinitions:
        """Compatibility view of the canonical session store."""

        return self.footnote_store.definitions

    @property
    def document_has_unsaved_changes(self) -> bool:
        return (
            self.editor.document().isModified()
            or self.footnote_store.modified
            or self.metadata_modified
            or self._session_unsaved
        )

    @property
    def metadata_modified(self) -> bool:
        return self.metadata != self._clean_metadata

    @property
    def project_workflow_available(self) -> bool:
        return self.pages_dir is not None and self.posts_dir is not None

    @property
    def _can_first_save(self) -> bool:
        return self.project_workflow_available and self.current_kind in {"page", "post"}

    def _update_project_actions(self) -> None:
        available = self.project_workflow_available
        self.content_browser.set_project_enabled(available)
        self.save_action.setEnabled(self.current_path is not None or self._can_first_save)
        self.metadata_action.setEnabled(self.current_kind in {"page", "post"})

    def refresh_content_browser(self) -> list[ContentCatalogEntry]:
        """Rescan project files without ever reloading the current document."""

        if not self.project_workflow_available:
            if hasattr(self, "content_browser"):
                self.content_browser.set_entries([])
            return []
        assert self.pages_dir is not None and self.posts_dir is not None
        entries = scan_content_catalog(self.pages_dir, self.posts_dir)
        if hasattr(self, "content_browser"):
            self.content_browser.set_entries(entries)
            self.content_browser.select_path(self.current_path)
        return entries

    def new_document(self, kind: str) -> bool:
        if kind not in {"page", "post"}:
            raise ValueError("Type de contenu inconnu.")
        if not self.project_workflow_available:
            QMessageBox.warning(
                self,
                "Nouveau contenu",
                "Les dossiers pages et billets ne sont pas configurés.",
            )
            return False
        if not self._confirm_unsaved_changes():
            return False
        self._reset_session(kind)
        self._clear_recovery_draft()
        return True

    def _reset_session(self, kind: str) -> None:
        populate_document(self.editor.document(), [])
        self.editor.document().setBaseUrl(QUrl())
        self.editor.document().clearUndoRedoStacks()
        self.editor.document().setModified(False)
        self.footnote_store.load({})
        self.metadata = {}
        self._clean_metadata = {}
        self._session_unsaved = False
        self.current_kind = kind
        self.current_path = None
        self._update_external_paste_context()
        self._update_project_actions()
        self.content_browser.select_path(None)
        self._refresh_footnote_panel()
        self._update_window_title()
        self._update_image_action()

    def _existing_slugs(self) -> set[str]:
        if not self.project_workflow_available:
            return set()
        assert self.pages_dir is not None and self.posts_dir is not None
        return scan_existing_slugs(self.pages_dir, self.posts_dir)

    def _edit_metadata_from_dialog(self) -> bool:
        if self.current_kind not in {"page", "post"}:
            QMessageBox.warning(
                self,
                "Métadonnées",
                "Impossible de déterminer le type de ce contenu.",
            )
            return False
        dialog = ContentMetadataDialog(
            kind=self.current_kind,
            initial=self.metadata,
            existing_slugs=self._existing_slugs(),
            slugify_mode=self.slugify_mode,
            own_slug=(
                self._clean_metadata.get("slug")
                if self.current_path is not None
                else None
            ),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        result = dialog.result_metadata()
        if result is None or result == self.metadata:
            return False
        self.metadata = result
        self._update_window_title()
        return True

    def _validated_metadata(self) -> dict[str, str]:
        if self.current_kind not in {"page", "post"}:
            raise ValueError("Impossible de déterminer le type de ce contenu.")
        own_slug = self._clean_metadata.get("slug") if self.current_path is not None else None
        return validate_editor_metadata(
            self.metadata,
            self.current_kind,
            existing_slugs=self._existing_slugs(),
            own_slug=own_slug,
        )

    def _ensure_valid_metadata_for_save(self) -> bool:
        # A manually opened standalone legacy file may have no type and no
        # project folders from which to infer one. Keep the established
        # ability to save that already-open file; project workflows are
        # always validated strictly below.
        if self.current_path is not None and self.current_kind is None:
            return True
        try:
            validated = self._validated_metadata()
        except ValueError:
            if not self._edit_metadata_from_dialog():
                return False
            try:
                validated = self._validated_metadata()
            except ValueError as exc:
                QMessageBox.warning(self, "Métadonnées", str(exc))
                return False
        if validated != self.metadata:
            self.metadata = validated
            self._update_window_title()
        return True

    def import_markdown(self, path: Path) -> bool:
        """Validate an external file fully, then install it as an unsaved session."""

        if not self.project_workflow_available:
            raise ValueError("Le contexte projet est indisponible pour importer un contenu.")
        prepared = prepare_content_document(path)
        declared = prepared.metadata.get("type", "").strip().lower()
        kind = declared if declared in {"page", "post"} else "page"
        if not self._confirm_unsaved_changes():
            return False
        document = self.editor.document()
        document.setBaseUrl(directory_base_url(Path(path).parent))
        populate_document(document, prepared.body_blocks)
        document.clearUndoRedoStacks()
        document.setModified(False)
        self.footnote_store.load(prepared.footnote_definitions)
        self.metadata = dict(prepared.metadata)
        self.metadata.setdefault("type", kind)
        self._clean_metadata = dict(self.metadata)
        self._session_unsaved = True
        self.current_kind = kind
        self.current_path = None
        self._update_external_paste_context()
        self._update_project_actions()
        self.content_browser.select_path(None)
        self._refresh_footnote_panel()
        self._update_window_title()
        self._update_image_action()
        self._clear_recovery_draft()
        return True

    def _import_from_dialog(self) -> None:
        if not self.project_workflow_available:
            QMessageBox.warning(self, "Importer", "Le contexte projet est indisponible.")
            return
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Importer un fichier Markdown",
            str(self.initial_directory),
            "Markdown (*.md *.markdown);;Tous les fichiers (*)",
        )
        if not path:
            return
        try:
            self.import_markdown(Path(path))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Import impossible", str(exc))

    def _open_selected_content(self) -> None:
        entry = self.content_browser.selected_entry()
        if entry is not None:
            self.open_document(entry.path)

    def _conversion_guard_for_current(self, path: Path) -> bool:
        if self.current_path is None or self.current_path.resolve() != Path(path).resolve():
            return True
        if not self.document_has_unsaved_changes:
            return True
        answer = QMessageBox.warning(
            self,
            "Modifications non enregistrées",
            "Enregistrer les modifications avant de convertir ce contenu ?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.save_document()
        try:
            self.load_markdown(path)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Conversion impossible", str(exc))
            return False
        self._clear_recovery_draft()
        return True

    def convert_content_entry(
        self,
        entry: ContentCatalogEntry,
        *,
        date_value: str | None = None,
    ) -> Path:
        if not self.project_workflow_available:
            raise ValueError("Le contexte projet est indisponible.")
        if not self._conversion_guard_for_current(entry.path):
            raise RuntimeError("Conversion annulée.")
        prepared = prepare_content_document(entry.path)
        source_kind = determine_content_kind(
            prepared.path,
            prepared.metadata,
            pages_dir=self.pages_dir,
            posts_dir=self.posts_dir,
        )
        if source_kind != entry.kind:
            raise ValueError("Le type du fichier ne correspond pas à l’entrée sélectionnée.")
        new_kind = "post" if entry.kind == "page" else "page"
        converted_metadata = dict(prepared.metadata)
        converted_metadata["type"] = new_kind
        if new_kind == "post":
            converted_metadata["date"] = (date_value or "").strip()
        else:
            converted_metadata.pop("date", None)
        converted_metadata = validate_editor_metadata(
            converted_metadata,
            new_kind,
            existing_slugs=self._existing_slugs(),
            own_slug=prepared.metadata.get("slug"),
        )
        target_dir = self.posts_dir if new_kind == "post" else self.pages_dir
        assert target_dir is not None
        target = target_dir / default_filename(
            new_kind,
            converted_metadata["slug"],
            date=converted_metadata.get("date"),
        )
        if target.resolve() != entry.path.resolve() and target.exists():
            raise FileExistsError(f"Le fichier cible existe déjà : {target}")
        conversion = convert_content_file(
            entry.path,
            new_kind=new_kind,
            target_dir=target_dir,
            date_value=converted_metadata.get("date"),
            metadata=converted_metadata,
            body=prepared.markdown_body,
        )
        if self.current_path is not None and self.current_path.resolve() == entry.path.resolve():
            self.load_markdown(conversion.path)
            self._clear_recovery_draft()
        self.refresh_content_browser()
        self.content_browser.select_path(conversion.path)
        return conversion.path

    def _convert_selected_content(self) -> None:
        entry = self.content_browser.selected_entry()
        if entry is None:
            QMessageBox.information(self, "Convertir", "Sélectionnez un contenu.")
            return
        date_value: str | None = None
        if entry.kind == "page":
            initial = date.today().isoformat()
            try:
                initial = prepare_content_document(entry.path).metadata.get("date", "") or initial
            except (OSError, ValueError):
                pass
            value, accepted = QInputDialog.getText(
                self,
                "Convertir en billet",
                "Date de publication (AAAA-MM-JJ) :",
                text=initial,
            )
            if not accepted:
                return
            date_value = value.strip()
        new_label = "billet" if entry.kind == "page" else "page"
        if QMessageBox.question(
            self,
            "Convertir",
            f"Transformer ce contenu en {new_label} ?\n\n"
            "Le fichier sera déplacé et son URL pourra changer. Les liens existants "
            "ne seront pas réécrits.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.convert_content_entry(entry, date_value=date_value)
        except RuntimeError as exc:
            if str(exc) != "Conversion annulée.":
                QMessageBox.critical(self, "Conversion impossible", str(exc))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Conversion impossible", str(exc))

    def delete_content_entry(self, entry: ContentCatalogEntry) -> bool:
        is_current = (
            self.current_path is not None
            and self.current_path.resolve() == entry.path.resolve()
        )
        if is_current and not self._confirm_unsaved_changes():
            return False
        entry.path.unlink(missing_ok=True)
        if is_current:
            self._reset_session(entry.kind)
            self._clear_recovery_draft()
        self.refresh_content_browser()
        return True

    def _delete_selected_content(self) -> None:
        entry = self.content_browser.selected_entry()
        if entry is None:
            QMessageBox.information(self, "Supprimer", "Sélectionnez un contenu.")
            return
        if QMessageBox.question(
            self,
            "Supprimer",
            f"Supprimer définitivement {entry.path.name} ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.delete_content_entry(entry)
        except OSError as exc:
            QMessageBox.critical(self, "Suppression impossible", str(exc))

    def _refresh_footnote_panel(self) -> None:
        self.footnote_panel.set_definitions(self.footnote_store.definitions)
        self._update_footnote_actions()

    def _update_footnote_actions(self, _note_id: str | None = None) -> None:
        note_id = self.footnote_panel.selected_note_id
        runs = self.footnote_store.definition(note_id) if note_id is not None else None
        self.delete_footnote_button.setEnabled(runs is not None)
        self.edit_footnote_button.setEnabled(runs is not None)
        self.edit_footnote_button.setToolTip("")

    def insert_footnote(self, content: str | list[InlineRun]) -> str:
        """Register validated rich runs and insert their atomic body reference."""

        runs = [InlineRun(text=content)] if isinstance(content, str) else content
        runs = validate_footnote_runs(runs)
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            raise ValueError(
                "Désélectionnez le texte avant d’insérer un appel de note."
            )
        store_snapshot = self.footnote_store.snapshot()
        note_id = self.footnote_store.register(runs)
        try:
            cursor = insert_footnote_reference(cursor, note_id)
        except Exception:
            self.footnote_store.restore(store_snapshot)
            raise
        self.editor.setTextCursor(cursor)
        self.footnote_panel.select_note(note_id)
        return note_id

    def insert_table(self, rows: int, columns: int) -> Block:
        """Insert a canonical table followed by an ordinary editing paragraph."""

        if rows < 2 or columns < 1:
            raise ValueError("Un tableau exige au moins 2 lignes et 1 colonne.")
        table_rows = []
        for row_index in range(rows):
            cells = [
                Block(
                    kind=TABLE_CELL,
                    runs=[
                        InlineRun(
                            text=f"Colonne {column_index + 1}"
                            if row_index == 0
                            else ""
                        )
                    ],
                )
                for column_index in range(columns)
            ]
            table_rows.append(Block(kind=TABLE_ROW, children=cells))
        table = Block(kind=TABLE, children=table_rows)
        cursor = insert_blocks(
            self.editor.textCursor(),
            [table, Block(kind=PARAGRAPH, runs=[InlineRun(text="")])],
        )
        self.editor.setTextCursor(cursor)
        return table

    def _refuse_in_caption(self, what: str) -> bool:
        """Warn before any dialog when the caret sits in an image caption."""

        if caption_block_for_selection(self.editor.textCursor()) is None:
            return False
        QMessageBox.warning(
            self,
            "Insertion impossible",
            f"Une légende d’image ne peut contenir que du texte : placez le "
            f"curseur hors de la légende pour insérer {what}.",
        )
        return True

    def _insert_table_from_dialog(self) -> bool:
        if self._refuse_in_caption("un tableau"):
            return False
        rows, accepted = QInputDialog.getInt(
            self,
            "Tableau",
            "Nombre de lignes (en-tête inclus) :",
            2,
            2,
            1000,
        )
        if not accepted:
            return False
        columns, accepted = QInputDialog.getInt(
            self,
            "Tableau",
            "Nombre de colonnes :",
            2,
            1,
            100,
        )
        if not accepted:
            return False
        try:
            self.insert_table(rows, columns)
        except (ValueError, UnsupportedDocumentError) as exc:
            QMessageBox.warning(self, "Insertion impossible", str(exc))
            return False
        return True

    def _insert_footnote_from_dialog(self) -> bool:
        if self._refuse_in_caption("un appel de note"):
            return False
        if self.editor.textCursor().hasSelection():
            QMessageBox.warning(
                self,
                "Insertion impossible",
                "Désélectionnez le texte avant d’insérer un appel de note.",
            )
            return False
        dialog = FootnoteEditorDialog(
            [],
            self,
            title="Insérer une note de bas de page",
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        try:
            self.insert_footnote(dialog.result_runs())
        except (ValueError, UnsupportedDocumentError) as exc:
            QMessageBox.warning(self, "Insertion impossible", str(exc))
            return False
        return True

    def edit_footnote_definition(
        self,
        note_id: str,
        content: str | list[InlineRun],
    ) -> bool:
        runs = self.footnote_store.definition(note_id)
        if runs is None:
            return False
        updated_runs = (
            [InlineRun(text=content)] if isinstance(content, str) else content
        )
        updated_runs = validate_footnote_runs(updated_runs)
        if footnote_runs_semantically_equal(runs, updated_runs):
            return False
        return self.footnote_store.update(note_id, updated_runs)

    def _edit_selected_footnote(self) -> bool:
        note_id = self.footnote_panel.selected_note_id
        if note_id is None:
            return False
        runs = self.footnote_store.definition(note_id)
        if runs is None:
            return False
        try:
            dialog = FootnoteEditorDialog(
                runs,
                self,
                title=f"Modifier la note [{note_id}]",
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Modification impossible", str(exc))
            return False
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        return self.edit_footnote_definition(note_id, dialog.result_runs())

    def delete_footnote_definition(self, note_id: str) -> bool:
        """Delete only the definition; body references deliberately remain."""

        return self.footnote_store.remove(note_id)

    def _delete_selected_footnote(self) -> bool:
        note_id = self.footnote_panel.selected_note_id
        if note_id is None or self.footnote_store.definition(note_id) is None:
            return False
        count = footnote_reference_counts(extract_blocks(self.editor.document())).get(
            note_id, 0
        )
        if count:
            message = (
                f"La définition [{note_id}] possède {count} appel(s) dans le corps.\n\n"
                "Supprimer seulement la définition et conserver ces appels ?"
            )
        else:
            message = f"Supprimer la définition orpheline [{note_id}] ?"
        answer = QMessageBox.question(
            self,
            "Supprimer la définition",
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        return self.delete_footnote_definition(note_id)

    def _prompt_for_link(self) -> None:
        href, accepted = QInputDialog.getText(self, "Lien", "Adresse du lien :")
        if accepted:
            set_link(self.editor, href.strip() or None)

    def insert_image_file(self, source: Path, *, image_alt: str = "") -> InlineRun:
        """Copy and insert one local image through the canonical adapter path."""

        if self.current_path is None:
            raise ValueError("Ouvrez d’abord un fichier Mérope.")
        if self.images_dir is None:
            raise ValueError("Le répertoire d’images du projet n’est pas configuré.")
        src = copy_into_images_dir(
            Path(source),
            self.images_dir,
            self.current_path.parent,
        )
        run = InlineRun(image_src=src, image_alt=image_alt)
        cursor = insert_blocks(
            self.editor.textCursor(),
            [Block(kind=PARAGRAPH, runs=[run])],
        )
        self.editor.setTextCursor(cursor)
        return run

    def _insert_image_from_dialog(self) -> None:
        if self._refuse_in_caption("une image"):
            return
        if self.current_path is None:
            QMessageBox.warning(
                self,
                "Insérer une image",
                "Ouvrez d’abord un fichier Mérope afin de calculer le chemin de l’image.",
            )
            return
        if self.images_dir is None:
            QMessageBox.warning(
                self,
                "Insérer une image",
                "Le répertoire d’images du projet n’est pas configuré.",
            )
            return
        source, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choisir une image",
            str(self.current_path.parent),
            "Images (*.jpg *.jpeg *.png *.gif *.webp);;Tous les fichiers (*)",
        )
        if not source:
            return
        try:
            self.insert_image_file(Path(source))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Insertion impossible", str(exc))
            return
        # The caption is typed right below a standalone image: go there.
        image_position = self.editor.textCursor().position() - 1
        if image_position >= 0:
            self.editor.edit_figure_caption(image_position)

    def replace_targeted_image(self, run: InlineRun) -> bool:
        """Replace the unique selected/adjacent image, if unambiguous."""

        try:
            target = targeted_merope_image(self.editor.textCursor())
            if target is None:
                return False
            cursor = replace_merope_image(self.editor.document(), target, run)
        except UnsupportedDocumentError:
            return False
        self.editor.setTextCursor(cursor)
        return run != target.run

    def replace_targeted_image_file(self, source: Path) -> bool:
        """Copy a new bitmap and change only one targeted image's source."""

        if self.current_path is None:
            raise ValueError("Ouvrez d’abord un fichier Mérope.")
        if self.images_dir is None:
            raise ValueError("Le répertoire d’images du projet n’est pas configuré.")
        try:
            target = targeted_merope_image(self.editor.textCursor())
        except UnsupportedDocumentError:
            return False
        if target is None:
            return False

        source = Path(source)
        reader = QImageReader(str(source))
        if not reader.canRead():
            raise ValueError("Le fichier choisi n’est pas une image lisible par Qt.")

        src = copy_into_images_dir(source, self.images_dir, self.current_path.parent)
        run = _run_for_new_bitmap(target.run, src)
        cursor = replace_merope_image(
            self.editor.document(),
            target,
            run,
            allow_source_change=True,
        )
        self.editor.setTextCursor(cursor)
        return run != target.run

    def _replace_image_from_dialog(self) -> bool:
        try:
            target = targeted_merope_image(self.editor.textCursor())
        except UnsupportedDocumentError:
            return False
        if target is None:
            return False
        if self.current_path is None:
            QMessageBox.warning(
                self,
                "Remplacer l’image",
                "Ouvrez d’abord un fichier Mérope afin de calculer le chemin de l’image.",
            )
            return False
        if self.images_dir is None:
            QMessageBox.warning(
                self,
                "Remplacer l’image",
                "Le répertoire d’images du projet n’est pas configuré.",
            )
            return False

        source, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choisir la nouvelle image",
            str(self.current_path.parent),
            "Images (*.jpg *.jpeg *.png *.gif *.webp);;Tous les fichiers (*)",
        )
        if not source:
            return False
        try:
            return self.replace_targeted_image_file(Path(source))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Remplacement impossible", str(exc))
            return False

    def crop_targeted_image(
        self,
        box: tuple[int, int, int, int],
        *,
        quarter_turns: int = 0,
    ) -> bool:
        """Crop/rotate a copy of the targeted local bitmap; update only its source.

        ``box`` refers to the displayed image rotated by ``quarter_turns``
        clockwise quarter turns. Choosing the whole unrotated image is a no-op.
        """

        capability = self._targeted_crop_source()
        if capability is None:
            raise ValueError(
                "L’image ciblée n’a pas de fichier source local lisible à recadrer."
            )
        target, source_path = capability
        width, height = edited_size(source_path, quarter_turns)
        box = validate_source_box(box, width, height)
        if crop_is_identity(source_path, box, quarter_turns):
            return False
        new_src = write_cropped_copy(
            source_path,
            box,
            self.current_path.parent,
            quarter_turns=quarter_turns,
        )
        run = _run_for_new_bitmap(target.run, new_src)
        cursor = replace_merope_image(
            self.editor.document(),
            target,
            run,
            allow_source_change=True,
        )
        self.editor.setTextCursor(cursor)
        return True

    def _crop_image_from_dialog(self) -> bool:
        capability = self._targeted_crop_source()
        if capability is None:
            QMessageBox.warning(
                self,
                "Recadrage impossible",
                "Cette image n’a pas de fichier source local lisible à recadrer.",
            )
            return False
        _target, source_path = capability
        try:
            dialog = CropImageDialog(source_path, self)
        except ValueError as exc:
            QMessageBox.warning(self, "Recadrage impossible", str(exc))
            return False
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        request = dialog.crop_request()
        try:
            return self.crop_targeted_image(
                request.box,
                quarter_turns=request.quarter_turns,
            )
        except (OSError, ValueError, UnsupportedDocumentError) as exc:
            QMessageBox.critical(self, "Recadrage impossible", str(exc))
            return False

    def _targeted_crop_source(self) -> tuple[ImageTarget, Path] | None:
        if self.current_path is None:
            return None
        try:
            target = targeted_merope_image(self.editor.textCursor())
        except UnsupportedDocumentError:
            return None
        if target is None:
            return None
        source_path = self._local_image_source(target.run.image_src)
        if source_path is None or probe_image(source_path) is None:
            return None
        return target, source_path

    def _local_image_source(self, image_src: str | None) -> Path | None:
        if self.current_path is None or not image_src:
            return None
        parsed = urlsplit(image_src)
        if parsed.scheme or parsed.netloc:
            return None
        source = Path(image_src)
        if source.is_absolute():
            return None
        try:
            resolved = (self.current_path.parent / source).resolve()
        except (OSError, RuntimeError):
            return None
        return resolved if resolved.is_file() else None

    def _edit_targeted_image(self) -> bool:
        try:
            target = targeted_merope_image(self.editor.textCursor())
        except UnsupportedDocumentError:
            return False
        if target is None:
            return False
        dialog = ImageMetadataDialog(target.run, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        return self.replace_targeted_image(dialog.image_run())

    def _update_image_action(self) -> None:
        try:
            enabled = targeted_merope_image(self.editor.textCursor()) is not None
        except UnsupportedDocumentError:
            enabled = False
        self.image_action.setEnabled(enabled)
        self.replace_image_action.setEnabled(enabled)
        self.crop_image_action.setEnabled(self._targeted_crop_source() is not None)

    def _show_paste_refused(self, message: str) -> None:
        QMessageBox.warning(
            self,
            "Collage impossible",
            f"Le contenu n’a pas été collé afin d’éviter une perte de données.\n\n{message}",
        )

    def _show_clipboard_refused(self, message: str) -> None:
        QMessageBox.warning(self, "Copie impossible", message)

    def _open_from_dialog(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Ouvrir un fichier Mérope",
            str(self.current_path.parent if self.current_path else self.initial_directory),
            "Markdown (*.md *.markdown);;Tous les fichiers (*)",
        )
        if path:
            self.open_document(Path(path))

    def _renumber_footnotes_for_save(self) -> _RenumberSaveSnapshot | None:
        body_blocks = extract_blocks(self.editor.document())
        renumbering = plan_footnote_renumbering(
            self.footnote_store.definitions,
            footnote_reference_order(body_blocks),
        )
        if not renumbering.changed:
            return None

        cursor = self.editor.textCursor()
        snapshot = _RenumberSaveSnapshot(
            body_blocks=body_blocks,
            store=self.footnote_store.snapshot(),
            body_modified=self.editor.document().isModified(),
            cursor_position=cursor.position(),
            cursor_anchor=cursor.anchor(),
        )
        try:
            renumber_footnote_references(
                self.editor.document(),
                renumbering.mapping,
            )
            self.footnote_store.replace_all(renumbering.definitions)
        except Exception:
            self._restore_renumber_save_snapshot(snapshot)
            raise
        return snapshot

    def _restore_renumber_save_snapshot(
        self,
        snapshot: _RenumberSaveSnapshot,
    ) -> None:
        populate_document(self.editor.document(), snapshot.body_blocks)
        self.editor.document().setModified(snapshot.body_modified)
        self.footnote_store.restore(snapshot.store)
        document_end = max(0, self.editor.document().characterCount() - 1)
        cursor = QTextCursor(self.editor.document())
        cursor.setPosition(min(snapshot.cursor_anchor, document_end))
        cursor.setPosition(
            min(snapshot.cursor_position, document_end),
            QTextCursor.MoveMode.KeepAnchor,
        )
        self.editor.setTextCursor(cursor)
        self._update_window_title()

    def _confirm_unsaved_changes(self) -> bool:
        if not self.document_has_unsaved_changes:
            return True
        answer = QMessageBox.warning(
            self,
            "Modifications non enregistrées",
            "Le document contient des modifications non enregistrées.",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.save_document()
        return True

    def _offer_version_purge(self, archive) -> None:
        if not archive.should_offer_purge:
            return
        candidates = versions_to_purge(archive.versions)
        if not candidates:
            return
        answer = QMessageBox.question(
            self,
            "Versions anciennes",
            f"Supprimer les {len(candidates)} versions les plus anciennes ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            try:
                purge_versions(candidates)
            except OSError as exc:
                QMessageBox.warning(
                    self,
                    "Versions anciennes",
                    f"Le document est enregistré, mais la purge a échoué :\n{exc}",
                )

    def _update_window_title(self, _modified: bool | None = None) -> None:
        name = self.current_path.name if self.current_path else "sans fichier"
        marker = " *" if self.document_has_unsaved_changes else ""
        self.setWindowTitle(f"Mérope - éditeur Qt - {name}{marker}")

    def closeEvent(self, event: QCloseEvent) -> None:
        had_unsaved_changes = self.document_has_unsaved_changes
        if self._confirm_unsaved_changes():
            if had_unsaved_changes:
                self._clear_recovery_draft()
            self.autosave_timer.stop()
            self._close_html_preview()
            self.ipc_bridge.shutdown()
            self._save_layout()
            event.accept()
        else:
            event.ignore()

    def fit_to_screen(self) -> None:
        """Open large enough for two side panels and a readable text column."""

        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        self.resize(
            min(DEFAULT_WINDOW_MAX_WIDTH, round(available.width() * 0.85)),
            min(DEFAULT_WINDOW_MAX_HEIGHT, round(available.height() * 0.85)),
        )

    def restore_layout(self, settings: QSettings) -> None:
        """Reuse the window size and panel widths of the previous session.

        Only the real application opts in (see ``run``); editors created by
        tests or embedders never read or write user settings.
        """

        self._layout_settings = settings
        geometry = settings.value(_GEOMETRY_KEY)
        state = settings.value(_STATE_KEY)
        if isinstance(geometry, QByteArray) and not geometry.isEmpty():
            self.restoreGeometry(geometry)
        if isinstance(state, QByteArray) and not state.isEmpty():
            self.restoreState(state, LAYOUT_STATE_VERSION)

    def _save_layout(self) -> None:
        settings = self._layout_settings
        if settings is None:
            return
        settings.setValue(_GEOMETRY_KEY, self.saveGeometry())
        settings.setValue(_STATE_KEY, self.saveState(LAYOUT_STATE_VERSION))
        settings.sync()

    def request_live_config(self) -> int:
        """Request a fresh parent-owned ProjectConfig snapshot asynchronously."""

        return self.ipc_bridge.request_config()

    def _request_html_preview(self) -> None:
        """Snapshot the current model, then asynchronously request live config."""

        if self.current_path is None:
            self._show_preview_error(
                "L’aperçu exige un document Mérope déjà ouvert afin de résoudre "
                "ses ressources relatives."
            )
            return
        try:
            body_blocks = extract_blocks(self.editor.document())
            all_blocks = body_blocks + footnote_definition_blocks(
                self.footnote_store.definitions
            )
            snapshot = PreviewSnapshot(
                body_markdown=blocks_to_markdown(all_blocks),
                metadata=dict(self.metadata),
                current_path=self.current_path,
                current_kind=self.current_kind,
            )
        except (UnsupportedDocumentError, ValueError) as exc:
            self._show_preview_error(str(exc))
            return

        request_id = self.request_live_config()
        self._pending_preview_request_id = request_id
        self._pending_preview_snapshots[request_id] = snapshot
        self.preview_action.setEnabled(False)

    def _on_preview_config_ready(
        self,
        request_id: int,
        config: ProjectConfig,
    ) -> None:
        snapshot = self._pending_preview_snapshots.pop(request_id, None)
        if request_id != self._pending_preview_request_id or snapshot is None:
            return
        try:
            if self.project_root is None:
                raise PreviewBuildError(
                    "L’aperçu exige la racine de projet fixe transmise par Mérope."
                )
            artifact = build_preview_artifact(
                snapshot,
                config=config,
                project_root=self.project_root,
            )
            self._activate_preview_artifact(artifact)
        except PreviewBuildError as exc:
            self._show_preview_error(str(exc))
        finally:
            self._finish_preview_request(request_id)

    def _on_preview_config_failed(self, request_id: int, message: str) -> None:
        self._pending_preview_snapshots.pop(request_id, None)
        if request_id != self._pending_preview_request_id:
            return
        self._show_preview_error(message)
        self._finish_preview_request(request_id)

    def _on_preview_protocol_error(self, message: str) -> None:
        request_id = self._pending_preview_request_id
        if request_id is None:
            return
        self._show_preview_error(f"Réponse de configuration invalide : {message}")
        self._finish_preview_request(request_id)

    def _finish_preview_request(self, request_id: int) -> None:
        if request_id != self._pending_preview_request_id:
            return
        self._pending_preview_request_id = None
        self._pending_preview_snapshots.clear()
        if self._preview_candidate_monitor is None:
            self.preview_action.setEnabled(True)

    def _activate_preview_artifact(self, artifact: PreviewArtifact) -> None:
        """Launch a candidate and swap the active preview only after READY."""

        if not pywebview_available():
            remove_preview_artifact(artifact)
            raise PreviewBuildError(
                "Aperçu HTML indisponible : pywebview n’est pas installé."
            )
        try:
            new_process = launch_preview_process(artifact)
        except PreviewBuildError:
            remove_preview_artifact(artifact)
            raise

        monitor = PreviewStartupMonitor(new_process, parent=self)
        monitor.ready.connect(
            lambda process, current=monitor: self._on_preview_process_ready(
                current, process
            )
        )
        monitor.failed.connect(
            lambda process, returncode, diagnostic, current=monitor: (
                self._on_preview_process_failed(
                    current,
                    process,
                    returncode,
                    diagnostic,
                )
            )
        )
        monitor.timedOut.connect(
            lambda process, current=monitor: self._on_preview_process_timeout(
                current, process
            )
        )
        monitor.closed.connect(
            lambda process, returncode, current=monitor: (
                self._on_preview_process_closed(current, process, returncode)
            )
        )
        self._preview_candidate_process = new_process
        self._preview_candidate_artifact = artifact
        self._preview_candidate_monitor = monitor
        try:
            monitor.start()
        except Exception as exc:  # pragma: no cover - defensive thread startup
            monitor.cancel()
            self._preview_candidate_process = None
            self._preview_candidate_artifact = None
            self._preview_candidate_monitor = None
            try:
                if new_process.poll() is None:
                    new_process.terminate()
            except OSError:
                pass
            remove_preview_artifact(artifact)
            raise PreviewBuildError(
                f"Impossible de surveiller le démarrage de l’aperçu : {exc}"
            ) from exc

    def _on_preview_process_ready(
        self,
        monitor: PreviewStartupMonitor,
        process: subprocess.Popen,
    ) -> None:
        if (
            monitor is not self._preview_candidate_monitor
            or process is not self._preview_candidate_process
        ):
            return
        artifact = self._preview_candidate_artifact
        if artifact is None:
            return

        old_process = self._preview_process
        old_artifact = self._preview_artifact
        old_monitor = self._preview_monitor
        self._preview_candidate_process = None
        self._preview_candidate_artifact = None
        self._preview_candidate_monitor = None
        self._preview_process = process
        self._preview_artifact = artifact
        self._preview_monitor = monitor
        self.preview_action.setEnabled(True)

        if old_monitor is not None:
            old_monitor.cancel()
        if old_process is not None and old_process.poll() is None:
            try:
                old_process.terminate()
            except OSError:
                pass
        remove_preview_artifact(old_artifact)

    def _on_preview_process_failed(
        self,
        monitor: PreviewStartupMonitor,
        process: subprocess.Popen,
        returncode: int,
        diagnostic: str,
    ) -> None:
        if (
            monitor is not self._preview_candidate_monitor
            or process is not self._preview_candidate_process
        ):
            return
        artifact = self._preview_candidate_artifact
        monitor.cancel()
        self._preview_candidate_process = None
        self._preview_candidate_artifact = None
        self._preview_candidate_monitor = None
        remove_preview_artifact(artifact)
        self.preview_action.setEnabled(True)
        message = "Impossible d’ouvrir la fenêtre d’aperçu."
        if diagnostic:
            message += f"\n\nDiagnostic :\n{diagnostic}"
        else:
            message += f"\n\nLe processus s’est arrêté avec le code {returncode}."
        self._show_preview_error(message)

    def _on_preview_process_timeout(
        self,
        monitor: PreviewStartupMonitor,
        process: subprocess.Popen,
    ) -> None:
        if (
            monitor is not self._preview_candidate_monitor
            or process is not self._preview_candidate_process
        ):
            return
        artifact = self._preview_candidate_artifact
        monitor.cancel()
        self._preview_candidate_process = None
        self._preview_candidate_artifact = None
        self._preview_candidate_monitor = None
        remove_preview_artifact(artifact)
        self.preview_action.setEnabled(True)
        self._show_preview_error(
            "Impossible d’ouvrir la fenêtre d’aperçu : elle n’a pas démarré "
            "dans le délai attendu de 5 secondes."
        )

    def _on_preview_process_closed(
        self,
        monitor: PreviewStartupMonitor,
        process: subprocess.Popen,
        _returncode: int,
    ) -> None:
        if monitor is not self._preview_monitor or process is not self._preview_process:
            return
        artifact = self._preview_artifact
        monitor.cancel()
        self._preview_process = None
        self._preview_artifact = None
        self._preview_monitor = None
        remove_preview_artifact(artifact)

    def _close_html_preview(self) -> None:
        candidate_monitor = self._preview_candidate_monitor
        candidate_process = self._preview_candidate_process
        candidate_artifact = self._preview_candidate_artifact
        if candidate_monitor is not None:
            candidate_monitor.cancel()
        if candidate_process is not None and candidate_process.poll() is None:
            try:
                candidate_process.terminate()
            except OSError:
                pass
        self._preview_candidate_monitor = None
        self._preview_candidate_process = None
        self._preview_candidate_artifact = None
        remove_preview_artifact(candidate_artifact)

        if self._preview_monitor is not None:
            self._preview_monitor.cancel()
        process = self._preview_process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        self._preview_process = None
        self._preview_monitor = None
        remove_preview_artifact(self._preview_artifact)
        self._preview_artifact = None

    def _show_preview_error(self, message: str) -> None:
        QMessageBox.critical(self, "Aperçu HTML", message)

    def _emit(
        self,
        event_type: str,
        *,
        path: Path | None = None,
        message: str | None = None,
    ) -> None:
        if self.ipc:
            emit_event(event_type, path=path, message=message)

    def _add_action(
        self,
        toolbar: WrappingToolBar,
        label: str,
        callback,
        shortcut: str | None = None,
        *,
        shortcuts: list[str] | None = None,
        icon_key: str,
        tooltip: str | None = None,
        checkable: bool = False,
    ) -> QAction:
        action = QAction(toolbar_icon(self, icon_key), label, self)
        sequences = shortcuts or ([shortcut] if shortcut is not None else [])
        if sequences:
            action.setShortcuts([QKeySequence(value) for value in sequences])
        action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        action.setCheckable(checkable)
        if tooltip is None:
            suffix = " / ".join(sequences)
            tooltip = f"{label} — {suffix}" if suffix else label
        action.setToolTip(tooltip)
        action.setStatusTip(tooltip)
        action.triggered.connect(callback)
        toolbar.add_action(action)
        return action


def run(
    markdown_path: Path | None = None,
    *,
    project_root: Path | None = None,
    initial_directory: Path | None = None,
    pages_dir: Path | None = None,
    posts_dir: Path | None = None,
    images_dir: Path | None = None,
    slugify_mode: str = "ascii",
    ipc: bool = False,
) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    try:
        window = QtEditorWindow(
            markdown_path=markdown_path,
            project_root=project_root,
            initial_directory=initial_directory,
            pages_dir=pages_dir,
            posts_dir=posts_dir,
            images_dir=images_dir,
            slugify_mode=slugify_mode,
            ipc=ipc,
        )
    except (OSError, ValueError) as exc:
        if ipc:
            emit_event("open_refused", path=markdown_path, message=str(exc))
        QMessageBox.critical(
            None,
            "Ouverture impossible",
            "Le prototype Qt refuse d’ouvrir ce fichier afin d’éviter toute perte "
            f"de données.\n\n{exc}",
        )
        return 2
    window.fit_to_screen()
    window.restore_layout(editor_layout_settings())
    window.show()
    window._emit("ready")
    returncode = app.exec()
    window._emit("closed")
    return returncode
