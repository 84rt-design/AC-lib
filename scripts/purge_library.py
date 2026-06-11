"""Purge SÛRE d'une bibliothèque A.C.Lib : supprime UNIQUEMENT la base
(library.db) et les aperçus (previews/). Ne touche JAMAIS aux fichiers sources
3D (.c4d .fbx .obj .step .mtl …). Compte les sources avant/après pour preuve.

Usage : python scripts/purge_library.py "\\\\serveur\\...\\ACLIB"
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

SOURCE_EXT = {".c4d", ".fbx", ".obj", ".step", ".stp", ".mtl", ".ply", ".stl", ".off", ".gltf", ".glb"}


def count_sources(lib: Path) -> int:
    return sum(1 for p in lib.rglob("*") if p.is_file() and p.suffix.lower() in SOURCE_EXT
               and "previews" not in p.parts)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: purge_library.py <dossier_bibliotheque>")
        return 2
    lib = Path(sys.argv[1])
    if not lib.is_dir():
        print(f"Dossier introuvable : {lib}")
        return 2

    previews_only = "--previews-only" in sys.argv

    before = count_sources(lib)
    print(f"Sources (c4d/fbx/obj/mtl…) AVANT : {before}")

    db = lib / "library.db"
    if previews_only:
        print("[GARDE] library.db conservee (--previews-only)")
    elif db.exists():
        db.unlink()
        print("[OK] library.db supprimee")
    else:
        print("library.db absente (deja supprimee)")

    # purge previews/ (uniquement ce sous-dossier)
    prev = lib / "previews"
    if prev.is_dir():
        n = sum(1 for _ in prev.iterdir())
        shutil.rmtree(prev)
        prev.mkdir(parents=True, exist_ok=True)
        print(f"[OK] previews/ vide ({n} elements)")
    else:
        print("previews/ absent")

    # previews-only : remet les flags pour forcer la régénération
    if previews_only and db.exists():
        import sqlite3
        try:
            con = sqlite3.connect(db)
            con.execute("UPDATE assets SET thumb_rendered=0, gltf_relpath=NULL, thumbnail_relpath=NULL")
            con.commit(); con.close()
            print("[OK] flags aperçus réinitialisés (régénération au prochain Refresh)")
        except Exception as exc:  # noqa: BLE001
            print(f"(flags non réinitialisés : {exc})")

    after = count_sources(lib)
    print(f"Sources APRES : {after}")
    if before == after:
        print(f"OK - banque 3D INTACTE ({after} fichiers, aucun supprime).")
        return 0
    print("ALERTE : le nombre de sources a change !")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
