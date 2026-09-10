"""The file list panel, and opening/importing/deleting/converting/
creating/saving documents (including .versions archiving)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from tkinter import messagebox, filedialog, simpledialog
from bloggen.content.metadata import is_valid_iso_date
from bloggen.content.versioning import (
    MAX_VERSIONS_PER_DOCUMENT,
    VERSION_PURGE_PROMPT_INTERVAL,
    VERSIONS_DIRNAME,
    archive_previous_version,
    convert_content_file,
    list_versions,
    purge_versions,
    versions_to_purge,
)
from bloggen.content.writer import (
    default_filename,
    read_content_file,
    scan_existing_slugs,
    write_content_file,
)
from bloggen.markdown.front_matter import parse_front_matter
from bloggen.markdown.rich_text_export import blocks_to_markdown
from bloggen.markdown.rich_text_import import markdown_to_blocks
from bloggen.ui.editor_recovery import clear_draft
from .dialogs import ContentMetadataDialog

# Name of the sibling folder (next to the .md file itself) where each save
# archives the previous on-disk version before overwriting it.
_VERSIONS_DIRNAME = VERSIONS_DIRNAME
# .versions/ grows by one file per save, for the life of a document —
# every _VERSION_PURGE_PROMPT_INTERVAL saves, the user is offered the
# choice to prune the oldest ones down to _MAX_VERSIONS_PER_DOCUMENT.
# Never automatic: a user who wants every single version kept forever
# can simply decline every time, indefinitely — this only ever deletes
# on an explicit "yes".
_MAX_VERSIONS_PER_DOCUMENT = MAX_VERSIONS_PER_DOCUMENT
_VERSION_PURGE_PROMPT_INTERVAL = VERSION_PURGE_PROMPT_INTERVAL


class FileOpsMixin:
    """The file list panel, and opening/importing/deleting/converting/
    creating/saving documents (including .versions archiving)."""

    def _refresh_file_list(self) -> None:
        self.file_listbox.delete(0, "end")
        self._file_entries = []
        entries: list[tuple[str, str, Path]] = []  # (kind, title, path)
        for kind, directory in (("page", self.pages_dir), ("post", self.posts_dir)):
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*.md")):
                if _VERSIONS_DIRNAME in path.parts:
                    continue
                try:
                    result = parse_front_matter(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    entries.append((kind, f"(invalide) {path.name}", path))
                    continue
                title = result.metadata.get("title") or path.stem
                entries.append((kind, title, path))

        for kind, title, path in entries:
            label = "Page" if kind == "page" else "Billet"
            self.file_listbox.insert("end", f"[{label}] {title}")
            self._file_entries.append((kind, path))

    def _selected_entry(self) -> tuple[str, Path] | None:
        selection = self.file_listbox.curselection()
        if not selection:
            return None
        return self._file_entries[selection[0]]

    def _open_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        if not self._confirm_discard_changes():
            return
        kind, path = entry
        metadata, body = read_content_file(path)
        blocks = markdown_to_blocks(body)
        self._populate_from_blocks(blocks)
        self.metadata = metadata
        self.current_kind = kind
        self.current_path = path
        # The previous document's in-progress state, if any, was just
        # confirmed discarded above — its stale draft must not resurface
        # as a "recover this?" prompt after a later, unrelated crash.
        clear_draft(self.project_root)

    def _import_markdown_file(self) -> None:
        source = filedialog.askopenfilename(
            title="Importer un fichier Markdown",
            filetypes=[("Markdown", "*.md *.markdown"), ("Tous les fichiers", "*.*")],
        )
        if not source:
            return
        try:
            text = Path(source).read_text(encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Importer", f"Impossible de lire le fichier :\n{exc}")
            return

        result = parse_front_matter(text)
        kind = result.metadata.get("type") if result.metadata.get("type") in ("page", "post") else "page"
        if not self._new_document(kind):
            return
        self._populate_from_blocks(markdown_to_blocks(result.body))
        self.metadata = dict(result.metadata)
        self.metadata.setdefault("type", kind)
        self.current_kind = kind
        # _populate_from_blocks() marks the editor clean — correct when
        # it's loading a file that's already saved (open an existing
        # entry), wrong here: an import has no corresponding file in the
        # project yet, so its content always differs from what's on
        # disk (nothing), regardless of whether the body text itself
        # triggered any edit event.
        self._dirty = True
        messagebox.showinfo(
            "Importer",
            "Fichier importé dans l'éditeur. Vérifiez/complétez les métadonnées "
            "(bouton Métadonnées...) puis enregistrez pour l'ajouter au projet.",
        )

    def _delete_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        _kind, path = entry
        if not messagebox.askyesno("Supprimer", f"Supprimer définitivement {path.name} ?"):
            return
        path.unlink(missing_ok=True)
        if self.current_path == path:
            self._new_document(self.current_kind or "page")
        self._refresh_file_list()

    def _convert_selected_kind(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            messagebox.showinfo("Convertir", "Sélectionnez d'abord une page ou un billet dans la liste.")
            return
        kind, path = entry
        new_kind = "post" if kind == "page" else "page"
        new_label, source_label = ("billet", "page") if new_kind == "post" else ("page", "billet")

        try:
            metadata, body = read_content_file(path)
        except OSError as exc:
            messagebox.showerror("Convertir", f"Impossible de lire le fichier :\n{exc}")
            return

        date_value = metadata.get("date", "").strip()
        if new_kind == "post":
            entered = simpledialog.askstring(
                "Convertir en billet",
                "Date de publication (AAAA-MM-JJ) :",
                initialvalue=date_value or date.today().isoformat(),
                parent=self,
            )
            if entered is None:
                return
            date_value = entered.strip()
            if not is_valid_iso_date(date_value):
                messagebox.showerror("Convertir", "La date doit être au format AAAA-MM-JJ.")
                return

        if not messagebox.askyesno(
            "Convertir",
            f"Transformer cette {source_label} en {new_label} ?\n\n"
            "Le fichier est déplacé vers le bon dossier et son URL change en conséquence "
            "(dossier des pages ou archive des billets). Les liens existants vers "
            "l'ancienne adresse ne sont pas mis à jour automatiquement.",
            parent=self,
        ):
            return

        target_dir = self.posts_dir if new_kind == "post" else self.pages_dir
        try:
            conversion = convert_content_file(
                path,
                new_kind=new_kind,
                target_dir=target_dir,
                date_value=date_value,
                metadata=metadata,
                body=body,
            )
        except OSError as exc:
            messagebox.showerror("Convertir", f"Impossible d'écrire le fichier :\n{exc}")
            return
        written = conversion.path
        metadata = conversion.metadata

        if self.current_path == path:
            self.current_path = written
            self.current_kind = new_kind
            self.metadata = metadata

        self._refresh_file_list()
        messagebox.showinfo("Convertir", f"Converti en {new_label} : {written}")

    def _new_document(self, kind: str) -> bool:
        """Returns False (leaving the editor untouched) if there were
        unsaved changes and the user declined to discard them."""
        if not self._confirm_discard_changes():
            return False
        self._destroy_embedded_images()
        self.text.delete("1.0", "end")
        self.footnote_definitions.clear()
        self.link_data.clear()
        self.footnote_ref_data.clear()
        self._note_link_data.clear()
        self._footnote_text_widgets.clear()
        self.metadata = {}
        self.current_kind = kind
        self.current_path = None
        self._quote_parity_opening = True
        self._refresh_notes_panel()
        self.text.edit_reset()
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._current_edit_kind = None
        self._last_char_count = self._char_count()
        self._dirty = False
        # The previous document's in-progress state, if any, is gone
        # (confirmed above) — its stale draft must not resurface as a
        # "recover this?" prompt after a later, unrelated crash.
        clear_draft(self.project_root)
        return True

    def _destroy_embedded_images(self) -> None:
        # Text.delete() does not destroy windows embedded via window_create;
        # left alone they'd leak as orphaned Tk widgets on every reload.
        for path in self.text.window_names():
            widget = self.text.nametowidget(path)
            widget.destroy()

    # -- metadata -------------------------------------------------------------

    def _existing_slugs(self) -> set[str]:
        return scan_existing_slugs(self.pages_dir, self.posts_dir)

    def _edit_metadata(self) -> dict[str, str] | None:
        kind = self.current_kind or "page"
        dialog = ContentMetadataDialog(
            self,
            kind=kind,
            initial=self.metadata,
            existing_slugs=self._existing_slugs(),
            slugify_mode=self.slugify_mode,
        )
        if dialog.result is not None:
            self.metadata = dialog.result
            self.current_kind = kind
            self._dirty = True
        return dialog.result

    # -- toolbar actions --------------------------------------------------

    def _existing_versions(self, versions_dir: Path, path: Path) -> list[tuple[int, Path]]:
        """(version number, path) for every archived version of ``path``
        found in ``versions_dir``, sorted oldest first."""
        return list_versions(path, versions_dir)

    def _archive_previous_version(self, path: Path) -> None:
        """Before a save overwrites ``path``, copy its current on-disk
        content into a sibling ``.versions`` folder under a numbered
        filename (``slug.v1.md``, ``slug.v2.md``, ...), so past edits stay
        recoverable. No-op the first time a file is saved (nothing to
        archive yet).

        Every ``_VERSION_PURGE_PROMPT_INTERVAL`` archived versions, offers
        the user the choice to prune the oldest ones down to
        ``_MAX_VERSIONS_PER_DOCUMENT`` — never automatic, so a user who
        wants every version kept forever can simply decline each time.
        """
        result = archive_previous_version(
            path,
            prompt_interval=_VERSION_PURGE_PROMPT_INTERVAL,
        )
        if result.should_offer_purge:
            self._offer_version_purge(path, list(result.versions))

    def _offer_version_purge(self, path: Path, existing_versions: list[tuple[int, Path]]) -> None:
        """Ask the user whether to prune the oldest archived versions of
        ``path`` down to ``_MAX_VERSIONS_PER_DOCUMENT``. Declining leaves
        every version on disk untouched."""
        to_delete = versions_to_purge(
            existing_versions,
            keep=_MAX_VERSIONS_PER_DOCUMENT,
        )
        if not to_delete:
            return
        if not messagebox.askyesno(
            "Versions archivées",
            f"{path.name} compte désormais {len(existing_versions)} versions archivées.\n\n"
            f"Supprimer les {len(to_delete)} versions les plus anciennes pour n'en "
            f"conserver que {_MAX_VERSIONS_PER_DOCUMENT} ?\n\n"
            "Vous pouvez refuser pour conserver l'ensemble des versions archivées.",
        ):
            return
        purge_versions(to_delete)

    def _save(self) -> None:
        if not self.metadata.get("title") or not self.metadata.get("slug"):
            if self._edit_metadata() is None:
                return

        kind = self.current_kind or "page"
        directory = self.pages_dir if kind == "page" else self.posts_dir

        self._renumber_footnotes()
        blocks = self.extract_blocks()
        body = blocks_to_markdown(blocks)

        if self.current_path is not None:
            filename = self.current_path.name
            target_dir = self.current_path.parent
        else:
            filename = default_filename(kind, self.metadata["slug"], date=self.metadata.get("date"))
            target_dir = directory

        try:
            self._archive_previous_version(target_dir / filename)
            written = write_content_file(target_dir, filename, self.metadata, body)
        except OSError as exc:
            messagebox.showerror("Enregistrement", f"Impossible d'écrire le fichier :\n{exc}")
            return

        self.current_path = written
        self._dirty = False
        clear_draft(self.project_root)
        self._refresh_file_list()
        messagebox.showinfo("Enregistrement", f"Contenu enregistré : {written}")
