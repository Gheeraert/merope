"""Qt session controller for canonical footnote definitions."""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtCore import QObject, Signal

from bloggen.content.footnotes import (
    FootnoteDefinitions,
    register_footnote,
    remove_footnote,
)
from bloggen.markdown.rich_text_model import InlineRun


def _clone_definitions(definitions: FootnoteDefinitions) -> FootnoteDefinitions:
    return {
        note_id: [replace(run) for run in runs]
        for note_id, runs in definitions.items()
    }


def plain_footnote_text(runs: list[InlineRun]) -> str | None:
    """Return concatenated text only when every run is losslessly plain."""

    for run in runs:
        if (
            run.bold
            or run.italic
            or run.strikethrough
            or run.superscript
            or run.link_href is not None
            or run.image_src is not None
            or run.image_alt is not None
            or run.image_width is not None
            or run.image_height is not None
            or run.image_align is not None
            or run.footnote_ref is not None
        ):
            return None
    return "".join(run.text for run in runs)


@dataclass(frozen=True, slots=True)
class FootnoteStoreSnapshot:
    definitions: FootnoteDefinitions
    clean_definitions: FootnoteDefinitions


class FootnoteStore(QObject):
    """Own definitions and compare them with the last loaded/saved state."""

    changed = Signal()
    modifiedChanged = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._definitions: FootnoteDefinitions = {}
        self._clean_definitions: FootnoteDefinitions = {}

    @property
    def definitions(self) -> FootnoteDefinitions:
        return _clone_definitions(self._definitions)

    @property
    def modified(self) -> bool:
        return self._definitions != self._clean_definitions

    def definition(self, note_id: str) -> list[InlineRun] | None:
        runs = self._definitions.get(note_id)
        return None if runs is None else [replace(run) for run in runs]

    def load(self, definitions: FootnoteDefinitions) -> None:
        """Replace current and clean state without making the session dirty."""

        was_modified = self.modified
        self._definitions = _clone_definitions(definitions)
        self._clean_definitions = _clone_definitions(definitions)
        self.changed.emit()
        if was_modified:
            self.modifiedChanged.emit(False)

    def register(self, note_content: str | list[InlineRun]) -> str:
        definitions = self.definitions
        note_id = register_footnote(definitions, note_content)
        self._set_current(definitions)
        return note_id

    def update(self, note_id: str, runs: list[InlineRun]) -> bool:
        if note_id not in self._definitions:
            return False
        definitions = self.definitions
        definitions[note_id] = [replace(run) for run in runs]
        return self._set_current(definitions)

    def remove(self, note_id: str) -> bool:
        definitions = self.definitions
        if not remove_footnote(definitions, note_id):
            return False
        self._set_current(definitions)
        return True

    def replace_all(self, definitions: FootnoteDefinitions) -> bool:
        """Replace current definitions while retaining the clean baseline."""

        return self._set_current(definitions)

    def mark_clean(self) -> None:
        if not self.modified:
            return
        self._clean_definitions = _clone_definitions(self._definitions)
        self.modifiedChanged.emit(False)

    def snapshot(self) -> FootnoteStoreSnapshot:
        return FootnoteStoreSnapshot(
            definitions=self.definitions,
            clean_definitions=_clone_definitions(self._clean_definitions),
        )

    def restore(self, snapshot: FootnoteStoreSnapshot) -> None:
        old_modified = self.modified
        self._definitions = _clone_definitions(snapshot.definitions)
        self._clean_definitions = _clone_definitions(snapshot.clean_definitions)
        self.changed.emit()
        if old_modified != self.modified:
            self.modifiedChanged.emit(self.modified)

    def _set_current(self, definitions: FootnoteDefinitions) -> bool:
        definitions = _clone_definitions(definitions)
        if definitions == self._definitions:
            return False
        old_modified = self.modified
        self._definitions = definitions
        self.changed.emit()
        if old_modified != self.modified:
            self.modifiedChanged.emit(self.modified)
        return True
