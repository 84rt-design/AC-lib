"""Conversion STEP/STP (CAO) -> glTF + vignette.

STUB. Le STEP est un format CAO B-Rep (surfaces, pas de mailles). Il faut :
  1. lire le B-Rep      -> pythonocc-core (bindings OpenCASCADE)
  2. mailler (tessélation) -> maillage triangulaire
  3. exporter glTF + bbox + polycount

pythonocc-core s'installe via conda (pas pip) :
    conda install -c conda-forge pythonocc-core

Alternative : FreeCAD en headless (FreeCADCmd) avec son module Mesh/Import.

Comme c4d, c'est une dépendance lourde réservée au Manager ; le Viewer ne
charge jamais ce module.
"""
from __future__ import annotations

from pathlib import Path

from aclib.core.conversion.base import ConversionError, ConversionResult, Mesh3DInfo


# Déflexion de tessélation : plus petit = plus de triangles, surface plus fine.
LINEAR_DEFLECTION = 0.1


def convert(source: Path, out_dir: Path, thumb_size: int = 512, out_name: str | None = None) -> ConversionResult:
    try:
        from OCC.Core.STEPControl import STEPControl_Reader  # type: ignore
        from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh  # type: ignore
        from OCC.Core.Bnd import Bnd_Box  # type: ignore
        from OCC.Core.BRepBndLib import brepbndlib  # type: ignore
    except ImportError as exc:
        raise ConversionError(
            "pythonocc-core absent. Installer via conda :\n"
            "  conda install -c conda-forge pythonocc-core\n"
            "(réservé au Manager — le Viewer n'en a pas besoin)."
        ) from exc

    out_dir.mkdir(parents=True, exist_ok=True)

    reader = STEPControl_Reader()
    status = reader.ReadFile(str(source))
    if status != 1:  # IFSelect_RetDone
        raise ConversionError(f"Lecture STEP échouée (status {status}) : {source}")
    reader.TransferRoots()
    shape = reader.OneShape()

    # Tessélation -> maillage.
    BRepMesh_IncrementalMesh(shape, LINEAR_DEFLECTION)

    # Bounding box.
    box = Bnd_Box()
    brepbndlib.Add(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    bbox = (float(xmax - xmin), float(ymax - ymin), float(zmax - zmin))

    # TODO: extraire les triangles -> trimesh -> export .glb + polycount + vignette.
    #       (tessélation OCC -> tableaux de sommets/faces -> trimesh.Trimesh)
    raise ConversionError(
        "STEP : tessélation OK (bbox=%s) — export glTF à finir. "
        "Brancher OCC->trimesh dans step.py." % (bbox,)
    )
