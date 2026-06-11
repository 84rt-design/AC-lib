"""Indexeur : parcourt les dossiers projets, repère les fichiers 3D, crée /
met à jour les fiches et déclenche la génération des aperçus.

Regroupement : les fichiers de même nom dans un même dossier (flacon_250.c4d,
flacon_250.fbx, flacon_250.obj) = UN volume en plusieurs formats. La clé de
regroupement est (dossier, nom sans extension).

Les champs « auto » sont remplis ici (formats, dims via conversion, poids).
Les champs « saisi » (contenance, type, projet, tags…) restent vides et sont
complétés ensuite dans le Manager.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path

from aclib import config
from aclib.core import paths
from aclib.core.conversion import convert
from aclib.core.conversion.base import ConversionError
from aclib.db import get_session
from aclib.db.models import Asset, AssetFile

# Priorité du fichier « source » (= original, ce qu'on garde comme référence).
_SOURCE_PRIORITY = (".c4d", ".step", ".stp", ".fbx", ".obj")
# Priorité pour l'APERÇU :
#  - FBX d'abord : via FBX2glTF, PRÉSERVE les pièces séparées (multi-meshes)
#    -> outliner pièce par pièce. (trimesh fusionne l'OBJ en un seul mesh.)
#  - puis glTF/GLB déjà multi-meshes, puis OBJ/PLY/STL (fallback fusionné),
#    puis C4D/STEP.
_PREVIEW_PRIORITY = (".fbx", ".glb", ".gltf", ".obj", ".ply", ".stl", ".off", ".c4d", ".step", ".stp")

ProgressCb = Callable[[str, int, int], None]  # (message, courant, total)


def _scan(folder: Path) -> dict[tuple[str, str], list[Path]]:
    """Regroupe les fichiers 3D par (dossier, stem)."""
    groups: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for p in folder.rglob("*"):
        if p.is_file() and p.suffix.lower() in config.MODEL_EXTENSIONS:
            groups[(str(p.parent), p.stem)].append(p)
    return groups


def _pick(files: list[Path], priority: Iterable[str]) -> Path:
    by_ext = {f.suffix.lower(): f for f in files}
    for ext in priority:
        if ext in by_ext:
            return by_ext[ext]
    return files[0]


def _groups_from_files(files: Iterable[Path]) -> dict[tuple[str, str], list[Path]]:
    """Regroupe une liste de fichiers explicites par (dossier, stem)."""
    groups: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for p in files:
        if p.is_file() and p.suffix.lower() in config.MODEL_EXTENSIONS:
            groups[(str(p.parent), p.stem)].append(p)
    return groups


def index_folder(
    folder: str | Path,
    *,
    make_previews: bool = True,
    progress: ProgressCb | None = None,
) -> dict[str, int]:
    """Indexe `folder` en récursif. Idempotent (mise à jour, pas de doublon)."""
    return _process_groups(_scan(Path(folder)), make_previews=make_previews, progress=progress)


def index_paths(
    targets: Iterable[str | Path],
    *,
    make_previews: bool = True,
    progress: ProgressCb | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Indexe une liste de chemins (fichiers ET/OU dossiers) — pour le
    glisser-déposer. Les dossiers sont parcourus en récursif ; les fichiers
    isolés sont regroupés tels quels par (dossier, nom).

    force=True : régénère les aperçus même s'ils existent déjà (re-conversion
    glb avec fix_normals + re-rendu miniature).
    """
    groups: dict[tuple[str, str], list[Path]] = defaultdict(list)
    loose: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            for k, v in _scan(p).items():
                groups[k].extend(v)
        elif p.is_file():
            loose.append(p)
    for k, v in _groups_from_files(loose).items():
        groups[k].extend(v)
    return _process_groups(groups, make_previews=make_previews, progress=progress, force=force)


def _process_groups(
    groups: dict[tuple[str, str], list[Path]],
    *,
    make_previews: bool,
    progress: ProgressCb | None,
    force: bool = False,
) -> dict[str, int]:
    total = len(groups)
    stats = {"new": 0, "updated": 0, "previews": 0, "errors": 0}

    with get_session() as session:
        for i, ((_dir, stem), files) in enumerate(sorted(groups.items()), start=1):
            source = _pick(files, _SOURCE_PRIORITY)
            src_rel = paths.to_relpath(source)

            if progress:
                progress(f"{stem}", i, total)

            asset = (
                session.query(Asset)
                .join(AssetFile)
                .filter(AssetFile.relpath == src_rel, AssetFile.is_source.is_(True))
                .first()
            )
            created = asset is None
            if created:
                asset = Asset(name=stem)
                session.add(asset)
                stats["new"] += 1
            else:
                stats["updated"] += 1

            old_size = asset.weight_bytes
            _sync_files(asset, files, source)
            _autofill_nomenclature(asset, stem)

            # aperçu : seulement si nouveau, source modifiée, ou aperçu absent
            # (sinon Refresh re-convertirait tout à chaque fois = lent).
            try:
                changed = source.stat().st_size != old_size
            except OSError:
                changed = True
            has_preview = bool(asset.gltf_relpath) and (config.PREVIEW_DIR / asset.gltf_relpath).exists()
            if make_previews and (force or created or changed or not has_preview):
                try:
                    _make_preview(asset, files)
                    asset.thumb_rendered = False  # force le re-rendu de la miniature
                    stats["previews"] += 1
                except Exception:  # noqa: BLE001
                    # Aperçu impossible (FBX/C4D/STEP sans convertisseur, fichier
                    # corrompu…) : NON bloquant. La fiche est créée quand même,
                    # à compléter à la main ; conversion relançable plus tard.
                    stats["errors"] += 1

            session.flush()

    return stats


def _sync_files(asset: Asset, files: list[Path], source: Path) -> None:
    """Aligne les AssetFile de l'asset sur les fichiers trouvés."""
    found = {}
    for f in files:
        fmt = f.suffix.lower().lstrip(".")
        found[fmt] = f

    existing = {af.fmt: af for af in asset.files}
    src_fmt = source.suffix.lower().lstrip(".")

    for fmt, f in found.items():
        rel = paths.to_relpath(f)
        size = f.stat().st_size
        af = existing.get(fmt)
        if af is None:
            af = AssetFile(fmt=fmt)
            asset.files.append(af)
        af.relpath = rel
        af.size_bytes = size
        af.is_source = fmt == src_fmt
        if af.is_source:
            asset.weight_bytes = size

    # purge des formats disparus
    for fmt, af in list(existing.items()):
        if fmt not in found:
            asset.files.remove(af)


def _autofill_nomenclature(asset: Asset, stem: str) -> None:
    """Pré-remplit type / contenance / client depuis le nom — UNIQUEMENT les
    champs encore vides (n'écrase jamais une saisie existante)."""
    from aclib.core import nomenclature

    parsed = nomenclature.parse(stem)
    if parsed.get("volume_type") and not asset.volume_type:
        asset.volume_type = parsed["volume_type"]
    if parsed.get("capacity_ml") and not asset.capacity_ml:
        asset.capacity_ml = parsed["capacity_ml"]
        asset.capacity_label = parsed.get("capacity_label")
    if parsed.get("client") and not asset.client:
        asset.client = parsed["client"]


def _make_preview(asset: Asset, files: list[Path]) -> None:
    """Génère glTF + vignette + dims. Essaie les sources par ordre de priorité
    avec FALLBACK : FBX d'abord (préserve les pièces via FBX2glTF), puis OBJ
    (trimesh fusionne les pièces mais marche sans convertisseur), etc.
    """
    # nom d'aperçu STABLE basé sur la source de référence (évite collisions +
    # garde le même nom à chaque régénération).
    src_file = asset.source_file()
    base_rel = src_file.relpath if src_file else paths.to_relpath(files[0])
    digest = hashlib.sha1(base_rel.encode("utf-8")).hexdigest()[:8]
    out_name = f"{Path(base_rel).stem}_{digest}"

    by_ext = {f.suffix.lower(): f for f in files}
    last_err: Exception | None = None
    for ext in _PREVIEW_PRIORITY:
        src = by_ext.get(ext)
        if src is None:
            continue
        try:
            result = convert(src, config.PREVIEW_DIR, thumb_size=config.THUMB_SIZE, out_name=out_name)
        except Exception as exc:  # noqa: BLE001 — essaie la source suivante
            last_err = exc
            continue
        if result.gltf_path:
            asset.gltf_relpath = result.gltf_path.relative_to(config.PREVIEW_DIR).as_posix()
        if result.thumbnail_path:
            asset.thumbnail_relpath = result.thumbnail_path.relative_to(config.PREVIEW_DIR).as_posix()
        info = result.info
        if info.bbox_mm:
            asset.bbox_x_mm, asset.bbox_y_mm, asset.bbox_z_mm = info.bbox_mm
            asset.height_mm = info.height_mm
            asset.diameter_mm = info.diameter_mm
        if info.poly_count is not None:
            asset.poly_count = info.poly_count
        return
    if last_err is not None:
        raise last_err
    raise ConversionError("aucun fichier convertible pour l'aperçu")
