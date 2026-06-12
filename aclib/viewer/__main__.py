"""Point d'entrée Viewer :  python -m aclib.viewer"""
from __future__ import annotations

import os
import sys

# IMPORTANT (macOS) : le renderer WebEngine du .app refuse par défaut de lire un
# .glb local (file://) -> "Erreur de chargement" dans l'aperçu 3D. Ces flags
# Chromium lèvent le sandbox + autorisent l'accès fichier local. Doit être posé
# AVANT l'initialisation de QtWebEngine. Sans effet sous Windows (déjà OK).
os.environ.setdefault(
    "QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --allow-file-access-from-files"
)
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

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
