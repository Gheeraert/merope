"""Small modal dialogs for inserting graphical tables."""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from bloggen.ui.qt_editor.table_clipboard import ClipboardTable


_PREVIEW_MAX_CHARACTERS = 120


class TablePasteChoice(Enum):
    CANCEL = auto()
    TABLE_WITH_HEADER = auto()
    TABLE_WITHOUT_HEADER = auto()
    PLAIN_TEXT = auto()


class TableInsertDialog(QDialog):
    """Collect safe dimensions for a simple table."""

    MINIMUM_DIMENSION = 1
    MAXIMUM_DIMENSION = 50
    DEFAULT_DIMENSION = 2

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insérer un tableau")

        layout = QVBoxLayout(self)
        explanation = QLabel(
            "La première ligne du tableau sert d’en-tête.",
            self,
        )
        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        form = QFormLayout()
        self.rows_spin = self._dimension_spinbox("Nombre de lignes, en-tête inclus")
        self.columns_spin = self._dimension_spinbox("Nombre de colonnes")
        form.addRow("Lignes :", self.rows_spin)
        form.addRow("Colonnes :", self.columns_spin)
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def dimensions(self) -> tuple[int, int]:
        return self.rows_spin.value(), self.columns_spin.value()

    def _dimension_spinbox(self, tooltip: str) -> QSpinBox:
        spinbox = QSpinBox(self)
        spinbox.setRange(self.MINIMUM_DIMENSION, self.MAXIMUM_DIMENSION)
        spinbox.setValue(self.DEFAULT_DIMENSION)
        spinbox.setToolTip(tooltip)
        return spinbox


class TablePasteDialog(QDialog):
    """Confirm a pasted table and say whether its first row holds headers."""

    def __init__(
        self,
        table: ClipboardTable,
        *,
        can_paste_as_text: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Coller un tableau")
        self._plain_text_requested = False

        layout = QVBoxLayout(self)
        summary = QLabel(
            f"Tableau détecté : {table.row_count} ligne(s), "
            f"{table.column_count} colonne(s).",
            self,
        )
        layout.addWidget(summary)

        self.first_row_check = QCheckBox("Première ligne = en-têtes", self)
        self.first_row_check.setChecked(True)
        self.first_row_check.setToolTip(
            "Décochée, le tableau reçoit une ligne d’en-têtes vide."
        )
        layout.addWidget(self.first_row_check)

        preview = " | ".join(table.rows[0])
        if len(preview) > _PREVIEW_MAX_CHARACTERS:
            preview = preview[:_PREVIEW_MAX_CHARACTERS] + "…"
        self.preview_label = QLabel(preview, self)
        self.preview_label.setTextFormat(Qt.TextFormat.PlainText)
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            "Coller le tableau"
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annuler")
        self.plain_text_button = self.buttons.addButton(
            "Coller comme texte",
            QDialogButtonBox.ButtonRole.ActionRole,
        )
        self.plain_text_button.setEnabled(can_paste_as_text)
        self.plain_text_button.clicked.connect(self._accept_plain_text)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def choice(self) -> TablePasteChoice:
        if self.result() != QDialog.DialogCode.Accepted:
            return TablePasteChoice.CANCEL
        if self._plain_text_requested:
            return TablePasteChoice.PLAIN_TEXT
        if self.first_row_check.isChecked():
            return TablePasteChoice.TABLE_WITH_HEADER
        return TablePasteChoice.TABLE_WITHOUT_HEADER

    def _accept_plain_text(self) -> None:
        self._plain_text_requested = True
        self.accept()


def ask_table_paste_choice(
    parent: QWidget,
    table: ClipboardTable,
    *,
    can_paste_as_text: bool,
) -> TablePasteChoice:
    dialog = TablePasteDialog(
        table,
        can_paste_as_text=can_paste_as_text,
        parent=parent,
    )
    dialog.exec()
    return dialog.choice()
