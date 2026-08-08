"""Lightweight hover tooltips for form widgets."""

from __future__ import annotations

import tkinter as tk


class Tooltip:
    """Shows a small popup with help text when the mouse hovers a widget."""

    _delay_ms = 450

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self._after_id: str | None = None
        self._popup: tk.Toplevel | None = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")

    def _on_enter(self, _event: tk.Event) -> None:
        self._schedule()

    def _on_leave(self, _event: tk.Event) -> None:
        self._cancel_scheduled()
        self._hide()

    def _schedule(self) -> None:
        self._cancel_scheduled()
        self._after_id = self.widget.after(self._delay_ms, self._show)

    def _cancel_scheduled(self) -> None:
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self) -> None:
        if self._popup is not None:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8

        popup = tk.Toplevel(self.widget)
        popup.wm_overrideredirect(True)
        popup.wm_geometry(f"+{x}+{y}")
        popup.attributes("-topmost", True)

        label = tk.Label(
            popup,
            text=self.text,
            justify="left",
            background="#ffffe0",
            foreground="#000000",
            relief="solid",
            borderwidth=1,
            wraplength=340,
            padx=6,
            pady=4,
            font=("TkDefaultFont", 9),
        )
        label.pack()
        self._popup = popup

    def _hide(self) -> None:
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None


def add_tooltip(widget: tk.Widget, text: str) -> Tooltip:
    """Attach a hover tooltip carrying an explanation + example to a widget."""
    return Tooltip(widget, text)
