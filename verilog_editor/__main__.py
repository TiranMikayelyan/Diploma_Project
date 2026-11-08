"""Launch the existing editor inside the AI Verilog Studio host window.

Run from the project root::

    python main.py

This is a separate entry point on purpose: it does not replace any
``__main__.py`` inside ``verilog_editor/``.
"""

from __future__ import annotations

import sys

from PyQt6.QtWidgets import QApplication

from ui.studio_window import StudioWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = StudioWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
