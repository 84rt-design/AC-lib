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

_WORKER = Path(__file__).resolve().parents[3] / "scripts" / "c4d_worker.py"

_C4DPY_HELP = (
    "c4dpy introuvable. Renseigner son chemin via le Manager (bouton Options), "
    "ou installer Cinema 4D et exposer c4dpy dans le PATH.\n"
    "  Windows : C:/Program Files/Maxon Cinema 4D 2024/c4dpy.exe\n"
    "  macOS   : /Applications/Maxon Cinema 4D 2024/c4dpy.app/Contents/MacOS/c4dpy"
)


# Délai max d'un appel c4dpy (s). Cinema 4D headless peut être lent au 1er
# lancement ; au-delà on considère un blocage (ex. dialogue licence) et on
# rend la main avec une erreur plutôt que de geler le Manager.
_C4DPY_TIMEOUT = 300


def _run_c4dpy(cmd: list[str]) -> dict:
    """Lance c4dpy avec timeout, renvoie le payload JSON du worker."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_C4DPY_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise ConversionError(
            f"c4dpy n'a pas répondu en {_C4DPY_TIMEOUT}s (Cinema 4D bloqué ? "
            "dialogue licence ? 1er lancement très lent ?). Import annulé."
        ) from exc
    if proc.returncode != 0:
        raise ConversionError(
            f"c4dpy a échoué : {proc.stderr.strip() or proc.stdout.strip()}"
        )
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        raise ConversionError(f"Sortie worker illisible : {proc.stdout!r}") from exc


def c4dpy_path() -> str | None:
    """Chemin de l'exécutable c4dpy : réglage utilisateur (Options) puis PATH."""
    try:
        from aclib import settings

        saved = settings.get("c4dpy_path")
        if saved and Path(saved).exists():
            return saved
    except Exception:  # noqa: BLE001
        pass
    return shutil.which("c4dpy")


def convert(source: Path, out_dir: Path, thumb_size: int = 512, out_name: str | None = None) -> ConversionResult:
    c4dpy = c4dpy_path()
    if c4dpy is None:
        raise ConversionError(_C4DPY_HELP)

    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) c4dpy : .c4d -> .fbx (dans un dossier temporaire).
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            c4dpy, str(_WORKER),
            "--source", str(source),
            "--out", tmp,
            "--thumb-size", str(thumb_size),
        ]
        payload = _run_c4dpy(cmd)
        if not payload.get("ok"):
            raise ConversionError(f"Worker C4D : {payload.get('error', 'inconnu')}")

        fbx = Path(payload["fbx"])

        # 2) pipeline standard : FBX -> glTF + vignette + bbox + polycount.
        from aclib.core.conversion import mesh

        result = mesh.convert(fbx, out_dir, thumb_size, out_name or source.stem)

    result.message = f"C4D via c4dpy -> {result.message}"
    return result


def export_exchange(source: Path, out_dir: Path) -> dict[str, Path]:
    """Exporte le .c4d en FBX + OBJ DANS out_dir (gardés, pour archivage dans la
    bibliothèque). Renvoie {'fbx': Path, 'obj': Path}. Nécessite c4dpy."""
    c4dpy = c4dpy_path()
    if c4dpy is None:
        raise ConversionError(_C4DPY_HELP)
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        c4dpy, str(_WORKER),
        "--source", str(source),
        "--out", str(out_dir),
        "--exchange",
    ]
    payload = _run_c4dpy(cmd)
    if not payload.get("ok"):
        raise ConversionError(f"Worker C4D : {payload.get('error', 'inconnu')}")
    out = {"fbx": Path(payload["fbx"])}
    if payload.get("obj"):
        out["obj"] = Path(payload["obj"])
    return out
