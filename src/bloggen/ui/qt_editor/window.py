"""Fenetre d'observation autonome du prototype d'editeur Qt."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QImageReader
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QToolBar,
    QVBoxLayout,
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
    insert_blocks,
    populate_document,
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
from bloggen.ui.qt_editor.text_edit import MeropeTextEdit
from bloggen.ui.qt_editor_protocol import emit_event


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
        self.initial_directory = Path(initial_directory) if initial_directory else Path.cwd()
        self.images_dir = Path(images_dir) if images_dir is not None else None
        self.ipc = ipc
        self.resize(920, 700)
        self.editor = MeropeTextEdit(self)
        self.editor.pasteRefused.connect(self._show_paste_refused)
        self.setCentralWidget(self.editor)
        populate_document(self.editor.document(), [])
        self.editor.document().setModified(False)
        self._create_toolbar()
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
        try:
            result = save_content_document(
                self.current_path,
                self.metadata,
                self.editor.document(),
            )
        except (OSError, ValueError) as exc:
            self._emit("error", message=f"Enregistrement impossible : {exc}")
            QMessageBox.critical(self, "Enregistrement impossible", str(exc))
            return False

        self.current_path = result.path
        self._update_window_title()
        self._emit("saved", path=result.path)
        self._offer_version_purge(result.archive)
        return True

    def show_reconstructed_markdown(self) -> None:
        try:
            markdown = blocks_to_markdown(extract_blocks(self.editor.document()))
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

    def _open_from_dialog(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Ouvrir un fichier Mérope",
            str(self.current_path.parent if self.current_path else self.initial_directory),
            "Markdown (*.md *.markdown);;Tous les fichiers (*)",
        )
        if path:
            self.open_document(Path(path))

    def _confirm_unsaved_changes(self) -> bool:
        if not self.editor.document().isModified():
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
        marker = " *" if self.editor.document().isModified() else ""
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
