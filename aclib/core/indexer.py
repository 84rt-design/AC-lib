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
import shutil
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


def _is_valid_obj(p: Path) -> bool:
    """Distingue un OBJ Wavefront (maillage 3D, texte ASCII) d'un .obj
    compilateur (objet COFF binaire C/C++, ex. build Qt). Évite d'indexer des
    artefacts de compilation qui partagent l'extension .obj.

    Lecture MINIMALE (512 o) : sur partage réseau chaque ouverture coûte cher.
    Le test octet-nul suffit — un COFF binaire en contient dès l'en-tête, un
    OBJ Wavefront (texte) jamais.
    """
    try:
        with p.open("rb") as f:
            head = f.read(512)
    except OSError:
        return False
    return b"\x00" not in head


def _accept(p: Path) -> bool:
    """Filtre RAPIDE du scan : extension seule, AUCUNE lecture (perf réseau).
    La validation du contenu .obj est faite plus tard, uniquement sur le
    fichier choisi comme SOURCE (cf. _source_ok), pas sur tout l'arbre.
    """
    return p.suffix.lower() in config.MODEL_EXTENSIONS


def _source_ok(source: Path) -> bool:
    """Le fichier SOURCE d'un volume est-il valide ? (lit seulement si .obj)
    Un .obj compilateur (COFF binaire) est rejeté ; tout le reste passe."""
    if source.suffix.lower() != ".obj":
        return True
    return _is_valid_obj(source)


def _relativize_paths(session) -> int:
    """Convertit les chemins stockés en ABSOLU (anciennes fiches indexées avant
    que la racine NAS soit connue) en RELATIF, dès qu'ils tombent sous la racine
    NAS courante. Rend portable une base Windows lisible/exploitable sur Mac.
    Coût nul réseau (manipulation de chaînes uniquement)."""
    from aclib.db.models import AssetFile

    try:
        root = str(config.nas_root()).replace("\\", "/").rstrip("/")
    except RuntimeError:
        return 0
    if not root:
        return 0
    root_lc = root.lower() + "/"
    n = 0
    for af in session.query(AssetFile).all():
        rp = af.relpath
        if not paths._is_absolute_stored(rp):
            continue
        norm = rp.replace("\\", "/")
        if norm.lower().startswith(root_lc):
            af.relpath = norm[len(root_lc):]  # garde la casse d'origine pour le reste
            n += 1
    return n


def _purge_invalid(session) -> int:
    """Supprime les fiches dont le fichier source .obj est JOIGNABLE mais
    invalide (objet compilateur indexé par erreur). Ne lit que les .obj et ne
    touche jamais une fiche hors-ligne (NAS non monté) -> zéro suppression
    accidentelle, coût réseau minimal.
    """
    removed = 0
    for a in session.query(Asset).all():
        src = a.source_file()
        if src is None or not src.relpath.lower().endswith(".obj"):
            continue  # seuls les .obj peuvent être des objets compilateur
        p = paths.to_abs(src.relpath)
        try:
            reachable = p.exists()
        except OSError:
            reachable = False
        if reachable and not _is_valid_obj(p):
            session.delete(a)
            removed += 1
    return removed


def _scan(folder: Path) -> dict[tuple[str, str], list[Path]]:
    """Regroupe les fichiers 3D par (dossier, stem)."""
    groups: dict[tuple[str, str], list[Path]] = defaultdict(list)
    for p in folder.rglob("*"):
        if p.is_file() and _accept(p):
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
        if p.is_file() and _accept(p):
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


def import_c4d_files(c4d_paths: list[Path], *, progress: ProgressCb | None = None) -> list[Path]:
    """Importe des .c4d DANS la bibliothèque : copie le .c4d natif sous
    <DATA_DIR>/sources/<stem>/ et exporte FBX + OBJ à côté (via c4dpy). Le trio
    (c4d + fbx + obj) forme un volume multi-formats. Renvoie les dossiers créés.

    Nécessite Cinema 4D (c4dpy). Une erreur sur un fichier n'interrompt pas les
    autres (l'erreur est propagée si AUCUN n'a abouti)."""
    from aclib.core.conversion import c4d as c4dconv

    base = config.DATA_DIR / "sources"
    dests: list[Path] = []
    last_err: Exception | None = None
    total = len(c4d_paths)
    for i, src in enumerate(c4d_paths, start=1):
        if progress:
            progress(f"Cinema 4D : export {src.stem} (peut prendre 1-2 min)…", i, total)
        try:
            dest = base / src.stem
            dest.mkdir(parents=True, exist_ok=True)
            native = dest / src.name
            if Path(src).resolve() != native.resolve():
                shutil.copy2(src, native)              # garde le .c4d natif
            c4dconv.export_exchange(native, dest)      # écrit fbx + obj à côté
            dests.append(dest)
        except Exception as exc:  # noqa: BLE001 — on continue les autres .c4d
            last_err = exc
    if not dests and last_err is not None:
        raise last_err
    return dests


def index_paths(
    targets: Iterable[str | Path],
    *,
    make_previews: bool = True,
    progress: ProgressCb | None = None,
    force: bool = False,
    materialize_c4d: bool = False,
) -> dict[str, int]:
    """Indexe une liste de chemins (fichiers ET/OU dossiers) — pour le
    glisser-déposer. Les dossiers sont parcourus en récursif ; les fichiers
    isolés sont regroupés tels quels par (dossier, nom).

    force=True : régénère les aperçus même s'ils existent déjà (re-conversion
    glb avec fix_normals + re-rendu miniature).

    materialize_c4d=True : un .c4d isolé déposé est IMPORTÉ dans la bibliothèque
    (copie native + export FBX/OBJ) avant indexation (cf. import_c4d_files).
    """
    groups: dict[tuple[str, str], list[Path]] = defaultdict(list)
    loose: list[Path] = []
    c4d_loose: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            for k, v in _scan(p).items():
                groups[k].extend(v)
        elif p.is_file():
            if materialize_c4d and p.suffix.lower() == ".c4d":
                c4d_loose.append(p)
            else:
                loose.append(p)
    # import des .c4d déposés -> dossiers sources/<stem> (c4d + fbx + obj)
    for dest in import_c4d_files(c4d_loose, progress=progress):
        for k, v in _scan(dest).items():
            groups[k].extend(v)
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
    stats = {"new": 0, "updated": 0, "previews": 0, "errors": 0, "removed": 0, "relativized": 0}

    with get_session() as session:
        stats["relativized"] = _relativize_paths(session)
        stats["removed"] = _purge_invalid(session)
        for i, ((_dir, stem), files) in enumerate(sorted(groups.items()), start=1):
            source = _pick(files, _SOURCE_PRIORITY)
            if not _source_ok(source):
                continue  # .obj compilateur (COFF) -> pas un volume, on ignore
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
