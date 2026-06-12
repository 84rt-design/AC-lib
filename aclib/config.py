"""Configuration centrale A.C.Lib.

Règle dure : aucun chemin absolu n'est stocké dans la base. Les fiches portent
des chemins RELATIFS à la racine NAS. La racine absolue dépend de l'OS et est
résolue ici — un même fichier a un chemin Windows (UNC) et un chemin macOS.

Tout est surchargeable par variable d'environnement (préfixe ACLIB_).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _env(key: str, default: str) -> str:
    return os.environ.get(f"ACLIB_{key}", default)


# --- Racine NAS par OS -------------------------------------------------------
# Même partage, monté différemment selon la plateforme.
#   Windows : UNC          \\serveur\projets
#   macOS   : point montage /Volumes/projets
#   Linux   : montage       /mnt/projets
_NAS_ENV_KEY: dict[str, str] = {
    "win32": "NAS_ROOT_WIN", "darwin": "NAS_ROOT_MAC", "linux": "NAS_ROOT_LINUX",
}
_NAS_DEFAULT: dict[str, str] = {
    "win32": r"\\serveur\projets", "darwin": "/Volumes/projets", "linux": "/mnt/projets",
}


def _derive_nas_root() -> str | None:
    """Déduit la racine NAS du dossier Bibliothèque (DATA_DIR).

    Cas nominal : la base ET les sources vivent sur le MÊME partage réseau
    (ex. \\\\littleds\\LA2026_3D\\ACLIB pour la base -> racine \\\\littleds\\LA2026_3D).
    On prend la racine du partage (UNC) ou du volume monté (POSIX). Les deux
    postes pointant le même partage en déduisent la même racine logique ->
    chemins portables SANS configuration. Renvoie None si DATA_DIR est local
    (pas un partage) -> on retombe sur env/défaut.
    """
    d = str(DATA_DIR)
    if d.startswith("\\\\") or d.startswith("//"):           # UNC \\serveur\partage\...
        parts = d.replace("/", "\\").lstrip("\\").split("\\")
        if len(parts) >= 2:
            return "\\\\" + parts[0] + "\\" + parts[1]
    elif d.startswith("/"):                                  # POSIX /Volumes/NOM/... ou /mnt/NOM/...
        parts = [p for p in d.split("/") if p]
        if len(parts) >= 2:
            return "/" + parts[0] + "/" + parts[1]
    return None


def nas_root() -> Path:
    """Racine NAS absolue pour l'OS courant.

    Priorité : variable d'env (ACLIB_NAS_ROOT_*) > racine déduite du dossier
    Bibliothèque (partage commun) > défaut par OS.
    """
    key = _NAS_ENV_KEY.get(sys.platform)
    val = os.environ.get(f"ACLIB_{key}") if key else None
    if not val:
        val = _derive_nas_root()
    if not val:
        val = _NAS_DEFAULT.get(sys.platform)
    if val is None:
        raise RuntimeError(f"Aucune racine NAS pour la plateforme {sys.platform!r}")
    return Path(val)


# --- Dossier de données (base + aperçus) ------------------------------------
# Découplé du NAS : la base et les aperçus peuvent vivre en local (mode
# portable) tandis que le NAS ne sert qu'à résoudre les fichiers sources.
#   - ACLIB_DATA_DIR force l'emplacement.
#   - exe figé (PyInstaller) : <dossier de l'exe>/data  -> 100 % portable.
#   - sinon (dev) : <NAS>/.aclib si accessible, sinon ~/.aclib/data.
def data_dir() -> Path:
    # 1) variable d'environnement (prioritaire, pour CI / déploiement)
    env = os.environ.get("ACLIB_DATA_DIR")
    if env:
        return Path(env)
    # 2) réglage utilisateur PARTAGÉ (choisi via le bouton « Bibliothèque »)
    try:
        from aclib import settings

        saved = settings.data_dir()
        if saved:
            return Path(saved)
    except Exception:
        pass
    # 3) exe figé : dossier data à côté de l'exe (démo par défaut)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "data"
    # 4) dev : NAS si monté, sinon ~/.aclib/data
    try:
        root = nas_root()
        if root.exists():
            return root / ".aclib"
    except RuntimeError:
        pass
    return Path.home() / ".aclib" / "data"


DATA_DIR: Path = data_dir()

# --- Base de fiches ----------------------------------------------------------
# SQLite local d'abord ; bascule Postgres via ACLIB_DB_URL si multi-utilisateurs.
DB_PATH: Path = Path(_env("DB_PATH", str(DATA_DIR / "library.db")))

# URL SQLAlchemy. Surcharger ACLIB_DB_URL pour pointer un Postgres.
DB_URL: str = _env("DB_URL", f"sqlite:///{DB_PATH}")


# --- Aperçus (vignettes + glTF allégés) -------------------------------------
PREVIEW_DIR: Path = Path(_env("PREVIEW_DIR", str(DATA_DIR / "previews")))
THUMB_SIZE: int = int(_env("THUMB_SIZE", "512"))  # px côté max vignette


# --- Indexeur ----------------------------------------------------------------
# Extensions reconnues comme modèles 3D SOURCES indexables.
# NB : .glb/.gltf NE sont PAS indexés — ce sont les formats d'APERÇU générés
# par A.C.Lib. Les indexer créerait des doublons avec les fichiers source.
MODEL_EXTENSIONS: tuple[str, ...] = (
    ".c4d", ".fbx", ".obj", ".step", ".stp",   # formats cités au cadrage
    ".ply", ".stl", ".off",                     # autres maillages sources
)

# Formats dont l'aperçu est généré directement par trimesh (sans convertisseur).
NATIVE_PREVIEW_EXTENSIONS: tuple[str, ...] = (".obj", ".ply", ".stl", ".off")

# Formats nécessitant un convertisseur externe pour l'aperçu glTF :
#   .fbx -> FBX2glTF / assimp ; .c4d -> c4dpy ; .step/.stp -> pythonocc.
CONVERT_EXTENSIONS: tuple[str, ...] = (".fbx", ".c4d", ".step", ".stp")


def ensure_dirs() -> None:
    """Crée les dossiers base + aperçus si absents."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def set_data_dir(path: str | Path) -> None:
    """Bascule la bibliothèque active vers `path` (base + aperçus) à chaud.

    Met à jour les chemins globaux. À appeler avec db.session.reset() +
    init_db() pour rebrancher la base. Ne persiste PAS (voir settings.set).
    """
    global DATA_DIR, DB_PATH, DB_URL, PREVIEW_DIR
    DATA_DIR = Path(path)
    DB_PATH = DATA_DIR / "library.db"
    DB_URL = f"sqlite:///{DB_PATH}"
    PREVIEW_DIR = DATA_DIR / "previews"
