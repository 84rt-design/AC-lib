"""Point d'entrée Manager :  python -m aclib.manager"""
from __future__ import annotations

import os
import sys

# macOS : autorise une page file:// à charger les .glb locaux (aperçu 3D) sans
# désactiver le sandbox (qui faisait crasher le .app). Voir viewer/__main__.
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--allow-file-access-from-files")

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
