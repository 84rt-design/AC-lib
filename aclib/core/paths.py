r"""Résolution chemin relatif <-> absolu selon l'OS.

LE point cross-platform du projet. La base ne stocke que des chemins relatifs
à la racine NAS. Ici on convertit :

    relatif  "Glicolyc/2023/flacon_250.c4d"
       │  to_abs()  (préfixe racine OS + sépare bon séparateur)
       ▼
    Windows  \\serveur\projets\Glicolyc\2023\flacon_250.c4d
    macOS    /Volumes/projets/Glicolyc/2023/flacon_250.c4d

Une fiche créée sur Mac reste donc valide sur Windows et inversement.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath

from aclib import config


def _is_absolute_stored(stored: str) -> bool:
    """Un chemin stocké est-il absolu (= hors NAS) ?

    Absolu si : POSIX ('/...'), UNC ('//serveur/...') ou lecteur Windows ('C:/...').
    Sinon c'est un chemin relatif à la racine NAS (portable).
    """
    return (
        stored.startswith("/")
        or (len(stored) > 1 and stored[1] == ":")
    )


def to_relpath(absolute: Path | str) -> str:
    """Chemin absolu -> chemin stocké en base (POSIX, '/' neutre OS).

    Sous le NAS  -> chemin RELATIF (portable, résolu selon l'OS).
    Hors NAS     -> chemin ABSOLU conservé tel quel (fichiers ad-hoc / démo /
                    drag-drop hors NAS). Moins portable mais utilisable.
    """
    abs_path = Path(absolute).resolve()
    try:
        root = config.nas_root().resolve()
        rel = abs_path.relative_to(root)
        return PurePosixPath(*rel.parts).as_posix()
    except (ValueError, RuntimeError, OSError):
        return abs_path.as_posix()


def to_abs(relpath: str) -> Path:
    """Chemin stocké -> chemin absolu pour l'OS courant."""
    if _is_absolute_stored(relpath):
        return Path(relpath)
    parts = PurePosixPath(relpath).parts
    return config.nas_root().joinpath(*parts)


def exists(relpath: str) -> bool:
    """Le fichier pointé existe-t-il sur ce poste ? (NAS monté ?)"""
    try:
        return to_abs(relpath).exists()
    except (RuntimeError, OSError):
        return False
