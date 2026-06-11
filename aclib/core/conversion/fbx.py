"""Conversion FBX -> glTF + vignette.

Le FBX est un format propriétaire Autodesk : trimesh ne le lit PAS. On passe
donc par un convertisseur externe pour produire un glTF (.glb), que le pipeline
standard (mesh.py / trimesh) transforme ensuite en aperçu + bbox + polycount.

Convertisseurs reconnus, par ordre de préférence :
  1. FBX2glTF  — binaire autonome MIT (Meta), aucune dépendance. Le plus simple :
     poser FBX2glTF.exe sur le PATH, à côté de l'exe, ou dans <projet>/tools/.
  2. assimp    — CLI Open Asset Import Library (`assimp export in.fbx out.glb`).

Si aucun n'est trouvé : ConversionError explicite (NON bloquant côté indexeur —
la fiche est créée sans aperçu, à compléter à la main, et convertie plus tard).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from aclib.core.conversion.base import ConversionError, ConversionResult


def _candidates(name: str) -> list[Path]:
    """Emplacements où chercher un binaire convertisseur."""
    out: list[Path] = []
    found = shutil.which(name)
    if found:
        out.append(Path(found))
    bases: list[Path] = []
    # bundle PyInstaller (onedir) : ressources dans _MEIPASS/tools
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bases += [Path(meipass) / "tools", Path(meipass)]
    # à côté de l'exe (build portable) et dans <projet>/tools/
    exe_dir = Path(sys.executable).resolve().parent
    proj_tools = Path(__file__).resolve().parents[3] / "tools"
    bases += [exe_dir / "tools", exe_dir, proj_tools]
    for base in bases:
        for ext in (".exe", ""):
            p = base / f"{name}{ext}"
            if p.exists():
                out.append(p)
    return out


def _find_converter() -> tuple[str, Path] | None:
    for p in _candidates("FBX2glTF"):
        return ("fbx2gltf", p)
    for p in _candidates("assimp"):
        return ("assimp", p)
    return None


def _to_glb(kind: str, exe: Path, source: Path, out_glb: Path) -> None:
    if kind == "fbx2gltf":
        # FBX2glTF -b (binaire .glb) -i input -o <stem sans extension>
        stem = out_glb.with_suffix("")
        cmd = [str(exe), "-b", "-i", str(source), "-o", str(stem)]
    else:  # assimp
        cmd = [str(exe), "export", str(source), str(out_glb)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not out_glb.exists():
        raise ConversionError(
            f"Conversion FBX échouée ({kind}) : {proc.stderr.strip() or proc.stdout.strip()}"
        )


def convert(source: Path, out_dir: Path, thumb_size: int = 512, out_name: str | None = None) -> ConversionResult:
    conv = _find_converter()
    if conv is None:
        raise ConversionError(
            "FBX non converti : aucun convertisseur trouvé. "
            "Pose FBX2glTF.exe (https://github.com/facebookincubator/FBX2glTF) "
            "sur le PATH, à côté de l'application, ou dans <projet>/tools/. "
            "La fiche est créée — relance la conversion une fois l'outil en place."
        )
    kind, exe = conv
    out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        glb = Path(tmp) / f"{source.stem}.glb"
        _to_glb(kind, exe, source, glb)
        from aclib.core.conversion import mesh

        result = mesh.convert(glb, out_dir, thumb_size, out_name or source.stem)

    result.message = f"FBX via {kind} -> {result.message}"
    return result
