"""WYSIWYG content editor package: create/edit pages and posts as real
Markdown files.

Split by concern into sibling modules (autosave, undo_redo, notes,
typography, paste, file_ops, formatting, blocks, dialogs, window) — see
window.py's ``ContentEditorWindow`` docstring for the full picture. This
``__init__`` re-exports the public names other modules import, so
``from bloggen.ui.content_editor import ContentEditorWindow`` (and the
two dialog classes) keeps working exactly as before the split.
"""

from __future__ import annotations

from tkinter import filedialog, messagebox

from bloggen.markdown.html_paste_import import html_to_blocks

from .dialogs import ContentMetadataDialog, FindReplaceDialog
from .file_ops import _MAX_VERSIONS_PER_DOCUMENT, _VERSION_PURGE_PROMPT_INTERVAL
from .undo_redo import _MAX_UNDO_HISTORY
from .window import ContentEditorWindow

__all__ = [
    "ContentEditorWindow",
    "ContentMetadataDialog",
    "FindReplaceDialog",
]
