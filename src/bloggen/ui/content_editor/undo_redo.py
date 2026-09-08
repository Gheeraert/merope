"""The unified undo/redo stack layered on top of Tk's own (see
_on_text_modified's docstring for why)."""

from __future__ import annotations

import tkinter as tk

# Caps both Tk's own native undo/redo history (-maxundo) and the parallel
# _undo_stack/_redo_stack tracked alongside it (see _on_text_modified) —
# unbounded otherwise for the length of one editing session. Consuming a
# stale marker whose underlying Tk undo group has already aged out is
# harmless (_perform_undo/_perform_redo already tolerate edit_undo/
# edit_redo raising TclError when there's nothing left to undo/redo).
#
# Read live (module-attribute access, not a plain value-copying import) by
# window.py's __init__ when constructing the Text widget, specifically so a
# test can monkeypatch bloggen.ui.content_editor.undo_redo._MAX_UNDO_HISTORY
# and have it actually take effect there too.
_MAX_UNDO_HISTORY = 500


class UndoRedoMixin:
    """The unified undo/redo stack layered on top of Tk's own (see
    _on_text_modified's docstring for why)."""

    def _char_count(self) -> int:
        return int(self.text.count("1.0", "end", "chars")[0])

    def _chars_between(self, start: str, end: str) -> int:
        """Like ``self.text.count(start, end, "chars")[0]`` but tolerant of
        Tk returning ``None`` (instead of ``0``) when the two indices
        coincide."""
        result = self.text.count(start, end, "chars")
        return int(result[0]) if result else 0

    @staticmethod
    def _trim_undo_stack(stack: list) -> None:
        overflow = len(stack) - _MAX_UNDO_HISTORY
        if overflow > 0:
            del stack[:overflow]

    def _on_text_modified(self, _event: tk.Event | None = None) -> None:
        """Track every insert/delete as one coalesced "text" marker on our
        own undo stack, so it interleaves in the right order with the
        "format" markers pushed by :meth:`_push_format_undo`. Consecutive
        edits of the same kind (insert-only, or delete-only) are folded
        into a single marker, matching how Tk itself groups them into one
        native undo step (a switch between inserting and deleting — or an
        explicit ``edit_separator()`` — is what starts a new Tk group).
        """
        if not self.text.edit_modified():
            return
        self.text.edit_modified(False)
        new_count = self._char_count()
        if self._suppress_undo_tracking:
            self._last_char_count = new_count
            self._current_edit_kind = None
            return
        self._dirty = True
        if new_count > self._last_char_count:
            kind = "insert"
        elif new_count < self._last_char_count:
            kind = "delete"
        else:
            kind = self._current_edit_kind or "insert"
        if kind != self._current_edit_kind:
            self._push_text_marker(self._pending_delete if kind == "delete" else None)
        if kind != "delete":
            self._pending_delete = None
        self._current_edit_kind = kind
        self._last_char_count = new_count

    def _push_text_marker(self, delete_info: dict | None) -> None:
        """Common tail of both a plain text edit and the start of a delete
        streak: separate it from whatever came before on Tk's own undo
        stack too, so Ctrl+Z/Ctrl+Y never merge unrelated edits together.
        """
        self.text.edit_separator()
        self._undo_stack.append(("text", delete_info))
        self._trim_undo_stack(self._undo_stack)
        self._redo_stack.clear()
        self._dirty = True

    def _capture_before_delete(self, start: str, end: str) -> None:
        """Record the tags carried by ``self.text[start:end]`` right before
        it gets deleted (by BackSpace/Delete/Cut/typing or pasting over a
        selection), so :meth:`_perform_undo` can restore them afterwards.

        Tk's native ``-undo`` mechanism (used for plain "text" markers, see
        :meth:`_on_text_modified`) only remembers characters, not
        ``tag_add``/``tag_remove`` calls — so on its own, undoing a delete
        brings the text back with none of its gras/italique/barré/exposant
        (or heading/liste/lien...) formatting. This sits alongside that
        mechanism: a Tk mark anchors the deleted span's position, and each
        tag range still present in it is recorded as a (tag, start_offset,
        end_offset) triple relative to that mark, in characters.
        """
        if self._suppress_undo_tracking or self.text.compare(start, "==", end):
            return
        if self._pending_delete is None or self._current_edit_kind != "delete":
            mark = self._new_tag("delmark")
            self.text.mark_set(mark, start)
            self.text.mark_gravity(mark, "left")
            self._pending_delete = {"mark": mark, "captures": []}
            self._push_text_marker(self._pending_delete)
            self._current_edit_kind = "delete"
        else:
            mark = self._pending_delete["mark"]
            if self.text.compare(start, "<", mark):
                shift = self._chars_between(start, mark)
                self.text.mark_set(mark, start)
                self._pending_delete["captures"] = [
                    (tag, s + shift, e + shift) for tag, s, e in self._pending_delete["captures"]
                ]
                mark = self._pending_delete["mark"]
        for tag in self.text.tag_names():
            if tag == "sel":
                continue
            # tag_nextrange only reports ranges that *start* inside the
            # search window, so it misses a tag already in progress at
            # ``start`` (e.g. deleting the middle of a bold run) — walk
            # every range of the tag instead and clip it to [start, end).
            ranges = self.text.tag_ranges(tag)
            for i in range(0, len(ranges), 2):
                r_start, r_end = ranges[i], ranges[i + 1]
                if self.text.compare(r_end, "<=", start) or self.text.compare(r_start, ">=", end):
                    continue
                seg_start = r_start if self.text.compare(r_start, ">", start) else start
                seg_end = r_end if self.text.compare(r_end, "<", end) else end
                if self.text.compare(seg_start, "<", seg_end):
                    s_off = self._chars_between(mark, seg_start)
                    e_off = self._chars_between(mark, seg_end)
                    self._pending_delete["captures"].append((tag, s_off, e_off))

    def _before_delete_backspace(self, _event: tk.Event) -> None:
        if self.text.tag_ranges("sel"):
            self._capture_before_delete(*self._selection_range())
        elif self.text.compare("insert", ">", "1.0"):
            self._capture_before_delete("insert-1c", "insert")

    def _before_delete_forward(self, _event: tk.Event) -> None:
        if self.text.tag_ranges("sel"):
            self._capture_before_delete(*self._selection_range())
        else:
            self._capture_before_delete("insert", "insert+1c")

    def _before_delete_selection(self, _event: tk.Event | None = None) -> None:
        selected = self._selection_range()
        if selected is not None:
            self._capture_before_delete(*selected)

    def _before_delete_typed(self, event: tk.Event) -> None:
        if event.char and self.text.tag_ranges("sel"):
            self._capture_before_delete(*self._selection_range())

    def _push_format_undo(self, undo_fn, redo_fn) -> None:
        """Record a pure formatting change (no character inserted/deleted)
        so it can be undone/redone alongside ordinary text edits.

        ``tag_add``/``tag_remove`` are invisible to Tk's own undo stack, so
        without an explicit separator here Tk would happily merge an insert
        made *before* this formatting change with one made *after* it into
        a single native undo group (nothing it saw told it they were
        different actions) — then a single Ctrl+Z on our "text" marker for
        the second insert would silently also erase the first, unrelated
        one. The separator keeps Tk's own grouping in sync with ours.
        """
        self.text.edit_separator()
        self._undo_stack.append(("format", undo_fn, redo_fn))
        self._trim_undo_stack(self._undo_stack)
        self._redo_stack.clear()
        self._current_edit_kind = None
        self._dirty = True

    def _restore_deleted_tags(self, delete_info: dict | None) -> None:
        """Reapply the tags :meth:`_capture_before_delete` recorded, once
        ``edit_undo`` has brought the plain characters back — Tk's own undo
        never restores them on its own.
        """
        if not delete_info:
            return
        mark = delete_info["mark"]
        for tag, s_off, e_off in delete_info["captures"]:
            if s_off == e_off:
                continue
            self.text.tag_add(tag, f"{mark}+{s_off}c", f"{mark}+{e_off}c")

    def _perform_undo(self) -> None:
        if not self._undo_stack:
            return
        entry = self._undo_stack.pop()
        if entry[0] == "text":
            try:
                self.text.edit_undo()
            except tk.TclError:
                pass
            else:
                self._restore_deleted_tags(entry[1])
        else:
            entry[1]()
        self._redo_stack.append(entry)
        self._trim_undo_stack(self._redo_stack)
        self._current_edit_kind = None
        self._last_char_count = self._char_count()

    def _perform_redo(self) -> None:
        if not self._redo_stack:
            return
        entry = self._redo_stack.pop()
        if entry[0] == "text":
            try:
                self.text.edit_redo()
            except tk.TclError:
                pass
        else:
            entry[2]()
        self._undo_stack.append(entry)
        self._trim_undo_stack(self._undo_stack)
        self._current_edit_kind = None
        self._last_char_count = self._char_count()
