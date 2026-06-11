"""Smoke test sans NAS réel : crée un faux dossier projet avec un .obj, lance
l'indexeur, vérifie base + glTF + vignette, puis construit les deux fenêtres
en mode offscreen. À lancer avec les variables ACLIB_NAS_ROOT_* déjà pointées
sur un dossier temporaire.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aclib import config  # noqa: E402


def build_fixture() -> Path:
    """Crée <NAS>/Glicolyc/2023/flacon_box.obj (cube) et renvoie le dossier projet."""
    import trimesh

    root = config.nas_root()
    proj = root / "Glicolyc" / "2023"
    proj.mkdir(parents=True, exist_ok=True)
    # cube 42 x 42 x 148 mm (proche d'un flacon)
    box = trimesh.creation.box(extents=(42.0, 42.0, 148.0))
    box.export(proj / "flacon_box.obj")
    return root


def run_index(folder: Path) -> None:
    from aclib.core import indexer
    from aclib.db import get_session, init_db
    from aclib.db.models import Asset

    init_db()
    stats = indexer.index_folder(folder, make_previews=True)
    print("Index stats :", stats)

    with get_session() as s:
        assets = s.query(Asset).all()
        assert assets, "aucun asset indexé"
        a = assets[0]
        print(f"  Asset       : {a.name}")
        print(f"  Formats     : {a.formats()}")
        print(f"  bbox (mm)   : {a.bbox_x_mm} x {a.bbox_y_mm} x {a.bbox_z_mm}")
        print(f"  H x O (mm)  : {a.height_mm} x {a.diameter_mm}")
        print(f"  tris        : {a.poly_count}")
        print(f"  glTF        : {a.gltf_relpath}")
        print(f"  vignette    : {a.thumbnail_relpath}")
        assert a.gltf_relpath, "glTF non généré"
        assert (config.PREVIEW_DIR / a.gltf_relpath).stat().st_size > 0, "glTF vide"
        assert a.height_mm and abs(a.height_mm - 148.0) < 1.0, "hauteur incohérente"
    print("  -> indexeur OK")


def build_guis() -> None:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    from aclib.manager.main_window import ManagerWindow

    mw = ManagerWindow()
    print(f"  Manager     : {mw.windowTitle()}  (liste : {mw.vol_list.count()} items)")

    from aclib.viewer.main_window import ViewerWindow

    vw = ViewerWindow()
    print(f"  Viewer      : {vw.windowTitle()}  (grille : {vw.grid.count()} items)")
    print("  -> GUI construites OK")
    app.quit()


if __name__ == "__main__":
    print(f"NAS root : {config.nas_root()}")
    print(f"DB URL   : {config.DB_URL}")
    root = build_fixture()
    run_index(root)
    build_guis()
    print("\nSMOKE TEST OK")
