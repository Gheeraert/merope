"""Point d'entree de ``python -m bloggen.ui.qt_editor``."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Prototype autonome de l'editeur Qt de Merope")
    parser.add_argument("markdown", nargs="?", type=Path, help="fichier Markdown a visualiser")
    args = parser.parse_args()
    try:
        from bloggen.ui.qt_editor.window import run
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            parser.error("PySide6 absent ; installez l'extra .[qt_editor]")
        raise
    return run(args.markdown)


if __name__ == "__main__":
    raise SystemExit(main())

