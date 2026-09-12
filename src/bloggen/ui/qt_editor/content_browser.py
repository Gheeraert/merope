"""Project content browser for the Qt editor."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from bloggen.content.catalog import ContentCatalogEntry
from bloggen.ui.qt_editor.wrapping_toolbar import WrappingButtonRow


class ContentBrowser(QWidget):
    newPageRequested = Signal()
    newPostRequested = Signal()
    openRequested = Signal()
    importRequested = Signal()
    convertRequested = Signal()
    deleteRequested = Signal()
    refreshRequested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self.list_widget = QListWidget(self)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.openRequested.emit())
        layout.addWidget(self.list_widget)

        buttons = WrappingButtonRow(self)
        specs = (
            ("Nouvelle page", self.newPageRequested),
            ("Nouveau billet", self.newPostRequested),
            ("Ouvrir", self.openRequested),
            ("Importer...", self.importRequested),
            ("Convertir page/billet", self.convertRequested),
            ("Supprimer", self.deleteRequested),
            ("Actualiser", self.refreshRequested),
        )
        self.project_buttons: list[QPushButton] = []
        for label, signal in specs:
            button = QPushButton(label, buttons)
            button.clicked.connect(
                lambda _checked=False, requested=signal: requested.emit()
            )
            buttons.add_button(button)
            self.project_buttons.append(button)
        layout.addWidget(buttons)

    def set_project_enabled(self, enabled: bool) -> None:
        for button in self.project_buttons:
            button.setEnabled(enabled)

    def set_entries(self, entries: list[ContentCatalogEntry]) -> None:
        selected_path = self.selected_entry().path if self.selected_entry() else None
        self.list_widget.clear()
        for entry in entries:
            label = "Page" if entry.kind == "page" else "Billet"
            item = QListWidgetItem(f"[{label}] {entry.title}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.list_widget.addItem(item)
            if selected_path is not None and entry.path == selected_path:
                self.list_widget.setCurrentItem(item)

    def selected_entry(self) -> ContentCatalogEntry | None:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        return value if isinstance(value, ContentCatalogEntry) else None

    def select_path(self, path: Path | None) -> None:
        if path is None:
            self.list_widget.clearSelection()
            self.list_widget.setCurrentRow(-1)
            return
        resolved = Path(path).resolve()
        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            entry = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(entry, ContentCatalogEntry) and entry.path.resolve() == resolved:
                self.list_widget.setCurrentItem(item)
                return
