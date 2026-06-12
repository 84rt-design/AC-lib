"""Point d'entrée Viewer :  python -m aclib.viewer"""
from __future__ import annotations

import os
import sys

# IMPORTANT (macOS) : le renderer WebEngine refuse par défaut qu'une page file://
# charge un .glb local (file://) -> "Erreur de chargement" dans l'aperçu 3D.
# --allow-file-access-from-files lève CETTE restriction. On NE désactive PAS le
# sandbox (--no-sandbox / DISABLE_SANDBOX faisaient crasher le .app au démarrage
# sur macOS). Doit être posé AVANT l'init QtWebEngine. Sans effet sous Windows.
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--allow-file-access-from-files")

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
