"""Auto-formatting applied as the user types: French typographic
quotes/spacing, century ordinals. The ``((note))`` shorthand is
deliberately left untouched here — it stays literal text while typing (so
every formatting option keeps working on it) and is only converted to a
real footnote when the Markdown is normalized, at preview/build time; see
:func:`bloggen.markdown.note_shortcuts.convert_double_paren_notes_in_markdown_text`."""

from __future__ import annotations

import re
from tkinter import messagebox
import tkinter as tk
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


class TypographyMixin:
    """Auto-formatting applied as the user types: French typographic
    quotes/spacing, century ordinals, ((note)) shorthand."""

    def _current_line_is_raw(self, widget: tk.Text) -> bool:
        line = int(widget.index("insert").split(".")[0])
        tags = set(widget.tag_names(f"{line}.0"))
        return "table_source" in tags or "verbatim" in tags

    def _on_key_release(self, event: tk.Event) -> None:
        self._update_toolbar_char_state()
        self._update_toolbar_block_state()
        if self._current_line_is_raw(self.text):
            return
        char = event.char
        self._quote_parity_opening = self._apply_typing_autoformat(
            self.text, char, opening_next=self._quote_parity_opening
        )

    def _apply_typing_autoformat(self, widget: tk.Text, char: str, *, opening_next: bool) -> bool:
        """The French-typography-as-you-type rules (quotes/guillemets,
        double-punctuation spacing, page numbers, period spacing, oe
        ligature, century ordinals) — everything :meth:`_on_key_release`
        applies to the main body. Shared with each footnote's own ``Text``
        widget (see :mod:`bloggen.ui.content_editor.notes`), which has no
        other way to get these autocorrections. Returns the updated
        quote-parity state (``opening_next``) for the caller to keep, since
        it must be tracked per widget, not globally.
        """
        if char and char in _TYPOGRAPHY_TRIGGER_CHARS:
            opening_next = self._autoformat_last_typed_char(widget, char, opening_next=opening_next)
        self._autoformat_century_ordinal(widget)
        if char.isdigit():
            self._autoformat_page_number_space(widget)
        elif char == ".":
            self._autoformat_period_spacing(widget)
        elif char.isalpha():
            self._autoformat_oe_ligature(widget)
            if char == "e":
                self._autoformat_common_century_ordinal(widget)
        return opening_next

    def _autoformat_last_typed_char(self, widget: tk.Text, char: str, *, opening_next: bool) -> bool:
        # Index expressions with arithmetic (e.g. "1.8-1c") are re-evaluated
        # against the *current* buffer on every call, so they silently drift
        # once a delete/insert has changed the line's length. Resolve each
        # index to a concrete "line.col" string up front and reuse only that.
        insert_index = widget.index("insert")
        char_index = widget.index(f"{insert_index}-1c")

        if char == '"':
            widget.delete(char_index, insert_index)
            if opening_next:
                widget.insert(char_index, OPENING_GUILLEMET + NBSP)
            else:
                widget.insert(char_index, NBSP + CLOSING_GUILLEMET)
            return not opening_next

        if char == OPENING_GUILLEMET:
            widget.insert(insert_index, NBSP)
            return opening_next
        if char == CLOSING_GUILLEMET:
            widget.insert(char_index, NBSP)
            return opening_next

        if char in DOUBLE_PUNCTUATION:
            preceding_index = widget.index(f"{char_index}-1c")
            preceding = widget.get(preceding_index, char_index)
            if preceding == NBSP:
                return opening_next
            if preceding == " ":
                widget.delete(preceding_index, char_index)
                widget.insert(preceding_index, NBSP)
            else:
                widget.insert(char_index, NBSP)
        return opening_next

    def _autoformat_century_ordinal(self, widget: tk.Text) -> None:
        """Detect "<numeral>er/e siecle" just typed (e.g. "XXIe siecle") and
        superscript the ordinal suffix in place, matching the same rule
        used for pasted/imported content (:func:`bloggen.markdown.
        typography.split_century_ordinals`).
        """
        cursor = widget.index("insert")
        line = int(cursor.split(".")[0])
        text_before = widget.get(f"{line}.0", cursor)
        # .search() would only ever find the first match on the line, so a
        # second (still unconverted) occurrence would be permanently
        # skipped once the first is tagged; check every match instead.
        for match in CENTURY_RE.finditer(text_before):
            numeral, suffix = match.group(1), match.group(2)
            if not is_valid_century_ordinal(numeral, suffix):
                continue

            chars_after_suffix_start = len(text_before) - match.start(2)
            chars_after_suffix_end = len(text_before) - match.end(2)
            suffix_start = widget.index(f"{cursor}-{chars_after_suffix_start}c")
            suffix_end = widget.index(f"{cursor}-{chars_after_suffix_end}c")
            if "superscript" in widget.tag_names(suffix_start):
                continue
            widget.tag_add("superscript", suffix_start, suffix_end)

    def _autoformat_common_century_ordinal(self, widget: tk.Text) -> None:
        """Superscript the "e" just typed right after one of the century
        numerals used most often (XVe, XVIe, XVIIe, XIIIe, XIXe, XXe,
        XXIe), the instant it's completed — unlike
        :meth:`_autoformat_century_ordinal` above (which mirrors the
        paste/import rule and needs a following "siecle" to trigger), this
        fires on the numeral alone so the superscript appears immediately
        even when "siecle" is never typed (e.g. "l'art XVe").
        """
        cursor = widget.index("insert")
        line = int(cursor.split(".")[0])
        text_before = widget.get(f"{line}.0", cursor)
        if COMMON_CENTURY_ORDINAL_TYPED_RE.search(text_before) is None:
            return
        suffix_start = widget.index(f"{cursor}-1c")
        if "superscript" in widget.tag_names(suffix_start):
            return
        widget.tag_add("superscript", suffix_start, cursor)

    def _autoformat_page_number_space(self, widget: tk.Text) -> None:
        """Detect a page number's first digit just typed right after
        "p. "/"pp. " (e.g. "p. 12") and turn that regular space into a
        non-breaking one in place, the same convention as the NBSP already
        enforced before ``; : ! ?`` — see :func:`bloggen.markdown.
        typography.fix_page_number_spacing`, applied the same way to
        pasted/imported content.
        """
        cursor = widget.index("insert")
        line = int(cursor.split(".")[0])
        text_before = widget.get(f"{line}.0", cursor)
        if PAGE_ABBREVIATION_TYPED_RE.search(text_before) is None:
            return
        # The digit just typed is the last character; the space to convert
        # is the one right before it.
        space_start = widget.index(f"{cursor}-2c")
        space_end = widget.index(f"{cursor}-1c")
        widget.delete(space_start, space_end)
        widget.insert(space_start, NBSP)

    def _autoformat_period_spacing(self, widget: tk.Text) -> None:
        """French typography never puts a space before a period, unlike
        ``; : ! ?`` (which take a non-breaking one) — strip whatever run of
        regular/non-breaking spaces the "." just typed landed after, same
        rule as :func:`bloggen.markdown.typography.fix_period_spacing`
        applied to pasted/imported content.
        """
        cursor = widget.index("insert")
        line = int(cursor.split(".")[0])
        text_before = widget.get(f"{line}.0", cursor)
        match = SPACE_BEFORE_PERIOD_TYPED_RE.search(text_before)
        if match is None:
            return
        space_start = widget.index(f"{cursor}-{len(text_before) - match.start()}c")
        period_index = widget.index(f"{cursor}-1c")
        widget.delete(space_start, period_index)

    def _autoformat_oe_ligature(self, widget: tk.Text) -> None:
        """Detect one of the common French "oe" words just completed (e.g.
        "soeur", "oeuvre", "boeuf") and replace the digraph in place with
        the œ ligature, same rule as :func:`bloggen.markdown.typography.
        oe_ligature_replacement` applied to pasted/imported content.
        """
        cursor = widget.index("insert")
        line = int(cursor.split(".")[0])
        text_before = widget.get(f"{line}.0", cursor)
        match = OE_LIGATURE_TYPED_RE.search(text_before)
        if match is None:
            return
        word = match.group(1)
        replacement = oe_ligature_replacement(word)
        if replacement == word:
            return
        word_start = widget.index(f"{cursor}-{len(word)}c")
        widget.delete(word_start, cursor)
        widget.insert(word_start, replacement)

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
