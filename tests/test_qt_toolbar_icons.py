from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from bloggen.ui.qt_editor.toolbar_icons import toolbar_icon


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    app = QApplication.instance() or QApplication([])
    yield app


def _owner_with_palette(*, button: str, button_text: str) -> QWidget:
    owner = QWidget()
    palette = owner.palette()
    palette.setColor(QPalette.ColorRole.Button, QColor(button))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(button_text))
    owner.setPalette(palette)
    return owner


def _opaque_colors(icon: QIcon) -> list[QColor]:
    image = icon.pixmap(QSize(30, 30)).toImage()
    return [
        image.pixelColor(x, y)
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() >= 240
    ]


def _color_distance(left: QColor, right: QColor) -> int:
    return sum(
        abs(component_left - component_right)
        for component_left, component_right in zip(left.getRgb()[:3], right.getRgb()[:3])
    )


@pytest.mark.parametrize("key", ["bold", "panel_contents", "clear_format", "preview"])
@pytest.mark.parametrize(
    ("button", "button_text"),
    [
        ("#f5f5f5", "#263238"),
        ("#202124", "#f1f3f4"),
    ],
)
def test_custom_toolbar_icons_use_owner_button_text_palette(key, button, button_text):
    owner = _owner_with_palette(button=button, button_text=button_text)

    colors = _opaque_colors(toolbar_icon(owner, key))

    assert colors
    expected = QColor(button_text)
    assert min(_color_distance(color, expected) for color in colors) <= 3


def test_standard_toolbar_icons_remain_available():
    owner = QWidget()

    assert all(
        not toolbar_icon(owner, key).isNull()
        for key in ("open", "save", "undo", "redo")
    )


@pytest.mark.parametrize(
    ("mode", "state"),
    [
        (QIcon.Mode.Normal, QIcon.State.Off),
        (QIcon.Mode.Disabled, QIcon.State.Off),
        (QIcon.Mode.Active, QIcon.State.On),
        (QIcon.Mode.Selected, QIcon.State.On),
    ],
)
def test_custom_dark_palette_icon_remains_visible_in_qicon_states(mode, state):
    owner = _owner_with_palette(button="#202124", button_text="#f1f3f4")

    image = toolbar_icon(owner, "bold").pixmap(QSize(30, 30), mode, state).toImage()

    assert any(
        image.pixelColor(x, y).alpha() > 0
        for y in range(image.height())
        for x in range(image.width())
    )
