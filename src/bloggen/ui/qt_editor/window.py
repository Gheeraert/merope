"""Fenetre d'observation autonome du prototype d'editeur Qt."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QMainWindow,
    QMessageBox,
    QInputDialog,
    QPlainTextEdit,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
)

from bloggen.content.writer import read_content_file
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.markdown.rich_text_model import BULLET_LIST, ORDERED_LIST
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedDocumentError,
    extract_blocks,
    populate_document,
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


class QtEditorWindow(QMainWindow):
    """Minimal QTextEdit shell; it deliberately has no save operation."""

    def __init__(self, markdown_path: Path | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Merope - prototype editeur Qt (lecture experimentale)")
        self.resize(920, 700)
        self.editor = QTextEdit(self)
        self.editor.setAcceptRichText(False)
        self.setCentralWidget(self.editor)
        self._create_toolbar()
        if markdown_path is not None:
            self.load_markdown(markdown_path)

    def load_markdown(self, path: Path) -> None:
        _metadata, body = read_content_file(path)
        populate_document(self.editor.document(), markdown_to_blocks(body))
        self.setWindowTitle(f"Merope - prototype Qt - {path.name} (sans sauvegarde)")

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


def run(markdown_path: Path | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = QtEditorWindow(markdown_path)
    window.show()
    return app.exec()
