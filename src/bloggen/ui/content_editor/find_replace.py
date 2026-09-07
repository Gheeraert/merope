"""Ctrl+F/Ctrl+H find-and-replace dialog integration."""

from __future__ import annotations

from .dialogs import FindReplaceDialog


class FindReplaceMixin:
    """Ctrl+F/Ctrl+H find-and-replace dialog integration."""

    def _mark_range(self, start: str, end: str) -> tuple[str, str]:
        """Turn a snapshot of a "start"/"end" index pair into a pair of Tk
        marks, so a formatting undo/redo closure captured now still points
        at the right text later even if unrelated edits before it have
        since shifted line/column numbers.
        """
        self._tag_counter += 1
        mark_start, mark_end = f"_undo_start_{self._tag_counter}", f"_undo_end_{self._tag_counter}"
        self.text.mark_set(mark_start, start)
        self.text.mark_gravity(mark_start, "left")
        self.text.mark_set(mark_end, end)
        self.text.mark_gravity(mark_end, "right")
        return mark_start, mark_end

    def _open_find(self) -> None:
        self._show_find_dialog(show_replace=False)

    def _open_replace(self) -> None:
        self._show_find_dialog(show_replace=True)

    def _show_find_dialog(self, *, show_replace: bool) -> None:
        if self._find_dialog is not None and self._find_dialog.winfo_exists():
            self._find_dialog.destroy()
        self._find_dialog = FindReplaceDialog(self, show_replace=show_replace)

    def _replace_range_preserving_tags(self, start: str, end: str, replacement: str) -> None:
        """Delete ``start``..``end`` and insert ``replacement`` in its place,
        reapplying whatever Tk tags (bold, headings, links...) were present
        at ``start`` so a find/replace edit doesn't strip formatting.
        """
        tags = [t for t in self.text.tag_names(start) if t not in ("sel", "search_match")]
        self.text.delete(start, end)
        self.text.insert(start, replacement)
        new_end = f"{start}+{len(replacement)}c"
        for tag in tags:
            self.text.tag_add(tag, start, new_end)
