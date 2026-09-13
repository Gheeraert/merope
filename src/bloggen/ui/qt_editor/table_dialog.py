"""Small modal dialog for choosing graphical table dimensions."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


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
