"""Fenetre d'observation autonome du prototype d'editeur Qt."""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QImageReader, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from bloggen.content.footnotes import (
    FootnoteDefinitions,
    footnote_definition_blocks,
    footnote_reference_counts,
    footnote_reference_order,
    plan_footnote_renumbering,
)
from bloggen.content.image_service import copy_into_images_dir, write_cropped_copy
from bloggen.content.versioning import purge_versions, versions_to_purge
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_model import (
    BULLET_LIST,
    ORDERED_LIST,
    PARAGRAPH,
    Block,
    InlineRun,
)
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedDocumentError,
    extract_blocks,
    insert_footnote_reference,
    insert_blocks,
    populate_document,
    renumber_footnote_references,
)
from bloggen.ui.qt_editor.file_io import (
    load_content_document,
    save_content_document,
)
from bloggen.ui.qt_editor.formatting import (
    set_alignment,
    set_blockquote,
    set_heading,
    set_link,
    set_list,
    set_paragraph,
    toggle_bold,
    toggle_italic,
    toggle_strikethrough,
    toggle_superscript,
)
from bloggen.ui.qt_editor.image_crop import validate_source_box
from bloggen.ui.qt_editor.image_crop_dialog import CropImageDialog, crop_source_size
from bloggen.ui.qt_editor.image_dialog import ImageMetadataDialog
from bloggen.ui.qt_editor.image_selection import (
    ImageTarget,
    replace_merope_image,
    targeted_merope_image,
)
from bloggen.ui.qt_editor.footnote_panel import FootnotePanel
from bloggen.ui.qt_editor.footnote_store import (
    FootnoteStore,
    FootnoteStoreSnapshot,
    plain_footnote_text,
)
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor_protocol import emit_event


@dataclass(frozen=True, slots=True)
class _RenumberSaveSnapshot:
    body_blocks: list[Block]
    store: FootnoteStoreSnapshot
    body_modified: bool
    cursor_position: int
    cursor_anchor: int


class QtEditorWindow(QMainWindow):
    """Standalone editor limited to content the Qt adapter can preserve."""

    def __init__(
        self,
        markdown_path: Path | None = None,
        *,
        initial_directory: Path | None = None,
        images_dir: Path | None = None,
        ipc: bool = False,
    ) -> None:
        super().__init__()
        self.current_path: Path | None = None
        self.metadata: dict[str, str] = {}
        self.footnote_store = FootnoteStore(self)
        self.initial_directory = Path(initial_directory) if initial_directory else Path.cwd()
        self.images_dir = Path(images_dir) if images_dir is not None else None
        self.ipc = ipc
        self.resize(920, 700)
        self.editor = MeropeTextEdit(self)
        self.editor.pasteRefused.connect(self._show_paste_refused)
        self.editor.clipboardRefused.connect(self._show_clipboard_refused)
        self.setCentralWidget(self.editor)
        populate_document(self.editor.document(), [])
        self.editor.document().setModified(False)
        self._create_toolbar()
        self._create_footnote_panel()
        self.footnote_store.changed.connect(self._refresh_footnote_panel)
        self.footnote_store.modifiedChanged.connect(self._update_window_title)
        self.editor.footnoteActivated.connect(self.footnote_panel.select_note)
        self.editor.cursorPositionChanged.connect(self._update_image_action)
        self.editor.selectionChanged.connect(self._update_image_action)
        self.editor.document().modificationChanged.connect(self._update_window_title)
        if markdown_path is not None:
            self.load_markdown(markdown_path)
        self._update_window_title()
        self._update_image_action()

    def load_markdown(self, path: Path) -> None:
        loaded = load_content_document(path, self.editor.document())
        self.current_path = loaded.path
        self.metadata = loaded.metadata
        self.footnote_store.load(loaded.footnote_definitions)
        self.save_action.setEnabled(True)
        self._update_window_title()
        self._update_image_action()
        self._emit("opened", path=loaded.path)

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
        return True

    def save_document(self) -> bool:
        if self.current_path is None:
            QMessageBox.warning(self, "Enregistrer", "Ouvrez d’abord un fichier Mérope.")
            return False
        renumber_snapshot: _RenumberSaveSnapshot | None = None
        try:
            renumber_snapshot = self._renumber_footnotes_for_save()
            result = save_content_document(
                self.current_path,
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
        if renumber_snapshot is not None:
            self.editor.document().clearUndoRedoStacks()
            self.editor.document().setModified(False)
        self.footnote_store.mark_clean()
        self._update_window_title()
        self._emit("saved", path=result.path)
        self._offer_version_purge(result.archive)
        return True

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
        toolbar = QToolBar("Mise en forme", self)
        self.addToolBar(toolbar)
        self._add_action(toolbar, "Ouvrir", self._open_from_dialog, "Ctrl+O")
        self.save_action = self._add_action(
            toolbar, "Enregistrer", self.save_document, "Ctrl+S"
        )
        self.save_action.setEnabled(False)
        toolbar.addSeparator()
        self._add_action(toolbar, "Gras", lambda: toggle_bold(self.editor), "Ctrl+B")
        self._add_action(toolbar, "Italique", lambda: toggle_italic(self.editor), "Ctrl+I")
        self._add_action(toolbar, "Barre", lambda: toggle_strikethrough(self.editor))
        self._add_action(toolbar, "Exposant", lambda: toggle_superscript(self.editor))
        self._add_action(toolbar, "Lien", self._prompt_for_link, "Ctrl+K")
        self._add_action(toolbar, "Insérer une note...", self._insert_footnote_from_dialog)
        self._add_action(toolbar, "Renuméroter les notes", self.save_document)
        self._add_action(toolbar, "Insérer une image...", self._insert_image_from_dialog)
        self.image_action = self._add_action(
            toolbar,
            "Image...",
            self._edit_targeted_image,
        )
        self.image_action.setEnabled(False)
        self.replace_image_action = self._add_action(
            toolbar,
            "Remplacer l’image...",
            self._replace_image_from_dialog,
        )
        self.replace_image_action.setEnabled(False)
        self.crop_image_action = self._add_action(
            toolbar,
            "Recadrer...",
            self._crop_image_from_dialog,
        )
        self.crop_image_action.setEnabled(False)
        toolbar.addSeparator()

        block_group = QActionGroup(self)
        for label, callback in [
            ("Paragraphe", lambda: set_paragraph(self.editor)),
            ("H1", lambda: set_heading(self.editor, 1)),
            ("H2", lambda: set_heading(self.editor, 2)),
            ("H3", lambda: set_heading(self.editor, 3)),
            ("H4", lambda: set_heading(self.editor, 4)),
            ("Citation", lambda: set_blockquote(self.editor)),
        ]:
            action = self._add_action(toolbar, label, callback)
            action.setCheckable(True)
            block_group.addAction(action)

        toolbar.addSeparator()
        self._add_action(toolbar, "Liste a puces", lambda: set_list(self.editor, BULLET_LIST))
        self._add_action(toolbar, "Liste numerotee", lambda: set_list(self.editor, ORDERED_LIST))
        toolbar.addSeparator()
        for label, alignment in [
            ("Gauche", "left"),
            ("Centre", "center"),
            ("Droite", "right"),
            ("Justifie", "justify"),
        ]:
            self._add_action(
                toolbar,
                label,
                lambda checked=False, value=alignment: set_alignment(self.editor, value),
            )
        toolbar.addSeparator()
        self._add_action(toolbar, "Annuler", self.editor.undo, "Ctrl+Z")
        self._add_action(toolbar, "Retablir", self.editor.redo, "Ctrl+Shift+Z")
        self._add_action(
            toolbar,
            "Typographie",
            self.editor.apply_typography_to_selection,
        )
        self._add_action(toolbar, "Voir Markdown", self.show_reconstructed_markdown)

    def _create_footnote_panel(self) -> None:
        self.footnote_dock = QDockWidget("Notes", self)
        self.footnote_dock.setObjectName("meropeFootnoteDock")
        container = QWidget(self.footnote_dock)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        self.footnote_panel = FootnotePanel(container)
        layout.addWidget(self.footnote_panel)
        buttons = QHBoxLayout()
        self.edit_footnote_button = QPushButton("Modifier...", container)
        self.delete_footnote_button = QPushButton("Supprimer...", container)
        self.edit_footnote_button.clicked.connect(self._edit_selected_footnote)
        self.delete_footnote_button.clicked.connect(self._delete_selected_footnote)
        buttons.addWidget(self.edit_footnote_button)
        buttons.addWidget(self.delete_footnote_button)
        layout.addLayout(buttons)
        self.footnote_panel.noteSelected.connect(self._update_footnote_actions)
        self.footnote_dock.setWidget(container)
        self.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea,
            self.footnote_dock,
        )
        self.footnote_panel.set_definitions(self.footnote_store.definitions)
        self._update_footnote_actions()

    @property
    def footnote_definitions(self) -> FootnoteDefinitions:
        """Compatibility view of the canonical session store."""

        return self.footnote_store.definitions

    @property
    def document_has_unsaved_changes(self) -> bool:
        return self.editor.document().isModified() or self.footnote_store.modified

    def _refresh_footnote_panel(self) -> None:
        self.footnote_panel.set_definitions(self.footnote_store.definitions)
        self._update_footnote_actions()

    def _update_footnote_actions(self, _note_id: str | None = None) -> None:
        note_id = self.footnote_panel.selected_note_id
        runs = self.footnote_store.definition(note_id) if note_id is not None else None
        self.delete_footnote_button.setEnabled(runs is not None)
        is_plain = runs is not None and plain_footnote_text(runs) is not None
        self.edit_footnote_button.setEnabled(is_plain)
        self.edit_footnote_button.setToolTip(
            ""
            if is_plain
            else "Cette note contient une mise en forme riche non éditable dans cette phase."
        )

    def insert_footnote(self, text: str) -> str:
        """Register a plain definition and insert its atomic body reference."""

        if text == "":
            raise ValueError("Le texte de la note ne peut pas être vide.")
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            raise ValueError(
                "Désélectionnez le texte avant d’insérer un appel de note."
            )
        store_snapshot = self.footnote_store.snapshot()
        note_id = self.footnote_store.register(text)
        try:
            cursor = insert_footnote_reference(cursor, note_id)
        except Exception:
            self.footnote_store.restore(store_snapshot)
            raise
        self.editor.setTextCursor(cursor)
        self.footnote_panel.select_note(note_id)
        return note_id

    def _insert_footnote_from_dialog(self) -> bool:
        text, accepted = QInputDialog.getText(
            self,
            "Note de bas de page",
            "Texte de la note :",
        )
        if not accepted:
            return False
        try:
            self.insert_footnote(text)
        except (ValueError, UnsupportedDocumentError) as exc:
            QMessageBox.warning(self, "Insertion impossible", str(exc))
            return False
        return True

    def edit_footnote_definition(self, note_id: str, text: str) -> bool:
        runs = self.footnote_store.definition(note_id)
        if runs is None:
            return False
        if plain_footnote_text(runs) is None:
            raise ValueError(
                "Cette note contient une mise en forme riche ; son édition sera "
                "disponible dans une phase suivante."
            )
        return self.footnote_store.update(note_id, [InlineRun(text=text)])

    def _edit_selected_footnote(self) -> bool:
        note_id = self.footnote_panel.selected_note_id
        if note_id is None:
            return False
        runs = self.footnote_store.definition(note_id)
        if runs is None:
            return False
        plain_text = plain_footnote_text(runs)
        if plain_text is None:
            QMessageBox.warning(
                self,
                "Modification impossible",
                "Cette note contient une mise en forme riche ; son édition sera "
                "disponible dans une phase suivante.",
            )
            return False
        text, accepted = QInputDialog.getText(
            self,
            "Modifier la note",
            "Texte de la note :",
            QLineEdit.EchoMode.Normal,
            plain_text,
        )
        return accepted and self.edit_footnote_definition(note_id, text)

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
        image_alt, accepted = QInputDialog.getText(
            self,
            "Image",
            "Légende (sert aussi de texte alternatif) :",
        )
        if not accepted:
            return
        try:
            self.insert_image_file(Path(source), image_alt=image_alt)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Insertion impossible", str(exc))

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
        run = replace(target.run, image_src=src)
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

    def crop_targeted_image(self, box: tuple[int, int, int, int]) -> bool:
        """Crop the targeted local bitmap copy and update only its source."""

        capability = self._targeted_crop_source()
        if capability is None:
            raise ValueError(
                "L’image ciblée n’a pas de fichier source local lisible à recadrer."
            )
        target, source_path = capability
        width, height = crop_source_size(source_path)
        box = validate_source_box(box, width, height)
        new_src = write_cropped_copy(source_path, box, self.current_path.parent)
        run = replace(target.run, image_src=new_src)
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
        try:
            return self.crop_targeted_image(dialog.crop_box())
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
        if source_path is None:
            return None
        try:
            crop_source_size(source_path)
        except ValueError:
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
        if self._confirm_unsaved_changes():
            event.accept()
        else:
            event.ignore()

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
        toolbar: QToolBar,
        label: str,
        callback,
        shortcut: str | None = None,
    ) -> QAction:
        action = QAction(label, self)
        if shortcut is not None:
            action.setShortcut(shortcut)
        action.triggered.connect(callback)
        toolbar.addAction(action)
        return action


def run(
    markdown_path: Path | None = None,
    *,
    initial_directory: Path | None = None,
    images_dir: Path | None = None,
    ipc: bool = False,
) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = QtEditorWindow(
        initial_directory=initial_directory,
        images_dir=images_dir,
        ipc=ipc,
    )
    if markdown_path is not None:
        try:
            window.load_markdown(markdown_path)
        except (OSError, ValueError) as exc:
            window._emit("open_refused", path=markdown_path, message=str(exc))
            QMessageBox.critical(
                None,
                "Ouverture impossible",
                "Le prototype Qt refuse d’ouvrir ce fichier afin d’éviter toute perte "
                f"de données.\n\n{exc}",
            )
            return 2
    window.show()
    window._emit("ready")
    returncode = app.exec()
    window._emit("closed")
    return returncode
