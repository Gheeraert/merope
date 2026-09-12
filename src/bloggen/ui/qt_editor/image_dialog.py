"""Small metadata dialog for one already selected Merope image."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from bloggen.content.image_size import (
    MAX_PERCENT,
    MIN_PERCENT,
    clamp_percent,
    format_percent,
    max_percent_for,
    parse_width,
)
from bloggen.markdown.rich_text_model import InlineRun


_DEFAULT_PERCENT = 50


class ImageMetadataDialog(QDialog):
    """Edit image metadata without changing its canonical source.

    The width is a percentage of the text column; the height always follows
    the image's proportions. Untouched values, including historical pixel
    sizes, are returned exactly as they were.
    """

    def __init__(self, run: InlineRun, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._initial = run
        self._edited_fields: set[str] = set()
        self.setWindowTitle("Image")

        self.src_edit = QLineEdit(run.image_src or "", self)
        self.src_edit.setReadOnly(True)
        self.alt_edit = QLineEdit(run.image_alt or "", self)

        spec = parse_width(run.image_width)
        self.width_spin = QSpinBox(self)
        self.width_spin.setRange(MIN_PERCENT, MAX_PERCENT)
        self.width_spin.setSuffix(" % de la colonne")
        self.width_spin.setValue(
            spec.value if spec is not None and spec.is_percent else _DEFAULT_PERCENT
        )
        self.natural_check = QCheckBox("Taille réelle", self)
        self.natural_check.setToolTip(
            "L’image garde sa taille d’origine, sans jamais dépasser la colonne."
        )
        self.natural_check.setChecked(spec is None)
        self.width_spin.setEnabled(spec is not None)
        width_row = QHBoxLayout()
        width_row.addWidget(self.width_spin, 1)
        width_row.addWidget(self.natural_check)

        self.legacy_label = QLabel(self)
        self.legacy_label.setWordWrap(True)
        self.legacy_label.setStyleSheet("color: palette(mid);")
        if spec is not None and not spec.is_percent:
            self.legacy_label.setText(
                f"Taille actuelle : {spec.value} px (ancien format). Elle est "
                "conservée tant que vous ne modifiez pas la largeur."
            )
        self.legacy_label.setVisible(bool(self.legacy_label.text()))

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
        form.addRow("Largeur :", width_row)
        form.addRow("", self.legacy_label)
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

        self._alignment_changed()
        self.alt_edit.textChanged.connect(lambda: self._edited_fields.add("alt"))
        self.width_spin.valueChanged.connect(self._width_changed)
        self.natural_check.toggled.connect(self._natural_toggled)
        self.align_combo.currentIndexChanged.connect(self._alignment_changed)

    def image_run(self) -> InlineRun:
        """Return a fresh canonical run while retaining untouched values."""

        align = self.align_combo.currentData()
        width = self._initial.image_width
        height = self._initial.image_height
        if "width" in self._edited_fields:
            height = None
            width = (
                None
                if self.natural_check.isChecked()
                else format_percent(clamp_percent(self.width_spin.value(), align=align))
            )
        return InlineRun(
            image_src=self._initial.image_src,
            image_alt=(
                self.alt_edit.text()
                if "alt" in self._edited_fields
                else self._initial.image_alt
            ),
            image_width=width,
            image_height=height,
            image_align=align,
        )

    def _width_changed(self) -> None:
        if self.width_spin.isEnabled():
            self._edited_fields.add("width")

    def _natural_toggled(self, checked: bool) -> None:
        self.width_spin.setEnabled(not checked)
        self._edited_fields.add("width")

    def _alignment_changed(self) -> None:
        # Floated figures are limited to half of the column on the site.
        ceiling = max_percent_for(self.align_combo.currentData())
        self.width_spin.setMaximum(ceiling)
