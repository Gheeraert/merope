"""Fenetre d'observation autonome du prototype d'editeur Qt."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QAction, QActionGroup, QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
)

from bloggen.content.versioning import purge_versions, versions_to_purge
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_model import BULLET_LIST, ORDERED_LIST
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedDocumentError,
    extract_blocks,
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
from bloggen.ui.qt_editor_protocol import emit_event


class QtEditorWindow(QMainWindow):
    """Standalone editor limited to content the Qt adapter can preserve."""

    def __init__(
        self,
        markdown_path: Path | None = None,
        *,
        initial_directory: Path | None = None,
        ipc: bool = False,
    ) -> None:
        super().__init__()
        self.current_path: Path | None = None
        self.metadata: dict[str, str] = {}
        self.initial_directory = Path(initial_directory) if initial_directory else Path.cwd()
        self.ipc = ipc
        self.resize(920, 700)
        self.editor = QTextEdit(self)
        self.editor.setAcceptRichText(False)
        self.setCentralWidget(self.editor)
        populate_document(self.editor.document(), [])
        self.editor.document().setModified(False)
        self._create_toolbar()
        self.editor.document().modificationChanged.connect(self._update_window_title)
        if markdown_path is not None:
            self.load_markdown(markdown_path)
        self._update_window_title()

    def load_markdown(self, path: Path) -> None:
        loaded = load_content_document(path, self.editor.document())
        self.current_path = loaded.path
        self.metadata = loaded.metadata
        self.save_action.setEnabled(True)
        self._update_window_title()
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
        self._add_action(toolbar, "Voir Markdown", self.show_reconstructed_markdown)

    def _prompt_for_link(self) -> None:
        href, accepted = QInputDialog.getText(self, "Lien", "Adresse du lien :")
        if accepted:
            set_link(self.editor, href.strip() or None)

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
    ipc: bool = False,
) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = QtEditorWindow(initial_directory=initial_directory, ipc=ipc)
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
