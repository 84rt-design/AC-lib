"""Interface commune + dispatch des convertisseurs."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Mesh3DInfo:
    """Métadonnées géométriques extraites du modèle (auto)."""

    bbox_mm: tuple[float, float, float] | None = None  # (x, y, z)
    poly_count: int | None = None                       # triangles

    @property
    def height_mm(self) -> float | None:
        # Orientation indépendante : la hauteur d'un packaging (flacon, tube…)
        # est sa plus grande dimension (peu importe l'axe up du fichier).
        return max(self.bbox_mm) if self.bbox_mm else None

    @property
    def diameter_mm(self) -> float | None:
        # Ø ≈ 2e plus grande dimension (la section du volume).
        if not self.bbox_mm:
            return None
        return sorted(self.bbox_mm)[-2]


@dataclass
class ConversionResult:
    """Sortie d'une conversion : aperçus + métadonnées."""

    gltf_path: Path | None = None        # glTF allégé pour le viewer
    thumbnail_path: Path | None = None   # vignette PNG
    info: Mesh3DInfo = field(default_factory=Mesh3DInfo)
    ok: bool = False
    message: str = ""


class ConversionError(RuntimeError):
    """Conversion impossible (format non géré, SDK absent, fichier corrompu)."""


def convert(source: Path, out_dir: Path, thumb_size: int = 512, out_name: str | None = None) -> ConversionResult:
    """Convertit `source` -> glTF + vignette dans `out_dir`, par extension.

    `out_name` : nom de base des fichiers générés (défaut = nom du source).
    Permet des noms uniques pour éviter les collisions entre volumes homonymes.

    Importe le backend paresseusement : le Viewer n'embarque jamais les
    dépendances lourdes (c4dpy, pythonocc) puisqu'il n'appelle pas convert().
    """
    ext = source.suffix.lower()

    # formats lus nativement par trimesh (aperçu direct)
    if ext in (".obj", ".glb", ".gltf", ".ply", ".stl", ".off"):
        from aclib.core.conversion import mesh

        return mesh.convert(source, out_dir, thumb_size, out_name)

    # FBX : propriétaire, trimesh ne le lit pas -> convertisseur externe
    if ext == ".fbx":
        from aclib.core.conversion import fbx

        return fbx.convert(source, out_dir, thumb_size, out_name)

    if ext == ".c4d":
        from aclib.core.conversion import c4d

        return c4d.convert(source, out_dir, thumb_size, out_name)

    if ext in (".step", ".stp"):
        from aclib.core.conversion import step

        return step.convert(source, out_dir, thumb_size, out_name)

    raise ConversionError(f"Format non géré : {ext}")
