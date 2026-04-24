"""Application entrypoint for MEROPE."""

from __future__ import annotations

from bloggen.ui.main_window import MainWindow


def main() -> None:
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
