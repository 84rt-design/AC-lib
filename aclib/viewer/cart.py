"""Panier : sélection de volumes persistée entre sessions.

Stocke des IDs d'assets dans un JSON local (poste utilisateur, pas le NAS).
Base des futures « collections » (§3 souhaitables). Plusieurs paniers nommés
possibles ; le panier courant est « default ».
"""
from __future__ import annotations

import json
from pathlib import Path

# Local au poste (pas sur le NAS) — un panier par utilisateur.
_CART_DIR = Path.home() / ".aclib"
_CART_FILE = _CART_DIR / "carts.json"


class Cart:
    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._ids: list[int] = []
        self._load()

    # --- API ---
    @property
    def ids(self) -> list[int]:
        return list(self._ids)

    def __len__(self) -> int:
        return len(self._ids)

    def __contains__(self, asset_id: int) -> bool:
        return asset_id in self._ids

    def add(self, asset_id: int) -> None:
        if asset_id not in self._ids:
            self._ids.append(asset_id)
            self._save()

    def remove(self, asset_id: int) -> None:
        if asset_id in self._ids:
            self._ids.remove(asset_id)
            self._save()

    def toggle(self, asset_id: int) -> bool:
        """Ajoute/retire ; renvoie True si présent après l'opération."""
        if asset_id in self._ids:
            self.remove(asset_id)
            return False
        self.add(asset_id)
        return True

    def clear(self) -> None:
        self._ids.clear()
        self._save()

    # --- persistance ---
    def _all(self) -> dict[str, list[int]]:
        if _CART_FILE.exists():
            try:
                return json.loads(_CART_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _load(self) -> None:
        self._ids = self._all().get(self.name, [])

    def _save(self) -> None:
        _CART_DIR.mkdir(parents=True, exist_ok=True)
        data = self._all()
        data[self.name] = self._ids
        _CART_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
