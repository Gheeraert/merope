"""Crash-recovery offer, autosave scheduling, unsaved-changes
confirmation, and window close/destroy lifecycle."""

from __future__ import annotations

from tkinter import messagebox
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.ui.editor_recovery import RecoveryDraft, clear_draft, load_draft, save_draft

# How often the in-progress document is autosaved to the crash-recovery
# draft while dirty — frequent enough that a crash loses at most a short
# stretch of work, infrequent enough not to matter for disk I/O.
_AUTOSAVE_INTERVAL_MS = 30_000


class AutosaveMixin:
    """Crash-recovery offer, autosave scheduling, unsaved-changes
    confirmation, and window close/destroy lifecycle."""

    def _offer_crash_recovery(self) -> None:
        draft = load_draft(self.project_root)
        if draft is None:
            return
        if not messagebox.askyesno(
            "Récupération après incident",
            "Un brouillon non enregistré a été retrouvé, probablement laissé par "
            "une fermeture inattendue de l'éditeur. Le restaurer ?",
            parent=self,
        ):
            clear_draft(self.project_root)
            return

        resolved_path = None
        if draft.current_path:
            candidate = (self.project_root / draft.current_path).resolve()
            if candidate.exists():
                resolved_path = candidate

        self._populate_from_blocks(markdown_to_blocks(draft.body_markdown))
        self.metadata = dict(draft.metadata)
        self.current_kind = draft.current_kind
        self.current_path = resolved_path
        # The restored content has no counterpart on disk that matches it
        # yet (resolved_path, if any, still holds its own last-saved
        # version) — _populate_from_blocks() marked the editor clean,
        # which is wrong here for the same reason it's wrong right after
        # an import (see _import_markdown_file).
        self._dirty = True
        clear_draft(self.project_root)
        self._refresh_file_list()

    def _schedule_autosave(self) -> None:
        self._autosave_after_id = self.after(_AUTOSAVE_INTERVAL_MS, self._autosave_tick)

    def _cancel_autosave(self) -> None:
        if self._autosave_after_id is not None:
            self.after_cancel(self._autosave_after_id)
            self._autosave_after_id = None

    def _autosave_tick(self) -> None:
        if self._dirty:
            self._write_autosave_draft()
        self._schedule_autosave()

    def _write_autosave_draft(self) -> None:
        try:
            body = blocks_to_markdown(self.extract_blocks())
        except Exception:  # noqa: BLE001 - autosave must never crash the editor
            return

        current_path_key = None
        if self.current_path is not None:
            try:
                current_path_key = self.current_path.resolve().relative_to(
                    self.project_root.resolve()
                ).as_posix()
            except ValueError:
                current_path_key = None

        draft = RecoveryDraft(
            current_path=current_path_key,
            current_kind=self.current_kind,
            metadata=dict(self.metadata),
            body_markdown=body,
        )
        try:
            save_draft(self.project_root, draft)
        except OSError:
            pass

    # -- unsaved-changes guard ---------------------------------------------

    def _confirm_discard_changes(self) -> bool:
        """Ask before an action that would replace the editor's current
        content. Returns True if it is safe to proceed (nothing unsaved,
        or the user confirmed discarding it)."""
        if not self._dirty:
            return True
        return messagebox.askyesno(
            "Modifications non enregistrées",
            "Ce contenu contient des modifications non enregistrées qui seront "
            "perdues. Continuer sans enregistrer ?",
            parent=self,
        )

    def _on_close_request(self) -> None:
        if not self._confirm_discard_changes():
            return
        # A confirmed close means the user is done with this document's
        # in-progress state one way or another (saved, or explicitly
        # accepted discarding it) — nothing left to offer recovering.
        clear_draft(self.project_root)
        self.destroy()

    def destroy(self) -> None:
        # Reached both via _on_close_request and via any direct
        # .destroy() call (parent window teardown, tests) that doesn't go
        # through it — either way, a pending autosave callback must never
        # fire against a widget that no longer exists.
        self._cancel_autosave()
        super().destroy()

    # -- layout -----------------------------------------------------------
