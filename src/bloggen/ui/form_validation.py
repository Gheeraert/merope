"""Small shared validation helpers for free-text numeric form fields.

Plain ``tk.StringVar`` fields parsed explicitly (rather than ``tk.IntVar``,
whose ``.get()`` raises a raw ``tkinter.TclError`` — not caught by any of
this app's ``except (ConfigValidationError, OSError, ValueError)``
clauses — the moment the field is empty or holds non-numeric text) so an
invalid value surfaces as the same kind of friendly ``messagebox.showerror``
every other configuration mistake does, not an unhandled Tcl error dialog.
"""

from __future__ import annotations


def parse_int_field(value: str, field_label: str, *, minimum: int | None = None) -> int:
    stripped = value.strip()
    try:
        parsed = int(stripped)
    except ValueError:
        raise ValueError(
            f"« {field_label} » doit être un nombre entier (valeur actuelle : « {value} »)."
        ) from None
    if minimum is not None and parsed < minimum:
        raise ValueError(
            f"« {field_label} » doit être un nombre entier supérieur ou égal à {minimum} "
            f"(valeur actuelle : « {value} »)."
        )
    return parsed
