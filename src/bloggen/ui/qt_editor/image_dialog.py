"""Small metadata dialog for one already selected Merope image."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from bloggen.markdown.rich_text_model import InlineRun


class ImageMetadataDialog(QDialog):
    """Edit image metadata without changing its canonical source."""

    def __init__(self, run: InlineRun, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._initial = run
        self._edited_fields: set[str] = set()
        self.setWindowTitle("Image")

        self.src_edit = QLineEdit(run.image_src or "", self)
        self.src_edit.setReadOnly(True)
        self.alt_edit = QLineEdit(run.image_alt or "", self)
        self.width_edit = QLineEdit(run.image_width or "", self)
        self.height_edit = QLineEdit(run.image_height or "", self)
        self.align_combo = QComboBox(self)
        self.align_combo.addItem("Aucun", None)
        self.align_combo.addItem("Gauche", "left")
        self.align_combo.addItem("Centre", "center")
        self.align_combo.addItem("Droite", "right")
        alignment_index = self.align_combo.findData(run.image_align)
        self.align_combo.setCurrentIndex(max(alignment_index, 0))

        form = QFormLayout()
        form.addRow("Source :", self.src_edit)
        form.addRow("Légende :", self.alt_edit)
        form.addRow("Largeur :", self.width_edit)
        form.addRow("Hauteur :", self.height_edit)
        form.addRow("Alignement :", self.align_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self.alt_edit.textChanged.connect(lambda: self._edited_fields.add("alt"))
        self.width_edit.textChanged.connect(lambda: self._edited_fields.add("width"))
        self.height_edit.textChanged.connect(lambda: self._edited_fields.add("height"))

    def image_run(self) -> InlineRun:
        """Return a fresh canonical run while retaining untouched values."""

        return InlineRun(
            image_src=self._initial.image_src,
            image_alt=self._text_value("alt", self.alt_edit, empty_means_none=False),
            image_width=self._text_value(
                "width", self.width_edit, empty_means_none=True
            ),
            image_height=self._text_value(
                "height", self.height_edit, empty_means_none=True
            ),
            image_align=self.align_combo.currentData(),
        )

    def _text_value(
        self,
        field: str,
        editor: QLineEdit,
        *,
        empty_means_none: bool,
    ) -> str | None:
        initial = getattr(self._initial, f"image_{field}")
        if field not in self._edited_fields:
            return initial
        value = editor.text()
        return None if empty_means_none and value == "" else value
