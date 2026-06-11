"""Point d'entrée Viewer :  python -m aclib.viewer"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from aclib.db import init_db
from aclib.ui import theme
from aclib.viewer.main_window import ViewerWindow


def main() -> int:
    init_db()
    app = QApplication(sys.argv)
    app.setApplicationName("A.C.Lib Viewer")
    theme.apply(app)
    win = ViewerWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
