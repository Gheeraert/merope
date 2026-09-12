"""Modal rich editor for one canonical Merope footnote definition."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QAction, QKeyEvent, QKeySequence, QTextDocument
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from bloggen.markdown.html_paste_import import UnsupportedHtmlStructureError
from bloggen.markdown.rich_text_model import PARAGRAPH, Block, InlineRun
from bloggen.ui.qt_editor.clipboard_fragment import (
    MEROPE_FRAGMENT_MIME,
    InvalidMeropeClipboardFragment,
)
from bloggen.ui.qt_editor.document_adapter import (
    UnsupportedDocumentError,
    extract_blocks,
    insert_blocks,
    populate_document,
    validate_footnote_definitions,
)
from bloggen.ui.qt_editor.formatting import (
    set_link,
    toggle_bold,
    toggle_italic,
    toggle_underline,
    toggle_strikethrough,
    toggle_superscript,
)
from bloggen.ui.qt_editor.text_edit import (
    MeropeTextEdit,
    blocks_from_rich_mime_data,
)


_PARAGRAPH_SEPARATORS = frozenset({"\r", "\n", "\u2028", "\u2029"})


class InvalidFootnoteDefinition(UnsupportedDocumentError):
    """Raised when a modal document cannot be one inline definition."""


def validate_footnote_runs(
    runs: list[InlineRun],
    *,
    require_nonempty: bool = True,
) -> list[InlineRun]:
    """Validate and clone the canonical inline subset accepted by the dialog."""

    try:
        validate_footnote_definitions({"1": runs})
    except UnsupportedDocumentError as exc:
        raise InvalidFootnoteDefinition(str(exc)) from exc
    if any(
        separator in run.text
        for run in runs
        for separator in _PARAGRAPH_SEPARATORS
    ):
        raise InvalidFootnoteDefinition(
            "Une définition de note doit rester sur un seul paragraphe."
        )
    if require_nonempty and not "".join(run.text for run in runs).strip():
        raise InvalidFootnoteDefinition(
            "Le texte de la note ne peut pas être vide ni contenir seulement des espaces."
        )
    return [replace(run) for run in runs]


def footnote_runs_semantically_equal(
    left: list[InlineRun],
    right: list[InlineRun],
) -> bool:
    """Compare rich inline meaning while ignoring technical run splitting."""

    return _semantic_run_segments(left) == _semantic_run_segments(right)


def _semantic_run_segments(runs: list[InlineRun]) -> list[tuple[object, ...]]:
    validate_footnote_runs(runs, require_nonempty=False)
    segments: list[tuple[object, ...]] = []
    for run in runs:
        if not run.text:
            continue
        attributes = (
            run.bold,
            run.italic,
            run.underline,
            run.strikethrough,
            run.superscript,
            run.link_href,
        )
        if segments and segments[-1][:-1] == attributes:
            segments[-1] = (*attributes, str(segments[-1][-1]) + run.text)
        else:
            segments.append((*attributes, run.text))
    return segments


def footnote_runs_from_blocks(
    blocks: list[Block],
    *,
    require_nonempty: bool = True,
) -> list[InlineRun]:
    """Extract one lossless definition from exactly one ordinary paragraph."""

    if len(blocks) != 1 or blocks[0].kind != PARAGRAPH:
        raise InvalidFootnoteDefinition(
            "Une définition de note doit contenir exactement un paragraphe ordinaire."
        )
    block = blocks[0]
    if (
        block.children
        or block.alignment != "left"
        or block.level is not None
        or block.footnote_id is not None
        or block.raw_text is not None
    ):
        raise InvalidFootnoteDefinition(
            "Les structures de bloc et alignements ne sont pas autorisés dans une note."
        )
    return validate_footnote_runs(
        block.runs,
        require_nonempty=require_nonempty,
    )


def footnote_runs_from_document(document: QTextDocument) -> list[InlineRun]:
    """Round-trip one modal QTextDocument through the canonical adapter."""

    return footnote_runs_from_blocks(extract_blocks(document))


class FootnoteTextEdit(MeropeTextEdit):
    """Merope editing surface constrained to one inline paragraph."""

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            event.accept()
            return
        super().keyPressEvent(event)

    def insertFromMimeData(self, source: QMimeData) -> None:
        """Validate rich or plain clipboard content before any local mutation."""

        has_internal_fragment = source.hasFormat(MEROPE_FRAGMENT_MIME)
        has_rich_html = source.hasHtml() and bool(source.html().strip())
        if has_internal_fragment or has_rich_html:
            try:
                blocks = blocks_from_rich_mime_data(source)
                if blocks:
                    runs = footnote_runs_from_blocks(blocks)
                    cursor = insert_blocks(
                        self.textCursor(),
                        [Block(kind=PARAGRAPH, runs=runs)],
                    )
                    self.setTextCursor(cursor)
                    return
                if has_internal_fragment:
                    return
            except InvalidMeropeClipboardFragment as exc:
                self.pasteRefused.emit(f"Fragment Mérope invalide : {exc}")
                return
            except (
                InvalidFootnoteDefinition,
                UnsupportedHtmlStructureError,
                UnsupportedDocumentError,
            ) as exc:
                self.pasteRefused.emit(str(exc))
                return
            except Exception as exc:
                self.pasteRefused.emit(
                    f"Le collage HTML n’a pas pu être analysé : {exc}"
                )
                return

        if source.hasText():
            text = source.text()
            if any(separator in text for separator in _PARAGRAPH_SEPARATORS):
                self.pasteRefused.emit(
                    "Une définition de note doit rester sur un seul paragraphe."
                )
                return
            super().insertFromMimeData(source)
            return

        self.pasteRefused.emit(
            "Ce format de presse-papiers n’est pas autorisé dans une note."
        )


class FootnoteEditorDialog(QDialog):
    """Edit one definition locally and expose runs only after successful OK."""

    def __init__(
        self,
        runs: list[InlineRun],
        parent: QWidget | None = None,
        *,
        title: str = "Note de bas de page",
    ) -> None:
        super().__init__(parent)
        validate_footnote_runs(runs, require_nonempty=False)
        self.setWindowTitle(title)
        self.resize(680, 300)
        self._accepted_runs: list[InlineRun] | None = None

        layout = QVBoxLayout(self)
        toolbar = QToolBar("Mise en forme de la note", self)
        layout.addWidget(toolbar)

        self.editor = FootnoteTextEdit(self)
        self.editor.pasteRefused.connect(self._show_paste_refused)
        self.editor.clipboardRefused.connect(self._show_clipboard_refused)
        populate_document(
            self.editor.document(),
            [Block(kind=PARAGRAPH, runs=[replace(run) for run in runs])],
        )
        self.editor.document().setModified(False)
        layout.addWidget(self.editor)

        bold_action = self._add_action(
            toolbar, "Gras", lambda: toggle_bold(self.editor), "Ctrl+B"
        )
        bold_action.setShortcuts([QKeySequence("Ctrl+G"), QKeySequence("Ctrl+B")])
        self._add_action(
            toolbar,
            "Italique",
            lambda: toggle_italic(self.editor),
            "Ctrl+I",
        )
        self._add_action(
            toolbar,
            "Souligné",
            lambda: toggle_underline(self.editor),
            "Ctrl+U",
        )
        self._add_action(
            toolbar,
            "Barré",
            lambda: toggle_strikethrough(self.editor),
        )
        self._add_action(
            toolbar,
            "Exposant",
            lambda: toggle_superscript(self.editor),
        )
        self._add_action(toolbar, "Lien", self._prompt_for_link, "Ctrl+K")
        toolbar.addSeparator()
        self._add_action(toolbar, "Annuler", self.editor.undo, "Ctrl+Z")
        redo_action = self._add_action(
            toolbar, "Rétablir", self.editor.redo, "Ctrl+Shift+Z"
        )
        redo_action.setShortcuts(
            [QKeySequence("Ctrl+Y"), QKeySequence("Ctrl+Shift+Z")]
        )
        self._add_action(
            toolbar,
            "Typographie",
            self.editor.apply_typography_to_selection,
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.editor.setFocus()

    def result_runs(self) -> list[InlineRun]:
        if self._accepted_runs is None:
            raise RuntimeError("Le dialogue n’a pas été validé")
        return [replace(run) for run in self._accepted_runs]

    def accept(self) -> None:
        try:
            runs = footnote_runs_from_document(self.editor.document())
        except (ValueError, UnsupportedDocumentError) as exc:
            QMessageBox.warning(self, "Note invalide", str(exc))
            return
        self._accepted_runs = runs
        super().accept()

    def _prompt_for_link(self) -> None:
        cursor = self.editor.textCursor()
        initial = cursor.charFormat().anchorHref() if cursor.charFormat().isAnchor() else ""
        href, accepted = QInputDialog.getText(
            self,
            "Lien",
            "Adresse du lien :",
            QLineEdit.EchoMode.Normal,
            initial,
        )
        if accepted:
            set_link(self.editor, href.strip() or None)

    def _show_paste_refused(self, message: str) -> None:
        QMessageBox.warning(
            self,
            "Collage impossible",
            f"Le contenu n’a pas été collé afin d’éviter une perte de données.\n\n{message}",
        )

    def _show_clipboard_refused(self, message: str) -> None:
        QMessageBox.warning(self, "Copie impossible", message)

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
