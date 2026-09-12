"""Point d'entree de ``python -m bloggen.ui.qt_editor``."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

from bloggen.ui.qt_editor_protocol import configure_utf8_stdio, emit_event


def main() -> int:
    parser = argparse.ArgumentParser(description="Prototype autonome de l'editeur Qt de Merope")
    parser.add_argument("markdown", nargs="?", type=Path, help="fichier Markdown a visualiser")
    parser.add_argument("--ipc", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--pages-dir", type=Path)
    parser.add_argument("--posts-dir", type=Path)
    parser.add_argument("--images-dir", type=Path)
    parser.add_argument("--slugify-mode", default="ascii")
    args = parser.parse_args()
    if args.ipc:
        configure_utf8_stdio()
    try:
        from bloggen.ui.qt_editor.window import run
    except ModuleNotFoundError as exc:
        if exc.name == "PySide6":
            message = "PySide6 absent ; installez l'extra .[qt_editor]"
            if args.ipc:
                emit_event("error", message=message)
                print(message, file=sys.stderr)
                return 2
            parser.error(message)
        if args.ipc:
            emit_event("error", message=str(exc))
            traceback.print_exc(file=sys.stderr)
            return 1
        raise
    except Exception as exc:
        if args.ipc:
            emit_event("error", message=str(exc))
            traceback.print_exc(file=sys.stderr)
            return 1
        raise
    try:
        return run(
            args.markdown,
            project_root=args.project_root,
            initial_directory=args.pages_dir,
            pages_dir=args.pages_dir,
            posts_dir=args.posts_dir,
            images_dir=args.images_dir,
            slugify_mode=args.slugify_mode,
            ipc=args.ipc,
        )
    except Exception as exc:
        if args.ipc:
            emit_event("error", message=str(exc))
        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
