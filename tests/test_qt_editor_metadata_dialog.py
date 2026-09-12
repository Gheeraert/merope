from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog

from bloggen.ui.qt_editor.metadata_dialog import ContentMetadataDialog


@pytest.fixture(scope="module", autouse=True)
def qapplication():
    yield QApplication.instance() or QApplication([])


def test_page_dialog_preserves_unknown_and_removes_known_empty_fields():
    dialog = ContentMetadataDialog(
        kind="page",
        initial={
            "title": "Ancien",
            "slug": "ancien",
            "description": "à retirer",
            "date": "2020-01-01",
            "custom-field": "exact",
        },
        existing_slugs={"ancien"},
        own_slug="ancien",
        slugify_mode="ascii",
    )
    dialog.title_edit.setText("Nouveau")
    dialog.description_edit.clear()
    dialog._accept_if_valid()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.result_metadata() == {
        "title": "Nouveau",
        "slug": "ancien",
        "type": "page",
        "custom-field": "exact",
    }


def test_slug_is_automatic_until_manually_edited():
    dialog = ContentMetadataDialog(
        kind="page",
        initial={},
        existing_slugs={"bossuet"},
        slugify_mode="ascii",
    )
    dialog.title_edit.setText("Bossuet")
    assert dialog.slug_edit.text() == "bossuet-2"

    dialog.slug_edit.setText("slug-manuel")
    dialog._disable_automatic_slug("slug-manuel")
    dialog.title_edit.setText("Autre titre")
    assert dialog.slug_edit.text() == "slug-manuel"


def test_post_defaults_date_and_serializes_draft():
    dialog = ContentMetadataDialog(
        kind="post",
        initial={},
        existing_slugs=set(),
        slugify_mode="ascii",
    )
    dialog.title_edit.setText("Billet")
    dialog.draft_check.setChecked(True)
    dialog._accept_if_valid()

    result = dialog.result_metadata()
    assert result is not None
    assert result["date"]
    assert result["draft"] == "true"


def test_dialog_excludes_only_the_slug_owned_by_current_file(monkeypatch):
    warnings = []
    monkeypatch.setattr(
        "bloggen.ui.qt_editor.metadata_dialog.QMessageBox.warning",
        lambda *args, **kwargs: warnings.append(str(args[2])),
    )
    dialog = ContentMetadataDialog(
        kind="page",
        initial={"title": "Page", "slug": "nouvelle-valeur", "type": "page"},
        existing_slugs={"slug-propre", "nouvelle-valeur"},
        own_slug="slug-propre",
        slugify_mode="ascii",
    )

    dialog._accept_if_valid()

    assert dialog.result() == QDialog.DialogCode.Rejected
    assert warnings and "déjà utilisé" in warnings[0]
