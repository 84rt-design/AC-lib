"""Conversion Cinema 4D (.c4d) -> glTF + vignette.

Le format C4D est propriétaire Maxon : aucune lib Python tierce ne le lit. On
passe donc par Cinema 4D lui-même, en headless, via c4dpy.

Pipeline en deux temps (découplé et robuste) :

  1. SOUS-PROCESSUS c4dpy  ->  scripts/c4d_worker.py libère la géométrie du .c4d
     vers un FBX (format d'échange stable).
  2. Pipeline standard      ->  mesh.convert() transforme ce FBX en glTF +
     vignette + bbox + polycount (trimesh).

Le module `c4d` n'existe que sous l'interpréteur Maxon : le Manager ne fait
JAMAIS `import c4d`, il appelle c4dpy en sous-processus. Le Viewer n'appelle
jamais ce module.

Tant que c4dpy n'est pas disponible, on lève une erreur explicite. À valider
via scripts/test_c4d_pipeline.py sur un fichier réel.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from aclib.core.conversion.base import ConversionError, ConversionResult

# Exécutable c4dpy. À configurer si absent du PATH :
#   Windows : "C:/Program Files/Maxon Cinema 4D 2024/c4dpy.exe"
#   macOS   : "/Applications/Maxon Cinema 4D 2024/c4dpy.app/Contents/MacOS/c4dpy"
C4DPY: str | None = shutil.which("c4dpy")

_WORKER = Path(__file__).resolve().parents[3] / "scripts" / "c4d_worker.py"


def convert(source: Path, out_dir: Path, thumb_size: int = 512, out_name: str | None = None) -> ConversionResult:
    if C4DPY is None:
        raise ConversionError(
            "c4dpy introuvable. Installer Cinema 4D et exposer c4dpy dans le PATH "
            "(ou éditer C4DPY dans aclib/core/conversion/c4d.py). "
            "Valider d'abord scripts/test_c4d_pipeline.py."
        )

    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) c4dpy : .c4d -> .fbx (dans un dossier temporaire).
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            C4DPY, str(_WORKER),
            "--source", str(source),
            "--out", tmp,
            "--thumb-size", str(thumb_size),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise ConversionError(
                f"c4dpy a échoué : {proc.stderr.strip() or proc.stdout.strip()}"
            )

        try:
            payload = json.loads(proc.stdout.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError) as exc:
            raise ConversionError(f"Sortie worker illisible : {proc.stdout!r}") from exc

        if not payload.get("ok"):
            raise ConversionError(f"Worker C4D : {payload.get('error', 'inconnu')}")

        fbx = Path(payload["fbx"])

        # 2) pipeline standard : FBX -> glTF + vignette + bbox + polycount.
        from aclib.core.conversion import mesh

        result = mesh.convert(fbx, out_dir, thumb_size, out_name or source.stem)

    result.message = f"C4D via c4dpy -> {result.message}"
    return result
