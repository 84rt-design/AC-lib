"""Réglages utilisateur PARTAGÉS entre Manager et Viewer.

Stockés dans ~/.aclib/settings.json (même fichier pour les deux apps), donc le
chemin de la bibliothèque choisi dans l'un est vu par l'autre.

Clé principale : "data_dir" = dossier de la bibliothèque (base library.db +
aperçus previews/). C'est ce que le Manager remplit et que le Viewer lit.
"""
from __future__ import annotations

import json
from pathlib import Path

_FILE = Path.home() / ".aclib" / "settings.json"


def _read() -> dict:
    if _FILE.exists():
        try:
            return json.loads(_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def get(key: str, default=None):
    return _read().get(key, default)


def set(key: str, value) -> None:  # noqa: A003 — API volontairement simple
    data = _read()
    data[key] = value
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def data_dir() -> str | None:
    """Dossier de bibliothèque enregistré (None si jamais configuré)."""
    return get("data_dir")
