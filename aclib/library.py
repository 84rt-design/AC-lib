"""Bascule de la bibliothèque active (dossier base + aperçus), partagée par
le Manager et le Viewer. Met à jour les chemins, rebranche la base, persiste.
"""
from __future__ import annotations

from pathlib import Path

from aclib import config, settings
from aclib.db import session


def current() -> Path:
    return config.DATA_DIR


def switch(path: str | Path, *, persist: bool = True) -> Path:
    """Pointe la bibliothèque sur `path` (crée la base si absente) et
    l'enregistre pour que les deux apps la retrouvent au prochain lancement.
    """
    p = Path(path)
    config.set_data_dir(p)
    config.ensure_dirs()
    session.reset()
    session.init_db()
    if persist:
        settings.set("data_dir", str(p))
    return p
