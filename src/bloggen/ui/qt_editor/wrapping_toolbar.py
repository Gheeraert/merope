"""Compact action strip whose buttons wrap with the available width."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QLayout,
    QSizePolicy,
    QToolButton,
    QWidget,
)


class FlowLayout(QLayout):
    """Small Qt flow layout used by the responsive editor action strip."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        margin: int = 4,
        horizontal_spacing: int = 3,
        vertical_spacing: int = 3,
    ) -> None:
        super().__init__(parent)
        self._items = []
        self._horizontal_spacing = horizontal_spacing
        self._vertical_spacing = vertical_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, max(0, width), 0), test_only=True)[0]

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        return size + QSize(left + right, top + bottom)

    def row_count_for_width(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, max(0, width), 0), test_only=True)[1]

    def _do_layout(self, rect: QRect, *, test_only: bool) -> tuple[int, int]:
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x = effective.x()
        y = effective.y()
        row_height = 0
        rows = 0

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width()
            if row_height and next_x > effective.right() + 1:
                x = effective.x()
                y += row_height + self._vertical_spacing
                row_height = 0
                rows += 1
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._horizontal_spacing
            row_height = max(row_height, hint.height())

        if self._items:
            rows += 1
        height = y + row_height - rect.y() + bottom
        return max(0, height), rows


class WrappingToolBar(QWidget):
    """Icon-only view over QActions; command ownership stays with QAction."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.flow_layout = FlowLayout(self)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.buttons: list[QToolButton] = []
        self.actions_in_order = []

    def add_action(self, action) -> QToolButton:
        button = QToolButton(self)
        button.setAutoRaise(True)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setIconSize(QSize(20, 20))
        button.setFixedSize(30, 30)
        button.setDefaultAction(action)
        button.setAccessibleName(action.text())
        button.setAccessibleDescription(action.toolTip())
        self.flow_layout.addWidget(button)
        self.buttons.append(button)
        self.actions_in_order.append(action)
        return button

    def add_separator(self) -> QFrame:
        separator = QFrame(self)
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setFixedSize(8, 24)
        self.flow_layout.addWidget(separator)
        return separator

    def row_count_for_width(self, width: int) -> int:
        return self.flow_layout.row_count_for_width(width)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self.flow_layout.heightForWidth(width)

    def sizeHint(self) -> QSize:
        width = max(self.width(), self.minimumSizeHint().width())
        return QSize(width, self.heightForWidth(width))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.flow_layout.invalidate()
        self.updateGeometry()
