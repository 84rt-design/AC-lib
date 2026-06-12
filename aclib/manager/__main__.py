"""Point d'entrée Manager :  python -m aclib.manager"""
from __future__ import annotations

import os
import sys

# macOS : autorise le renderer WebEngine à lire les .glb locaux (aperçu 3D).
# Doit précéder l'init QtWebEngine. Sans effet sous Windows. Voir viewer/__main__.
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --allow-file-access-from-files"
)
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

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
