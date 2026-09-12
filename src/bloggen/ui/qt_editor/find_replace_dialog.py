"""Non-modal find/replace dialog for the Qt editor body."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bloggen.ui.qt_editor.find_replace import (
    find_next,
    replace_all,
    replace_current,
    selected_replaceable_match,
)


class FindReplaceDialog(QDialog):
    """One reusable non-modal view over safe QTextDocument operations."""

    def __init__(self, editor, parent=None, *, show_replace: bool = False) -> None:
        super().__init__(parent)
        self.editor = editor
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.search_edit = QLineEdit(self)
        self.replace_edit = QLineEdit(self)
        self.replace_label = QLabel("Remplacer par :", self)
        form.addRow("Rechercher :", self.search_edit)
        form.addRow(self.replace_label, self.replace_edit)
        layout.addLayout(form)

        self.case_checkbox = QCheckBox("Respecter la casse", self)
        layout.addWidget(self.case_checkbox)

        self.buttons = QWidget(self)
        button_layout = QHBoxLayout(self.buttons)
        button_layout.setContentsMargins(0, 0, 0, 0)
        self.next_button = QPushButton("Suivant", self.buttons)
        self.replace_button = QPushButton("Remplacer", self.buttons)
        self.replace_all_button = QPushButton("Tout remplacer", self.buttons)
        button_layout.addWidget(self.next_button)
        button_layout.addWidget(self.replace_button)
        button_layout.addWidget(self.replace_all_button)
        layout.addWidget(self.buttons)

        self.status_label = QLabel("", self)
        layout.addWidget(self.status_label)

        self.search_edit.returnPressed.connect(self.find_next)
        self.next_button.clicked.connect(self.find_next)
        self.replace_button.clicked.connect(self.replace_current)
        self.replace_all_button.clicked.connect(self.replace_all)
        self.set_replace_visible(show_replace)

    def set_replace_visible(self, visible: bool) -> None:
        self.replace_label.setVisible(visible)
        self.replace_edit.setVisible(visible)
        self.replace_button.setVisible(visible)
        self.replace_all_button.setVisible(visible)
        self.setWindowTitle("Rechercher et remplacer" if visible else "Rechercher")

    def focus_search(self) -> None:
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def find_next(self) -> bool:
        match = find_next(
            self.editor,
            self.search_edit.text(),
            case_sensitive=self.case_checkbox.isChecked(),
        )
        self.status_label.setText("" if match is not None else "Aucune occurrence trouvée.")
        return match is not None

    def replace_current(self) -> bool:
        pattern = self.search_edit.text()
        case_sensitive = self.case_checkbox.isChecked()
        if selected_replaceable_match(
            self.editor, pattern, case_sensitive=case_sensitive
        ) is None and not self.find_next():
            return False
        changed = replace_current(
            self.editor,
            pattern,
            self.replace_edit.text(),
            case_sensitive=case_sensitive,
        )
        self.find_next()
        return changed

    def replace_all(self) -> int:
        count = replace_all(
            self.editor,
            self.search_edit.text(),
            self.replace_edit.text(),
            case_sensitive=self.case_checkbox.isChecked(),
        )
        self.status_label.setText(f"{count} remplacement(s) effectué(s).")
        return count

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        event.accept()
