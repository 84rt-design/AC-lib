"""Capture le Manager (réutilise le seed démo). Plateforme native, hors écran."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aclib import config  # noqa: E402
from scripts.screenshot_test import seed  # noqa: E402


def main() -> int:
    seed()
    from PySide6.QtWidgets import QApplication
    from aclib.ui import theme
    from aclib.manager.main_window import ManagerWindow

    app = QApplication.instance() or QApplication(sys.argv)
    theme.apply(app)
    win = ManagerWindow()
    win.resize(1180, 760)
    win.setAttribute(Qt.WA_DontShowOnScreen, True)
    win.show()
    for _ in range(8):
        app.processEvents()

    out = Path(config.nas_root() if _has_nas() else Path.home()) / "shots"
    out.mkdir(parents=True, exist_ok=True)
    win.grab().save(str(out / "10_manager_empty.png"))

    first = None
    with __import__("aclib.db", fromlist=["get_session"]).get_session() as s:
        from aclib.db.models import Asset
        a = s.query(Asset).order_by(Asset.name).first()
        first = a.id if a else None
    if first:
        win._select(first)
        for _ in range(6):
            app.processEvents()
        win.grab().save(str(out / "11_manager_edit.png"))
    print("shots ->", out)
    app.quit()
    return 0


def _has_nas() -> bool:
    try:
        return config.nas_root().exists()
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
