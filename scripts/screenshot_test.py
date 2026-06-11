"""Rend le Viewer hors écran avec un jeu de données proche de la maquette et
capture la page Bibliothèque + la page Détail en PNG, pour vérifier le rendu
graphique vs CHARTE ET DA. À lancer avec ACLIB_NAS_ROOT_WIN sur un dossier
temporaire (les fichiers réels ne sont pas nécessaires : données semées).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aclib import config  # noqa: E402

SEED = [
    ("Flacon Sérum « Aurélia »", "Flacon", 250, 148, 42, "c4d", ["cosmétique", "verre", "premium", "2023"],
     "Aurélia Skincare", "Maison Aurélia", 2023, "Studio 3D · L. Marchand", 48200, 2_516_582),
    ("Pot crème « Velours »", "Pot", 50, 52, 70, "fbx", ["cosmétique", "pot", "premium"],
     "Velours", "Groupe LM", 2022, "Studio 3D", 31200, 1_300_000),
    ("Tube soin « Botanic »", "Tube", 75, 130, 35, "c4d", ["soin", "tube", "naturel"],
     "Botanic", "BioCare", 2023, "PF1", 18900, 980_000),
    ("Bouteille « Hydra »", "Bouteille", 200, 190, 60, "obj", ["boisson", "plastique"],
     "Hydra", "AquaCo", 2021, "Studio 3D", 22400, 1_700_000),
    ("Flacon pompe « Pure »", "Flacon", 300, 165, 50, "step", ["cosmétique", "pompe"],
     "Pure", "Maison Aurélia", 2024, "L. Marchand", 54000, 3_100_000),
    ("Spray brume « Fresh »", "Spray", 150, 158, 45, "c4d", ["cosmétique", "spray", "été"],
     "Fresh", "BioCare", 2023, "PF1", 41000, 2_050_000),
    ("Tube gel « Aqua »", "Tube", 100, 140, 38, "fbx", ["soin", "tube"],
     "Aqua", "AquaCo", 2022, "Studio 3D", 16700, 870_000),
    ("Flacon huile « Soleil »", "Flacon", 100, 120, 40, "c4d", ["cosmétique", "huile", "premium"],
     "Soleil", "Maison Aurélia", 2024, "L. Marchand", 38800, 1_900_000),
]


def _demo_glb() -> str | None:
    """Génère un glTF de démo (silhouette flacon) pour le viewer 3D."""
    try:
        import trimesh
        import numpy as np
    except ImportError:
        return None
    config.PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    body = trimesh.creation.cylinder(radius=21, height=120, sections=48)
    body.apply_translation((0, 0, 60))
    neck = trimesh.creation.cylinder(radius=8, height=28, sections=32)
    neck.apply_translation((0, 0, 134))
    flacon = trimesh.util.concatenate([body, neck])
    out = config.PREVIEW_DIR / "demo.glb"
    flacon.export(out)
    return "demo.glb"


def seed() -> None:
    from aclib.core.conversion.thumbnail import _placeholder
    from aclib.db import get_session, init_db
    from aclib.db.models import Asset, AssetFile, Tag

    init_db()
    config.PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    glb = _demo_glb()
    with get_session() as s:
        if s.query(Asset).count() >= len(SEED):
            return
        tag_cache: dict[str, Tag] = {}
        for (name, vtype, cap, h, d, fmt, tags, proj, client, year, author, poly, weight) in SEED:
            thumb = f"{name[:10]}.png".replace(" ", "_").replace("«", "").replace("»", "")
            _placeholder(config.PREVIEW_DIR / thumb, 512, label=name)
            a = Asset(
                name=name, volume_type=vtype, capacity_ml=cap, capacity_label=f"{cap} ml",
                height_mm=h, diameter_mm=d, bbox_z_mm=h, bbox_x_mm=d, bbox_y_mm=d,
                project=proj, client=client, year=year, author=author,
                poly_count=poly, weight_bytes=weight, thumbnail_relpath=thumb,
                gltf_relpath=glb,
            )
            a.files.append(AssetFile(fmt=fmt, relpath=f"{proj}/{year}/{thumb[:-4]}.{fmt}", size_bytes=weight, is_source=True))
            for tn in tags:
                tag = tag_cache.get(tn) or s.query(Tag).filter(Tag.name == tn).first()
                if tag is None:
                    tag = Tag(name=tn); s.add(tag)
                tag_cache[tn] = tag
                a.tags.append(tag)
            s.add(a)


def shoot() -> None:
    from PySide6.QtWidgets import QApplication
    from aclib.ui import theme
    from aclib.viewer.main_window import ViewerWindow

    app = QApplication.instance() or QApplication(sys.argv)
    theme.apply(app)
    win = ViewerWindow()
    win.resize(1320, 820)
    if os.environ.get("ACLIB_NO_SHOW") != "1":
        win.show()
    else:
        win.setAttribute(Qt.WA_DontShowOnScreen, True)
        win.show()  # nécessaire pour le layout, mais hors écran
    for _ in range(8):
        app.processEvents()

    out = Path(config.nas_root()) / "shots"
    out.mkdir(exist_ok=True)
    win.grab().save(str(out / "01_library.png"))
    print("lib shot ->", out / "01_library.png")

    # ouvrir une fiche
    first_id = win._query_assets()[0]["id"]
    win._open_detail(first_id)
    for _ in range(10):
        app.processEvents()
    win.grab().save(str(out / "02_detail.png"))
    print("detail shot ->", out / "02_detail.png")
    app.quit()


if __name__ == "__main__":
    seed()
    if "--seed-only" in sys.argv:
        print("SEED OK ->", config.DATA_DIR)
    else:
        shoot()
        print("OK")
