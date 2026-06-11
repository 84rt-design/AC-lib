"""Conversion FBX/OBJ -> glTF + bbox + polycount via trimesh.

Formats d'échange ouverts : pas de SDK propriétaire. trimesh charge, calcule
la bounding box et le nombre de triangles, puis exporte un glTF allégé.

La vignette est déléguée à thumbnail.py (rendu offscreen optionnel).
"""
from __future__ import annotations

from pathlib import Path

from aclib.core.conversion.base import ConversionError, ConversionResult, Mesh3DInfo


def convert(source: Path, out_dir: Path, thumb_size: int = 512, out_name: str | None = None) -> ConversionResult:
    try:
        import trimesh
    except ImportError as exc:  # pragma: no cover
        raise ConversionError("trimesh non installé (pip install trimesh)") from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = out_name or source.stem

    try:
        scene = trimesh.load(source, force="scene")
    except Exception as exc:  # noqa: BLE001 — message clair plutôt que trace brute
        raise ConversionError(
            f"Lecture impossible ({source.suffix}) : {exc}. "
            f"Formats lus directement : OBJ, GLB/glTF, PLY, STL, OFF."
        ) from exc

    if scene is None or not getattr(scene, "geometry", None):
        raise ConversionError(f"Aucune géométrie trouvée dans {source.name}.")

    # --- répare les normales (orientation cohérente vers l'extérieur) ---
    # certains modèles ont des faces inversées -> rendu sombre/troué. fix_normals
    # corrige le winding + l'inversion. Non bloquant si ça échoue sur un mesh.
    for geom in scene.geometry.values():
        try:
            if hasattr(geom, "fix_normals"):
                geom.fix_normals()
        except Exception:  # noqa: BLE001
            pass

    # --- bbox (mm) : on suppose les unités du fichier en mm (cf. cadrage 3D). ---
    bounds = scene.bounds  # [[xmin,ymin,zmin],[xmax,ymax,zmax]]
    if bounds is not None:
        extents = (bounds[1] - bounds[0]).tolist()
        bbox = (float(extents[0]), float(extents[1]), float(extents[2]))
    else:
        bbox = None

    # --- polycount : somme des faces de toutes les géométries ---
    poly = 0
    for geom in scene.geometry.values():
        faces = getattr(geom, "faces", None)
        if faces is not None:
            poly += len(faces)
    info = Mesh3DInfo(bbox_mm=bbox, poly_count=poly or None)

    # --- export glTF (binaire .glb : un seul fichier, idéal pour le viewer) ---
    gltf_path = out_dir / f"{stem}.glb"
    scene.export(gltf_path)

    # --- vignette ---
    from aclib.core.conversion import thumbnail

    thumb_path = thumbnail.render(scene, out_dir / f"{stem}.png", size=thumb_size)

    return ConversionResult(
        gltf_path=gltf_path,
        thumbnail_path=thumb_path,
        info=info,
        ok=True,
        message=f"glTF + {poly} tris",
    )
