"""Headless command-line interface for MEROPE.

Allows generating a site without launching the Tkinter UI, for
scripting, CI, or scheduled builds.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bloggen.build.reports import format_build_report
from bloggen.build.site_builder import build_site
from bloggen.config.io import ConfigValidationError, load_config


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "build":
        return _run_build(args.config)

    if args.command == "gui":
        from bloggen.ui.main_window import MainWindow

        MainWindow().mainloop()
        return 0

    parser.error("Commande inconnue.")
    return 2  # pragma: no cover - argparse.error exits before this point


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bloggen", description="Générateur de site statique MEROPE.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="Génère le site à partir d'une configuration JSON.")
    build_parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Chemin du fichier de configuration JSON du projet.",
    )

    subparsers.add_parser("gui", help="Lance l'interface graphique Tkinter.")
    return parser


def _run_build(config_path: Path) -> int:
    try:
        config = load_config(config_path)
    except ConfigValidationError as exc:
        print("Configuration invalide:", file=sys.stderr)
        for error in exc.errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"Impossible de charger la configuration: {exc}", file=sys.stderr)
        return 1

    report = build_site(config, config_path=config_path.resolve())
    print(format_build_report(report))
    return 0 if report.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
