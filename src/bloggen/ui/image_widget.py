"""Real, resizable, croppable image preview embedded in the content editor.

Uses Pillow for decoding/resizing/cropping (plain Tkinter cannot decode
JPEG or resize arbitrarily). ``ImageWidget`` is embedded into the editor's
``Text`` widget via ``Text.window_create``, which makes it behave like a
single character in the surrounding text flow: selectable and deletable
like any other inline content.

Image alignment (left/center/right) only affects the *published* page
(a CSS class on the generated ``<figure>``) — Tkinter's ``Text`` widget has
no notion of floating inline windows, so the editor cannot simulate the
float visually; it only shows which alignment is currently set.
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, simpledialog, ttk
import tkinter as tk

from PIL import Image, ImageTk

from bloggen.ui.tooltip import add_tooltip

_HANDLE_SIZE = 8
_CROP_HANDLE_HIT = 16
_MIN_SIZE = 40
_MAX_PREVIEW_WIDTH = 400
_MAX_CROP_PREVIEW_DIM = 700
_ALIGN_LABELS = {"left": "gauche", "center": "centré", "right": "droite"}


def copy_into_images_dir(source: Path, images_dir: Path, doc_dir: Path) -> str:
    """Copy ``source`` into ``images_dir`` (avoiding collisions) and return
    the path to reference from Markdown, relative to ``doc_dir`` (the
    directory of the post/page Markdown file the image is inserted into —
    the same base the Pandoc/TEI/site-build pipeline resolves image
    references against, so the two must agree or the generated link 404s).
    """
    images_dir.mkdir(parents=True, exist_ok=True)
    destination = images_dir / source.name
    counter = 2
    while destination.exists() and source.resolve() != destination.resolve():
        destination = images_dir / f"{source.stem}-{counter}{source.suffix}"
        counter += 1
    if not destination.exists():
        shutil.copyfile(source, destination)
    return _relative_src(destination, doc_dir)


def grab_clipboard_image() -> Image.Image | None:
    """Return the image currently on the system clipboard, if any.

    Covers both a raw bitmap (e.g. a screenshot, or an image copied from a
    browser/editor) and a copied image file (e.g. from Explorer, which puts
    a file path list on the clipboard instead of pixel data). Returns
    ``None`` on any other platform, when the clipboard holds something else
    (plain text, multiple/non-image files...), or on any grab failure —
    callers should fall back to their normal paste handling.
    """
    try:
        from PIL import ImageGrab

        content = ImageGrab.grabclipboard()
    except Exception:
        return None
    if isinstance(content, Image.Image):
        return content
    if isinstance(content, list) and len(content) == 1:
        try:
            return Image.open(content[0])
        except Exception:
            return None
    return None


def save_clipboard_image(image: Image.Image, images_dir: Path, doc_dir: Path) -> str:
    """Save a clipboard image to ``images_dir`` and return its Markdown src
    (relative to ``doc_dir``, see :func:`copy_into_images_dir`), the paste
    counterpart to :func:`copy_into_images_dir` for a file already on disk.
    """
    images_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = images_dir / f"presse-papiers-{timestamp}.png"
    counter = 2
    while destination.exists():
        destination = images_dir / f"presse-papiers-{timestamp}-{counter}.png"
        counter += 1
    if image.mode not in ("RGB", "RGBA", "L", "LA", "P"):
        image = image.convert("RGBA")
    image.save(destination, "PNG")
    return _relative_src(destination, doc_dir)


def ask_caption(parent: tk.Misc, title: str, prompt: str, initial: str = "") -> str | None:
    """Prompt for an image caption, with Gras/Italique buttons that wrap the
    current selection in ``**``/``*`` markers (kept literally through export,
    see :mod:`bloggen.markdown.rich_text_export`, so they render as real
    emphasis in the published caption while ``alt`` stays plain text).
    Returns ``None`` if the user cancels, mirroring ``simpledialog.askstring``.
    """
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.resizable(False, False)

    ttk.Label(dialog, text=prompt, wraplength=340).pack(padx=10, pady=(10, 6), anchor="w")

    text_var = tk.StringVar(value=initial)
    entry = ttk.Entry(dialog, textvariable=text_var, width=50)
    entry.pack(padx=10, pady=(0, 6), fill="x")
    entry.focus_set()
    entry.selection_range(0, "end")

    def _wrap(marker: str) -> None:
        try:
            start, end = entry.index("sel.first"), entry.index("sel.last")
        except tk.TclError:
            start = end = entry.index("insert")
        value = text_var.get()
        wrapped = f"{marker}{value[start:end]}{marker}"
        text_var.set(value[:start] + wrapped + value[end:])
        entry.selection_range(start, start + len(wrapped))
        entry.focus_set()

    toolbar = ttk.Frame(dialog)
    toolbar.pack(padx=10, pady=(0, 8), anchor="w")
    bold_button = ttk.Button(toolbar, text="G", width=3, command=lambda: _wrap("**"))
    bold_button.pack(side="left")
    add_tooltip(bold_button, "Mettre la sélection en gras.")
    italic_button = ttk.Button(toolbar, text="I", width=3, command=lambda: _wrap("*"))
    italic_button.pack(side="left", padx=(4, 0))
    add_tooltip(italic_button, "Mettre la sélection en italique.")

    result: dict[str, str | None] = {"value": None}

    def _confirm(_event: tk.Event | None = None) -> None:
        result["value"] = text_var.get()
        dialog.destroy()

    def _cancel(_event: tk.Event | None = None) -> None:
        dialog.destroy()

    buttons = ttk.Frame(dialog)
    buttons.pack(fill="x", padx=10, pady=(0, 10))
    ttk.Button(buttons, text="Valider", command=_confirm).pack(side="right")
    ttk.Button(buttons, text="Annuler", command=_cancel).pack(side="right", padx=(0, 6))

    dialog.bind("<Return>", _confirm)
    dialog.bind("<Escape>", _cancel)
    dialog.protocol("WM_DELETE_WINDOW", _cancel)
    dialog.grab_set()
    parent.wait_window(dialog)
    return result["value"]


def _relative_src(path: Path, doc_dir: Path) -> str:
    return Path(os.path.relpath(path, doc_dir)).as_posix()


def _write_cropped_copy(
    source_path: Path, box: tuple[int, int, int, int], doc_dir: Path
) -> str:
    image = Image.open(source_path)
    cropped = image.crop(box)
    counter = 1
    candidate = source_path.with_name(f"{source_path.stem}-crop{counter}{source_path.suffix}")
    while candidate.exists():
        counter += 1
        candidate = source_path.with_name(f"{source_path.stem}-crop{counter}{source_path.suffix}")
    cropped.convert("RGB").save(candidate)
    return _relative_src(candidate, doc_dir)


class ImageWidget(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        images_dir: Path,
        doc_dir: Path,
        src: str,
        alt: str = "",
        width: int | None = None,
        height: int | None = None,
        align: str | None = None,
    ) -> None:
        super().__init__(master, borderwidth=1, relief="solid")
        self.images_dir = Path(images_dir)
        self.doc_dir = Path(doc_dir)
        self.src = src
        self.alt = alt
        self.align = align
        self._resize_corner: str | None = None
        self._resize_start = (0, 0)
        self._resize_start_size = (0, 0)

        self._source_image = self._load_source_image()
        natural_width, natural_height = self._source_image.size
        if width and height:
            self.width, self.height = width, height
        else:
            self.width = min(natural_width, _MAX_PREVIEW_WIDTH)
            self.height = round(natural_height * (self.width / natural_width)) if natural_width else natural_height

        self._build_ui()
        self._render_preview()

    def _resolve_path(self) -> Path:
        return (self.doc_dir / self.src).resolve()

    def _load_source_image(self) -> Image.Image:
        try:
            return Image.open(self._resolve_path()).convert("RGB")
        except Exception:
            return Image.new("RGB", (200, 150), color="#cccccc")

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x")

        for label, value, tip in (
            ("⇐", "left", "Aligner l'image à gauche du texte."),
            ("≡", "center", "Centrer l'image."),
            ("⇒", "right", "Aligner l'image à droite du texte."),
        ):
            button = ttk.Button(toolbar, text=label, width=2, command=lambda v=value: self._set_align(v))
            button.pack(side="left")
            add_tooltip(button, tip)

        crop_button = ttk.Button(toolbar, text="Recadrer...", command=self._open_crop_dialog)
        crop_button.pack(side="left", padx=(4, 0))
        add_tooltip(crop_button, "Découpe réellement le fichier image selon une zone choisie.")

        caption_button = ttk.Button(toolbar, text="Légende...", command=self._edit_caption)
        caption_button.pack(side="left", padx=(4, 0))
        add_tooltip(
            caption_button,
            "Modifie la légende affichée sous l'image (et le texte alternatif pour l'accessibilité).",
        )

        replace_button = ttk.Button(toolbar, text="Remplacer...", command=self._replace_image)
        replace_button.pack(side="left", padx=(4, 0))
        add_tooltip(
            replace_button,
            "Remplace cette image par un autre fichier, en conservant la taille et l'alignement.",
        )

        self.align_label = ttk.Label(toolbar, text=self._align_label_text(), foreground="#777777")
        self.align_label.pack(side="left", padx=(6, 0))

        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.canvas.pack()
        self._handle_ids: dict[str, int] = {}

    def _align_label_text(self) -> str:
        return f"Alignement : {_ALIGN_LABELS.get(self.align, 'aucun (dans le texte)')}"

    def _set_align(self, value: str) -> None:
        self.align = None if self.align == value else value
        self.align_label.configure(text=self._align_label_text())

    def _render_preview(self) -> None:
        display = self._source_image.resize((max(self.width, 1), max(self.height, 1)))
        self._photo = ImageTk.PhotoImage(display)
        self.canvas.configure(width=self.width, height=self.height)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self._draw_handles()

    def _draw_handles(self) -> None:
        self._handle_ids = {}
        corners = {
            "nw": (0, 0),
            "ne": (self.width, 0),
            "sw": (0, self.height),
            "se": (self.width, self.height),
        }
        for name, (x, y) in corners.items():
            handle = self.canvas.create_rectangle(
                x - _HANDLE_SIZE // 2,
                y - _HANDLE_SIZE // 2,
                x + _HANDLE_SIZE // 2,
                y + _HANDLE_SIZE // 2,
                fill="#1a73e8",
                outline="",
            )
            self._handle_ids[name] = handle
            self.canvas.tag_bind(handle, "<ButtonPress-1>", lambda e, n=name: self._start_resize(e, n))
            self.canvas.tag_bind(handle, "<B1-Motion>", self._do_resize)
            self.canvas.tag_bind(handle, "<ButtonRelease-1>", self._end_resize)

    def _start_resize(self, event: tk.Event, corner: str) -> None:
        self._resize_corner = corner
        self._resize_start = (event.x_root, event.y_root)
        self._resize_start_size = (self.width, self.height)

    def _do_resize(self, event: tk.Event) -> None:
        if self._resize_corner is None:
            return
        dx = event.x_root - self._resize_start[0]
        start_w, start_h = self._resize_start_size
        sign = 1 if self._resize_corner in ("ne", "se") else -1
        new_width = max(_MIN_SIZE, start_w + sign * dx)
        ratio = new_width / start_w if start_w else 1
        new_height = max(_MIN_SIZE, round(start_h * ratio))
        self.width, self.height = int(new_width), int(new_height)
        self._render_preview()

    def _end_resize(self, _event: tk.Event) -> None:
        self._resize_corner = None

    def _replace_image(self) -> None:
        source = filedialog.askopenfilename(
            title="Choisir une image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.gif *.webp"), ("Tous les fichiers", "*.*")],
        )
        if not source:
            return
        self.src = copy_into_images_dir(Path(source), self.images_dir, self.doc_dir)
        self._source_image = self._load_source_image()
        self._render_preview()

    def _edit_caption(self) -> None:
        caption = ask_caption(
            self,
            "Légende",
            "Légende (affichée sous l'image sur le site publié ; laissez vide pour ne pas en mettre) :",
            initial=self.alt,
        )
        if caption is None:
            return
        self.alt = caption

    def _open_crop_dialog(self) -> None:
        dialog = CropDialog(self, image_path=self._resolve_path())
        self.wait_window(dialog)
        if dialog.result is None:
            return
        self.src = _write_cropped_copy(self._resolve_path(), dialog.result, self.doc_dir)
        self._source_image = self._load_source_image()
        self._render_preview()


class CropDialog(tk.Toplevel):
    """Modal dialog to pick a crop rectangle; on confirm, the caller writes
    an actually-cropped copy of the file (crop is destructive by nature,
    unlike the non-destructive width/height resize)."""

    def __init__(self, master: tk.Misc, *, image_path: Path) -> None:
        super().__init__(master)
        self.title("Recadrer l'image")
        self.result: tuple[int, int, int, int] | None = None

        self._original = Image.open(image_path).convert("RGB")
        orig_w, orig_h = self._original.size
        self._scale = min(1.0, _MAX_CROP_PREVIEW_DIM / max(orig_w, orig_h)) if max(orig_w, orig_h) else 1.0
        display_w, display_h = max(1, int(orig_w * self._scale)), max(1, int(orig_h * self._scale))

        display_image = self._original.resize((display_w, display_h))
        self._photo = ImageTk.PhotoImage(display_image)

        self.canvas = tk.Canvas(self, width=display_w, height=display_h, highlightthickness=0)
        self.canvas.pack(padx=8, pady=8)
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)

        inset_x, inset_y = display_w * 0.1, display_h * 0.1
        self._rect = [inset_x, inset_y, display_w - inset_x, display_h - inset_y]
        self._rect_id = self.canvas.create_rectangle(*self._rect, outline="#1a73e8", width=2)
        self._handle_ids: dict[str, int] = {}
        self._dragging_corner: str | None = None
        self._draw_handles()

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(buttons, text="Valider", command=self._confirm).pack(side="right")
        ttk.Button(buttons, text="Annuler", command=self.destroy).pack(side="right", padx=(0, 6))

        self.transient(master)
        self.grab_set()

    def _draw_handles(self) -> None:
        """Create the four corner handles once; dragging afterwards only
        repositions them (see ``_drag_corner``) rather than recreating them,
        since deleting the item currently under the pointer mid-drag stops
        Tk's canvas tag bindings — which track the "current" item by id —
        from ever firing another ``<B1-Motion>`` for that drag."""
        left, top, right, bottom = self._rect
        corners = {"nw": (left, top), "ne": (right, top), "sw": (left, bottom), "se": (right, bottom)}
        for name, (x, y) in corners.items():
            handle = self.canvas.create_rectangle(
                x - _CROP_HANDLE_HIT // 2,
                y - _CROP_HANDLE_HIT // 2,
                x + _CROP_HANDLE_HIT // 2,
                y + _CROP_HANDLE_HIT // 2,
                fill="#1a73e8",
                outline="white",
                width=1,
            )
            self._handle_ids[name] = handle
            self.canvas.tag_bind(handle, "<ButtonPress-1>", lambda e, n=name: self._start_drag(e, n))
            self.canvas.tag_bind(handle, "<B1-Motion>", self._drag_corner)
            self.canvas.tag_bind(handle, "<ButtonRelease-1>", self._end_drag)

    def _start_drag(self, _event: tk.Event, corner: str) -> None:
        self._dragging_corner = corner

    def _end_drag(self, _event: tk.Event) -> None:
        self._dragging_corner = None

    def _reposition_handles(self) -> None:
        left, top, right, bottom = self._rect
        positions = {"nw": (left, top), "ne": (right, top), "sw": (left, bottom), "se": (right, bottom)}
        for name, (x, y) in positions.items():
            handle = self._handle_ids[name]
            self.canvas.coords(
                handle,
                x - _CROP_HANDLE_HIT // 2,
                y - _CROP_HANDLE_HIT // 2,
                x + _CROP_HANDLE_HIT // 2,
                y + _CROP_HANDLE_HIT // 2,
            )

    def _drag_corner(self, event: tk.Event) -> None:
        corner = self._dragging_corner
        if corner is None:
            return
        left, top, right, bottom = self._rect
        x = max(0, min(event.x, int(self.canvas["width"])))
        y = max(0, min(event.y, int(self.canvas["height"])))
        if corner == "nw":
            left, top = min(x, right - 20), min(y, bottom - 20)
        elif corner == "ne":
            right, top = max(x, left + 20), min(y, bottom - 20)
        elif corner == "sw":
            left, bottom = min(x, right - 20), max(y, top + 20)
        elif corner == "se":
            right, bottom = max(x, left + 20), max(y, top + 20)
        self._rect = [left, top, right, bottom]
        self.canvas.coords(self._rect_id, *self._rect)
        self._reposition_handles()

    def _confirm(self) -> None:
        left, top, right, bottom = self._rect
        self.result = (
            round(left / self._scale),
            round(top / self._scale),
            round(right / self._scale),
            round(bottom / self._scale),
        )
        self.destroy()
