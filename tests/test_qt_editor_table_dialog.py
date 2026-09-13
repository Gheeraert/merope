from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog

from bloggen.ui.qt_editor.table_dialog import TableInsertDialog


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    return QApplication.instance() or QApplication([])


def test_table_dialog_defaults_and_limits():
    dialog = TableInsertDialog()

    assert dialog.dimensions() == (2, 2)
    for spinbox in (dialog.rows_spin, dialog.columns_spin):
        assert spinbox.minimum() == 1
        assert spinbox.maximum() == 50
        assert spinbox.toolTip()


def test_table_dialog_accept_returns_selected_dimensions():
    dialog = TableInsertDialog()
    dialog.rows_spin.setValue(7)
    dialog.columns_spin.setValue(4)

    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.dimensions() == (7, 4)


def test_table_dialog_cancel_rejects_without_changing_dimensions():
    dialog = TableInsertDialog()
    dialog.rows_spin.setValue(3)
    dialog.columns_spin.setValue(5)

    dialog.reject()

    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog.dimensions() == (3, 5)
