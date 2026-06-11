"""Favoris : ensemble d'IDs de volumes marqués d'une étoile.

Perso au poste (pas sur le NAS), comme le panier — stocké dans un JSON local
(~/.aclib/favorites.json). Permet le filtre « Favoris » et l'étoile des cartes.
"""
from __future__ import annotations

import json
from pathlib import Path

_FAV_DIR = Path.home() / ".aclib"
_FAV_FILE = _FAV_DIR / "favorites.json"


class Favorites:
    def __init__(self) -> None:
        self._ids: set[int] = set()
        self._load()

    @property
    def ids(self) -> list[int]:
        return list(self._ids)

    def __contains__(self, asset_id: int) -> bool:
        return asset_id in self._ids

    def __len__(self) -> int:
        return len(self._ids)

    def toggle(self, asset_id: int) -> bool:
        """Ajoute/retire ; renvoie True si favori après l'opération."""
        if asset_id in self._ids:
            self._ids.discard(asset_id)
            self._save()
            return False
        self._ids.add(asset_id)
        self._save()
        return True

    # --- persistance ---
    def _load(self) -> None:
        if _FAV_FILE.exists():
            try:
                self._ids = set(json.loads(_FAV_FILE.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError, TypeError):
                self._ids = set()

    def _save(self) -> None:
        _FAV_DIR.mkdir(parents=True, exist_ok=True)
        _FAV_FILE.write_text(json.dumps(sorted(self._ids)), encoding="utf-8")
