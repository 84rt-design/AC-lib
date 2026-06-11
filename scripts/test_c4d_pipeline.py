"""Validation CRITIQUE du pipeline C4D -> glTF (point d'attention §5 du cadrage).

À lancer AVANT d'investir plus dans l'app. Vérifie bout en bout :
  .c4d  --(c4dpy worker)-->  .fbx  --(trimesh)-->  .glb + vignette + bbox + tris

Lancement (Python standard — il appelle c4dpy en sous-processus tout seul) :

    python scripts/test_c4d_pipeline.py "C:/chemin/vers/flacon_250.c4d"

Si ça sort un .glb non vide + une bbox plausible, le reste du projet déroule.
Si ça échoue : c'est ICI qu'il faut régler le problème (version C4D, id export
FBX, unités), pas dans l'app.
"""
from __future__ import annotations

import sys
from pathlib import Path

# rendre le package aclib importable quand lancé depuis n'importe où
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aclib.core.conversion import c4d  # noqa: E402
from aclib.core.conversion.base import ConversionError  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage : python scripts/test_c4d_pipeline.py <fichier.c4d> [dossier_sortie]")
        return 2

    source = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.cwd() / "c4d_test_out"

    if not source.exists():
        print(f"Fichier introuvable : {source}")
        return 2
    if c4d.C4DPY is None:
        print("c4dpy introuvable dans le PATH. Voir aclib/core/conversion/c4d.py (C4DPY).")
        return 2

    print(f"Source  : {source}")
    print(f"c4dpy   : {c4d.C4DPY}")
    print(f"Sortie  : {out}")
    print("Conversion en cours…")

    try:
        result = c4d.convert(source, out)
    except ConversionError as exc:
        print(f"\nÉCHEC : {exc}")
        return 1

    print("\n--- RÉSULTAT ---")
    print(f"glTF       : {result.gltf_path}")
    print(f"vignette   : {result.thumbnail_path}")
    print(f"bbox (mm)  : {result.info.bbox_mm}")
    print(f"H × Ø (mm) : {result.info.height_mm} × {result.info.diameter_mm}")
    print(f"triangles  : {result.info.poly_count}")
    print(f"message    : {result.message}")

    ok = bool(result.gltf_path and result.gltf_path.exists() and result.gltf_path.stat().st_size > 0)
    print(f"\n{'OK — pipeline validé.' if ok else 'glTF manquant ou vide — à investiguer.'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
