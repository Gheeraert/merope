"""Modal Qt editor for the known Mérope front-matter fields."""

from __future__ import annotations

from datetime import date

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from bloggen.content.catalog import validate_editor_metadata
from bloggen.content.writer import suggest_slug


class ContentMetadataDialog(QDialog):
    """Edit known metadata while preserving every unknown key."""

    def __init__(
        self,
        *,
        kind: str,
        initial: dict[str, str],
        existing_slugs: set[str],
        slugify_mode: str,
        own_slug: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if kind not in {"page", "post"}:
            raise ValueError("Type de contenu inconnu.")
        self.kind = kind
        self.initial = dict(initial)
        self.existing_slugs = set(existing_slugs)
        self.slugify_mode = slugify_mode
        self.own_slug = own_slug
        self._slug_auto = not bool(initial.get("slug", "").strip())
        self._result_metadata: dict[str, str] | None = None
        self.setWindowTitle("Métadonnées du billet" if kind == "post" else "Métadonnées de la page")

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.type_label = QLabel("Billet" if kind == "post" else "Page", self)
        form.addRow("Type", self.type_label)
        self.title_edit = self._line(form, "Titre", initial.get("title", ""))
        self.slug_edit = self._line(form, "Slug", initial.get("slug", ""))
        self.date_edit = self._line(
            form,
            "Date (AAAA-MM-JJ)",
            initial.get("date", date.today().isoformat()),
        )
        self.date_edit.setVisible(kind == "post")
        form.labelForField(self.date_edit).setVisible(kind == "post")
        self.updated_edit = self._line(form, "Mis à jour le", initial.get("updated", ""))
        self.author_edit = self._line(form, "Auteur", initial.get("author", ""))
        self.orcid_edit = self._line(form, "ORCID", initial.get("orcid", ""))
        self.keywords_edit = self._line(form, "Mots-clés", initial.get("keywords", ""))
        self.description_edit = self._line(form, "Description", initial.get("description", ""))
        self.layout_edit = self._line(form, "Layout", initial.get("layout", ""))
        self.draft_check = QCheckBox("Brouillon (ne pas publier)", self)
        self.draft_check.setChecked(initial.get("draft", "false").strip().lower() == "true")
        form.addRow("", self.draft_check)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.title_edit.textChanged.connect(self._update_automatic_slug)
        self.slug_edit.textEdited.connect(self._disable_automatic_slug)

    @staticmethod
    def _line(form: QFormLayout, label: str, value: str) -> QLineEdit:
        edit = QLineEdit(value)
        form.addRow(label, edit)
        return edit

    def _disable_automatic_slug(self, _text: str) -> None:
        self._slug_auto = False

    def _update_automatic_slug(self, title: str) -> None:
        if not self._slug_auto:
            return
        existing = self.existing_slugs - ({self.own_slug} if self.own_slug else set())
        self.slug_edit.setText(
            suggest_slug(title, mode=self.slugify_mode, existing=existing)
        )

    def candidate_metadata(self) -> dict[str, str]:
        result = dict(self.initial)
        values = {
            "title": self.title_edit.text().strip(),
            "slug": self.slug_edit.text().strip(),
            "updated": self.updated_edit.text().strip(),
            "author": self.author_edit.text().strip(),
            "orcid": self.orcid_edit.text().strip(),
            "keywords": self.keywords_edit.text().strip(),
            "description": self.description_edit.text().strip(),
            "layout": self.layout_edit.text().strip(),
        }
        for key, value in values.items():
            if value:
                result[key] = value
            else:
                result.pop(key, None)
        result["type"] = self.kind
        if self.kind == "post":
            result["date"] = self.date_edit.text().strip()
        else:
            result.pop("date", None)
        if self.draft_check.isChecked():
            result["draft"] = "true"
        else:
            result.pop("draft", None)
        return result

    def _accept_if_valid(self) -> None:
        try:
            self._result_metadata = validate_editor_metadata(
                self.candidate_metadata(),
                self.kind,
                existing_slugs=self.existing_slugs,
                own_slug=self.own_slug,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Métadonnées", str(exc))
            return
        self.accept()

    def result_metadata(self) -> dict[str, str] | None:
        return None if self._result_metadata is None else dict(self._result_metadata)
