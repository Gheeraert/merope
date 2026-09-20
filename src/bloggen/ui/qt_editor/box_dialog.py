"""Small modal dialog asking for the optional title of a new encadré."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class BoxInsertDialog(QDialog):
    """Collect the (optional) single-line title of an encadré."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insérer un encadré")

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title_edit = QLineEdit(self)
        self.title_edit.setPlaceholderText("Facultatif")
        self.title_edit.setToolTip("Titre de l’encadré (facultatif)")
        form.addRow("Titre de l’encadré :", self.title_edit)
        layout.addLayout(form)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def title(self) -> str:
        """The title, single-lined and stripped; empty means untitled."""

        return " ".join(self.title_edit.text().split())
