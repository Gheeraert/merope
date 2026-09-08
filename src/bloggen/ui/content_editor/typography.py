"""Auto-formatting applied as the user types: French typographic
quotes/spacing, century ordinals, ((note)) shorthand."""

from __future__ import annotations

import re
from tkinter import messagebox
import tkinter as tk
from bloggen.markdown.note_shortcuts import strip_runs
from bloggen.markdown.typography import (
    CENTURY_RE,
    CLOSING_GUILLEMET,
    COMMON_CENTURY_ORDINAL_TYPED_RE,
    DOUBLE_PUNCTUATION,
    NBSP,
    OE_LIGATURE_TYPED_RE,
    OPENING_GUILLEMET,
    PAGE_ABBREVIATION_TYPED_RE,
    SPACE_BEFORE_PERIOD_TYPED_RE,
    convert_curly_quotes_to_guillemets,
    convert_straight_quotes_stateful,
    fix_double_punctuation_spacing,
    fix_guillemet_spacing,
    fix_page_number_spacing,
    fix_period_spacing,
    is_valid_century_ordinal,
    oe_ligature_replacement,
)

_TYPOGRAPHY_TRIGGER_CHARS = '"' + OPENING_GUILLEMET + CLOSING_GUILLEMET + DOUBLE_PUNCTUATION
# Same shorthand as bloggen.markdown.note_shortcuts.DOUBLE_PAREN_NOTE_RE, but
# anchored to the end of the string: used to detect the pattern right as its
# closing "))" is typed, one line-prefix at a time.
_DOUBLE_PAREN_NOTE_TYPED_RE = re.compile(r"\(\((.+?)\)\)$")


class TypographyMixin:
    """Auto-formatting applied as the user types: French typographic
    quotes/spacing, century ordinals, ((note)) shorthand."""

    def _current_line_is_raw(self) -> bool:
        line = self._current_line()
        tags = set(self.text.tag_names(f"{line}.0"))
        return "table_source" in tags or "verbatim" in tags

    def _on_key_release(self, event: tk.Event) -> None:
        self._update_toolbar_char_state()
        self._update_toolbar_block_state()
        if self._current_line_is_raw():
            return
        char = event.char
        if char and char in _TYPOGRAPHY_TRIGGER_CHARS:
            self._autoformat_last_typed_char(char)
        self._autoformat_century_ordinal()
        if char == ")":
            self._autoformat_double_paren_note()
        elif char.isdigit():
            self._autoformat_page_number_space()
        elif char == ".":
            self._autoformat_period_spacing()
        elif char.isalpha():
            self._autoformat_oe_ligature()
            if char == "e":
                self._autoformat_common_century_ordinal()

    def _autoformat_last_typed_char(self, char: str) -> None:
        # Index expressions with arithmetic (e.g. "1.8-1c") are re-evaluated
        # against the *current* buffer on every call, so they silently drift
        # once a delete/insert has changed the line's length. Resolve each
        # index to a concrete "line.col" string up front and reuse only that.
        insert_index = self.text.index("insert")
        char_index = self.text.index(f"{insert_index}-1c")

        if char == '"':
            self.text.delete(char_index, insert_index)
            if self._quote_parity_opening:
                self.text.insert(char_index, OPENING_GUILLEMET + NBSP)
            else:
                self.text.insert(char_index, NBSP + CLOSING_GUILLEMET)
            self._quote_parity_opening = not self._quote_parity_opening
            return

        if char == OPENING_GUILLEMET:
            self.text.insert(insert_index, NBSP)
            return
        if char == CLOSING_GUILLEMET:
            self.text.insert(char_index, NBSP)
            return

        if char in DOUBLE_PUNCTUATION:
            preceding_index = self.text.index(f"{char_index}-1c")
            preceding = self.text.get(preceding_index, char_index)
            if preceding == NBSP:
                return
            if preceding == " ":
                self.text.delete(preceding_index, char_index)
                self.text.insert(preceding_index, NBSP)
            else:
                self.text.insert(char_index, NBSP)

    def _autoformat_century_ordinal(self) -> None:
        """Detect "<numeral>er/e siecle" just typed (e.g. "XXIe siecle") and
        superscript the ordinal suffix in place, matching the same rule
        used for pasted/imported content (:func:`bloggen.markdown.
        typography.split_century_ordinals`).
        """
        cursor = self.text.index("insert")
        line = int(cursor.split(".")[0])
        text_before = self.text.get(f"{line}.0", cursor)
        # .search() would only ever find the first match on the line, so a
        # second (still unconverted) occurrence would be permanently
        # skipped once the first is tagged; check every match instead.
        for match in CENTURY_RE.finditer(text_before):
            numeral, suffix = match.group(1), match.group(2)
            if not is_valid_century_ordinal(numeral, suffix):
                continue

            chars_after_suffix_start = len(text_before) - match.start(2)
            chars_after_suffix_end = len(text_before) - match.end(2)
            suffix_start = self.text.index(f"{cursor}-{chars_after_suffix_start}c")
            suffix_end = self.text.index(f"{cursor}-{chars_after_suffix_end}c")
            if "superscript" in self.text.tag_names(suffix_start):
                continue
            self.text.tag_add("superscript", suffix_start, suffix_end)

    def _autoformat_common_century_ordinal(self) -> None:
        """Superscript the "e" just typed right after one of the century
        numerals used most often (XVe, XVIe, XVIIe, XIIIe, XIXe, XXe,
        XXIe), the instant it's completed — unlike
        :meth:`_autoformat_century_ordinal` above (which mirrors the
        paste/import rule and needs a following "siecle" to trigger), this
        fires on the numeral alone so the superscript appears immediately
        even when "siecle" is never typed (e.g. "l'art XVe").
        """
        cursor = self.text.index("insert")
        line = int(cursor.split(".")[0])
        text_before = self.text.get(f"{line}.0", cursor)
        if COMMON_CENTURY_ORDINAL_TYPED_RE.search(text_before) is None:
            return
        suffix_start = self.text.index(f"{cursor}-1c")
        if "superscript" in self.text.tag_names(suffix_start):
            return
        self.text.tag_add("superscript", suffix_start, cursor)

    def _autoformat_page_number_space(self) -> None:
        """Detect a page number's first digit just typed right after
        "p. "/"pp. " (e.g. "p. 12") and turn that regular space into a
        non-breaking one in place, the same convention as the NBSP already
        enforced before ``; : ! ?`` — see :func:`bloggen.markdown.
        typography.fix_page_number_spacing`, applied the same way to
        pasted/imported content.
        """
        cursor = self.text.index("insert")
        line = int(cursor.split(".")[0])
        text_before = self.text.get(f"{line}.0", cursor)
        if PAGE_ABBREVIATION_TYPED_RE.search(text_before) is None:
            return
        # The digit just typed is the last character; the space to convert
        # is the one right before it.
        space_start = self.text.index(f"{cursor}-2c")
        space_end = self.text.index(f"{cursor}-1c")
        self.text.delete(space_start, space_end)
        self.text.insert(space_start, NBSP)

    def _autoformat_period_spacing(self) -> None:
        """French typography never puts a space before a period, unlike
        ``; : ! ?`` (which take a non-breaking one) — strip whatever run of
        regular/non-breaking spaces the "." just typed landed after, same
        rule as :func:`bloggen.markdown.typography.fix_period_spacing`
        applied to pasted/imported content.
        """
        cursor = self.text.index("insert")
        line = int(cursor.split(".")[0])
        text_before = self.text.get(f"{line}.0", cursor)
        match = SPACE_BEFORE_PERIOD_TYPED_RE.search(text_before)
        if match is None:
            return
        space_start = self.text.index(f"{cursor}-{len(text_before) - match.start()}c")
        period_index = self.text.index(f"{cursor}-1c")
        self.text.delete(space_start, period_index)

    def _autoformat_oe_ligature(self) -> None:
        """Detect one of the common French "oe" words just completed (e.g.
        "soeur", "oeuvre", "boeuf") and replace the digraph in place with
        the œ ligature, same rule as :func:`bloggen.markdown.typography.
        oe_ligature_replacement` applied to pasted/imported content.
        """
        cursor = self.text.index("insert")
        line = int(cursor.split(".")[0])
        text_before = self.text.get(f"{line}.0", cursor)
        match = OE_LIGATURE_TYPED_RE.search(text_before)
        if match is None:
            return
        word = match.group(1)
        replacement = oe_ligature_replacement(word)
        if replacement == word:
            return
        word_start = self.text.index(f"{cursor}-{len(word)}c")
        self.text.delete(word_start, cursor)
        self.text.insert(word_start, replacement)

    def _autoformat_double_paren_note(self) -> None:
        """Detect "((note text))" (Hypothèses/WordPress note shorthand)
        just completed by the closing "))" that triggered this call, and
        replace it in place with a real footnote reference — same
        conversion as :func:`bloggen.markdown.note_shortcuts.
        split_double_paren_notes` applied to pasted/imported content, but
        driven off the live cursor instead of a static block tree. Not
        gated on what follows (space, punctuation, end of line...): the
        note is often placed right before the sentence's closing
        punctuation, e.g. "((note)).".
        """
        cursor = self.text.index("insert")
        line = int(cursor.split(".")[0])
        text_before = self.text.get(f"{line}.0", cursor)
        match = _DOUBLE_PAREN_NOTE_TYPED_RE.search(text_before)
        if match is None:
            return

        # Resolve indices up front from the *current* buffer, for the same
        # reason as _autoformat_last_typed_char: they must not be
        # re-evaluated after the delete/insert below has changed line length.
        chars_after_start = len(text_before) - match.start()
        chars_after_note_start = len(text_before) - match.start(1)
        chars_after_note_end = len(text_before) - match.end(1)
        start_index = self.text.index(f"{cursor}-{chars_after_start}c")
        note_start_index = self.text.index(f"{cursor}-{chars_after_note_start}c")
        note_end_index = self.text.index(f"{cursor}-{chars_after_note_end}c")

        # Extracted with tags intact (not the plain text_before string
        # above), so formatting applied while typing the note — e.g. an
        # italicized title — survives into the footnote definition instead
        # of being flattened to plain text.
        note_runs = strip_runs(self._extract_runs(note_start_index, note_end_index))
        if not any(run.text for run in note_runs):
            return

        self.text.delete(start_index, cursor)
        note_id = self._register_new_footnote(note_runs)
        self._insert_footnote_marker(start_index, note_id)
        self._refresh_notes_panel()

    def _apply_typography_to_selection(self) -> None:
        """Same rules as :func:`bloggen.markdown.typography.apply_french_typography`,
        but rewrites the selection run by run (each contiguous stretch of
        unchanged Tk tags) instead of as one flat string, so that character
        formatting (bold/italic/strike/links...) and block formatting
        (blockquote, headings, alignment...) already on the selection survive
        the edit. Quote-parity tracking still threads across runs, matching
        :func:`bloggen.markdown.html_paste_import._normalize_typography`,
        which applies the same rules run by run for pasted content.
        """
        selected = self._selection_range()
        if selected is None:
            messagebox.showinfo("Typographie", "Sélectionnez d'abord le texte à corriger.")
            return
        start, end = selected
        runs = self._dump_tagged_runs(start, end)
        if not runs:
            return

        fixed_runs: list[tuple[frozenset[str], str, str, str]] = []
        opening_next = True
        changed = False
        counters = {
            "guillemets": 0,
            "espaces": 0,
            "ponctuation": 0,
            "numeros_page": 0,
            "avant_point": 0,
        }
        for tags, text, run_start, run_end in runs:
            step = convert_curly_quotes_to_guillemets(text)
            step, opening_next = convert_straight_quotes_stateful(step, opening_next=opening_next)
            if step != text:
                counters["guillemets"] += 1
            after_quotes = step

            step = fix_guillemet_spacing(step)
            if step != after_quotes:
                counters["espaces"] += 1
            after_spacing = step

            step = fix_double_punctuation_spacing(step)
            if step != after_spacing:
                counters["ponctuation"] += 1
            after_punctuation = step

            step = fix_page_number_spacing(step)
            if step != after_punctuation:
                counters["numeros_page"] += 1
            after_page_number = step

            step = fix_period_spacing(step)
            if step != after_page_number:
                counters["avant_point"] += 1

            fixed = step
            if fixed != text:
                changed = True
            fixed_runs.append((tags, fixed, run_start, run_end))

        if not changed:
            messagebox.showinfo(
                "Typographie",
                "Aucune correction nécessaire : la sélection respecte déjà les règles "
                "typographiques.",
            )
            return

        # Rewrite runs back-to-front: editing a run never changes the
        # widget indices of anything before it, so the start/end positions
        # captured above (against the original, unedited content) stay
        # valid for every run still to come.
        for tags, fixed, run_start, run_end in reversed(fixed_runs):
            self.text.delete(run_start, run_end)
            self.text.insert(run_start, fixed)
            for tag in tags:
                if tag == "sel":
                    continue
                self.text.tag_add(tag, run_start, f"{run_start}+{len(fixed)}c")

        labels = {
            "guillemets": "Guillemets convertis en chevrons français",
            "espaces": "Espaces autour des guillemets corrigées",
            "ponctuation": "Espaces insécables ajoutées avant ; : ! ?",
            "numeros_page": "Espaces insécables ajoutées dans les numéros de page",
            "avant_point": "Espaces supprimées avant les points",
        }
        lines = [f"• {labels[key]}" for key, count in counters.items() if count]
        messagebox.showinfo(
            "Typographie",
            "Corrections appliquées à la sélection :\n" + "\n".join(lines),
        )

    def _dump_tagged_runs(
        self, start: str, end: str
    ) -> list[tuple[frozenset[str], str, str, str]]:
        """Split ``start``..``end`` into runs of unbroken tag combinations,
        in document order: each run is ``(tags, text, run_start, run_end)``.
        """
        runs: list[tuple[frozenset[str], str, str, str]] = []
        active: set[str] = set()
        run_start = start
        run_text: list[str] = []
        for key, value, index in self.text.dump(start, end, tag=True, text=True):
            if key == "text":
                run_text.append(value)
                continue
            if run_text:
                runs.append((frozenset(active), "".join(run_text), run_start, index))
            run_text = []
            run_start = index
            if key == "tagon":
                active.add(value)
            elif key == "tagoff":
                active.discard(value)
        if run_text:
            runs.append((frozenset(active), "".join(run_text), run_start, end))
        return runs

    # -- rich paste (Word / Google Docs) -------------------------------------
