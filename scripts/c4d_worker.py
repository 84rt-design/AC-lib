"""Worker C4D — s'exécute SOUS c4dpy (interpréteur Maxon), pas sous le Python
standard. Le module `c4d` n'existe que là.

Rôle minimal et robuste : libérer la géométrie du .c4d propriétaire vers un
format d'échange (FBX), que le pipeline standard (trimesh, mesh.py) sait
ensuite transformer en glTF + vignette + bbox + polycount.

On ne tente PAS d'exporter directement le glTF ici : l'id du format glTF varie
selon la version de Cinema 4D, alors que l'export FBX est stable et universel.

Usage :
    c4dpy scripts/c4d_worker.py --source flacon.c4d --out ./previews
Sortie : <out>/<stem>.fbx  +  une ligne JSON sur stdout {"fbx": "...", "ok": true}

⚠️ À VALIDER sur une vraie install C4D : les constantes d'export et l'API de
chargement peuvent différer selon la version (voir test_c4d_pipeline.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import c4d
    from c4d import documents
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "Ce script doit être lancé avec c4dpy (Cinema 4D), pas python standard.\n"
    )
    raise SystemExit(2)


# Id d'export FBX. Stable, mais à confirmer selon la version (Plugins > Save As).
FORMAT_FBX_EXPORT = getattr(c4d, "FORMAT_FBX_EXPORT", 1026370)


def export_fbx(source: Path, out_dir: Path) -> Path:
    doc = documents.LoadDocument(
        str(source),
        c4d.SCENEFILTER_OBJECTS | c4d.SCENEFILTER_MATERIALS,
    )
    if doc is None:
        raise RuntimeError(f"LoadDocument a échoué : {source}")

    out_dir.mkdir(parents=True, exist_ok=True)
    fbx = out_dir / f"{source.stem}.fbx"

    ok = documents.SaveDocument(
        doc,
        str(fbx),
        c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST,
        FORMAT_FBX_EXPORT,
    )
    if not ok or not fbx.exists():
        raise RuntimeError(f"Export FBX échoué : {fbx}")
    return fbx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--thumb-size", type=int, default=512)  # réservé (rendu natif futur)
    args = ap.parse_args()

    try:
        fbx = export_fbx(Path(args.source), Path(args.out))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    print(json.dumps({"ok": True, "fbx": str(fbx)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
