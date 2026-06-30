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


def _log(msg: str) -> None:
    """Trace d'étape sur stderr (visible dans la console c4dpy ; n'interfère
    pas avec la ligne JSON finale lue sur stdout)."""
    sys.stderr.write(f"[c4d_worker] {msg}\n")
    sys.stderr.flush()


_log("démarrage worker ; import du module c4d (init Cinema 4D)…")
try:
    import c4d
    from c4d import documents
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "Ce script doit être lancé avec c4dpy (Cinema 4D), pas python standard.\n"
    )
    raise SystemExit(2)
_log("module c4d chargé.")


# Ids d'export. Stables, mais à confirmer selon la version (Plugins > Save As).
FORMAT_FBX_EXPORT = getattr(c4d, "FORMAT_FBX_EXPORT", 1026370)
# Deux exportateurs OBJ existent selon la version ; on tente le récent puis l'ancien.
FORMAT_OBJ2_EXPORT = getattr(c4d, "FORMAT_OBJ2EXPORT", 1030178)
FORMAT_OBJ_EXPORT = getattr(c4d, "FORMAT_OBJEXPORT", 1019572)


def _load(source: Path):
    _log(f"chargement du document : {source}")
    doc = documents.LoadDocument(
        str(source),
        c4d.SCENEFILTER_OBJECTS | c4d.SCENEFILTER_MATERIALS,
    )
    if doc is None:
        raise RuntimeError(f"LoadDocument a échoué : {source}")
    _log("document chargé.")
    return doc


def _save_as(doc, dst: Path, fmt: int) -> bool:
    return bool(documents.SaveDocument(
        doc, str(dst), c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST, fmt,
    ))


def export_fbx(source: Path, out_dir: Path) -> Path:
    doc = _load(source)
    out_dir.mkdir(parents=True, exist_ok=True)
    fbx = out_dir / f"{source.stem}.fbx"
    if not _save_as(doc, fbx, FORMAT_FBX_EXPORT) or not fbx.exists():
        raise RuntimeError(f"Export FBX échoué : {fbx}")
    return fbx


def export_obj(source: Path, out_dir: Path) -> Path:
    doc = _load(source)
    out_dir.mkdir(parents=True, exist_ok=True)
    obj = out_dir / f"{source.stem}.obj"
    # tente l'exportateur OBJ récent puis l'ancien
    if not (_save_as(doc, obj, FORMAT_OBJ2_EXPORT) and obj.exists()):
        if not (_save_as(doc, obj, FORMAT_OBJ_EXPORT) and obj.exists()):
            raise RuntimeError(f"Export OBJ échoué : {obj}")
    return obj


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--thumb-size", type=int, default=512)  # réservé (rendu natif futur)
    # --exchange : exporte FBX + OBJ (gardés dans --out) pour archivage dans la
    # bibliothèque. Sans le flag : FBX seul (pipeline d'aperçu).
    ap.add_argument("--exchange", action="store_true")
    args = ap.parse_args()

    src, out = Path(args.source), Path(args.out)
    try:
        _log("export FBX…")
        fbx = export_fbx(src, out)  # FBX = indispensable (aperçu + échange)
        _log(f"FBX écrit : {fbx}")
    except Exception as exc:  # noqa: BLE001
        _log(f"ERREUR export FBX : {exc}")
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1

    result = {"ok": True, "fbx": str(fbx)}
    if args.exchange:
        # OBJ best-effort : l'id d'export varie selon la version C4D. En cas
        # d'échec on n'interrompt PAS l'import (c4d + fbx suffisent).
        try:
            _log("export OBJ…")
            result["obj"] = str(export_obj(src, out))
            _log(f"OBJ écrit : {result['obj']}")
        except Exception as exc:  # noqa: BLE001
            _log(f"OBJ ignoré (échec) : {exc}")
            result["obj_error"] = str(exc)

    _log("terminé, émission du JSON.")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
