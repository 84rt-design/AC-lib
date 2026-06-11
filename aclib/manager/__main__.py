"""Point d'entrée Manager :  python -m aclib.manager"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from aclib.db import init_db
from aclib.ui import theme
from aclib.manager.main_window import ManagerWindow


def main() -> int:
    init_db()
    app = QApplication(sys.argv)
    app.setApplicationName("A.C.Lib Manager")
    theme.apply(app)
    win = ManagerWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
