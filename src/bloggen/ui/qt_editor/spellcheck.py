"""French spellchecking as a transient Qt presentation layer."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)

from bloggen.markdown.rich_text_model import BLOCKQUOTE, HEADING, LIST_ITEM, PARAGRAPH
from bloggen.ui.qt_editor.constants import (
    BLOCK_KIND_PROPERTY,
    IMAGE_CAPTION_KIND,
    MEROPE_TABLE_PROPERTY,
    RAW_BLOCK_KIND_PROPERTY,
)

try:
    from spellchecker import SpellChecker as _SpellChecker
except ImportError:  # The Qt editor remains launchable without its optional extra.
    _SpellChecker = None


_LETTER = r"[^\W\d_]"
_WORD_RE = re.compile(rf"{_LETTER}+(?:['’]{_LETTER}+)*", re.UNICODE)
_EXCLUDED_RE = re.compile(
    r"(?i:(?:https?://|www\.)[^\s<>()]+"
    r"|[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"
    r"|[a-z]:\\[^\s]+)"
)
_ELISION_PREFIXES = frozenset(
    {
        "l",
        "d",
        "j",
        "m",
        "n",
        "s",
        "t",
        "c",
        "qu",
        "jusqu",
        "lorsqu",
        "puisqu",
    }
)
_EDITORIAL_BLOCK_KINDS = frozenset(
    {"", PARAGRAPH, HEADING, BLOCKQUOTE, LIST_ITEM, IMAGE_CAPTION_KIND}
)


@dataclass(frozen=True, slots=True)
class SpellingIssue:
    start: int
    length: int
    word: str


def spellcheck_available() -> bool:
    """Whether the optional pure-Python French dictionary can be loaded."""

    return _load_spellchecker() is not None


@lru_cache(maxsize=1)
def _load_spellchecker():
    """Load one read-only session dictionary for all editor windows."""

    if _SpellChecker is None:
        return None
    try:
        return _SpellChecker(language="fr", distance=1)
    except (OSError, ValueError):
        return None


class FrenchSpellChecker:
    """Find unknown French words while preserving source-text offsets."""

    def __init__(self) -> None:
        self._known_cache: dict[str, bool] = {}
        self._spellchecker = _load_spellchecker()

    @property
    def available(self) -> bool:
        return self._spellchecker is not None

    def is_known(self, word: str) -> bool:
        """Check dictionary membership without computing correction candidates."""

        if self._spellchecker is None:
            return True
        key = _dictionary_key(word)
        known = self._known_cache.get(key)
        if known is None:
            known = key in self._spellchecker.word_frequency
            self._known_cache[key] = known
        return known

    def issues(self, text: str) -> list[SpellingIssue]:
        if self._spellchecker is None:
            return []

        excluded = [(match.start(), match.end()) for match in _EXCLUDED_RE.finditer(text)]
        issues: list[SpellingIssue] = []
        for match in _WORD_RE.finditer(text):
            start, end = match.span()
            if _range_overlaps_any(start, end, excluded):
                continue
            if (start and text[start - 1].isdigit()) or (
                end < len(text) and text[end].isdigit()
            ):
                continue

            token = match.group()
            if len(token) >= 2 and token.isupper():
                continue
            if "'" not in token and "’" not in token:
                if not self.is_known(token):
                    issues.append(SpellingIssue(start, end - start, token))
                continue
            if self.is_known(token):
                continue

            components = list(re.finditer(_LETTER + "+", token, re.UNICODE))
            for index, component in enumerate(components):
                word = component.group()
                if (
                    index == 0
                    and len(components) > 1
                    and _dictionary_key(word) in _ELISION_PREFIXES
                ):
                    continue
                if not self.is_known(word):
                    issues.append(
                        SpellingIssue(
                            start + component.start(),
                            component.end() - component.start(),
                            word,
                        )
                    )
        return issues


def _dictionary_key(word: str) -> str:
    normalized = unicodedata.normalize("NFC", word).replace("’", "'").casefold()
    # pyspellchecker 0.9's French word list stores these entries as oe/oeu.
    return normalized.replace("œ", "oe")


def _range_overlaps_any(
    start: int,
    end: int,
    excluded: list[tuple[int, int]],
) -> bool:
    return any(
        start < excluded_end and end > excluded_start
        for excluded_start, excluded_end in excluded
    )


class FrenchSpellHighlighter(QSyntaxHighlighter):
    """Underline spelling issues without changing canonical character formats."""

    def __init__(
        self,
        document: QTextDocument,
        checker: FrenchSpellChecker | None = None,
    ) -> None:
        super().__init__(document)
        self.checker = checker or FrenchSpellChecker()
        self.issue_format = QTextCharFormat()
        self.issue_format.setUnderlineStyle(
            QTextCharFormat.UnderlineStyle.SpellCheckUnderline
        )
        self.issue_format.setUnderlineColor(QColor(Qt.GlobalColor.red))

    def highlightBlock(self, text: str) -> None:  # noqa: N802 - Qt virtual API
        if not self._current_block_is_editorial():
            return
        for issue in self.checker.issues(text):
            self.setFormat(issue.start, issue.length, self.issue_format)

    def _current_block_is_editorial(self) -> bool:
        block = self.currentBlock()
        if not block.isValid():
            return False
        block_format = block.blockFormat()
        if block_format.hasProperty(RAW_BLOCK_KIND_PROPERTY):
            return False

        table = QTextCursor(block).currentTable()
        if table is not None:
            table_format = table.format()
            return table_format.hasProperty(MEROPE_TABLE_PROPERTY) and bool(
                table_format.property(MEROPE_TABLE_PROPERTY)
            )

        kind = block_format.property(BLOCK_KIND_PROPERTY)
        return (kind or "") in _EDITORIAL_BLOCK_KINDS
