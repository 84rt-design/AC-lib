"""Export du panier vers un dossier choisi.

Choix par export : l'utilisateur coche les formats voulus (seuls ceux qui
existent pour chaque volume sont copiés). Structure : un sous-dossier par
volume. Copie réelle des fichiers (l'artiste les déplace dans son projet),
exécutée dans un thread avec progression pour ne pas figer l'UI.

Lit depuis le NAS (chemin résolu selon l'OS) -> écrit vers le dossier local.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from aclib.core import paths
from aclib.db import get_session
from aclib.db.models import Asset

_SAFE = re.compile(r"[^\w\-. ]+", re.UNICODE)


def _safe_name(name: str) -> str:
    cleaned = _SAFE.sub("_", name).strip(" .")
    return cleaned or "volume"


class ExportWorker(QThread):
    """Copie les fichiers des volumes du panier, formats filtrés."""

    progress = Signal(str, int, int)          # message, courant, total
    done = Signal(int, int)                   # fichiers copiés, volumes ignorés
    failed = Signal(str)

    def __init__(self, asset_ids: list[int], formats: set[str], dest: str | Path) -> None:
        super().__init__()
        self._ids = asset_ids
        self._formats = {f.lower() for f in formats}
        self._dest = Path(dest)

    def run(self) -> None:
        try:
            self._dest.mkdir(parents=True, exist_ok=True)
            jobs = self._collect()  # [(asset_name, src_abs, fmt)]
            total = len(jobs)
            copied = 0
            for i, (vol, src, _fmt) in enumerate(jobs, start=1):
                self.progress.emit(f"{vol} / {src.name}", i, total)
                sub = self._dest / _safe_name(vol)
                sub.mkdir(parents=True, exist_ok=True)
                if src.exists():
                    shutil.copy2(src, sub / src.name)
                    copied += 1
                # source absente (NAS non monté ?) -> ignorée, non bloquant
            skipped = total - copied
            self.done.emit(copied, skipped)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))

    def _collect(self) -> list[tuple[str, Path, str]]:
        jobs: list[tuple[str, Path, str]] = []
        with get_session() as s:
            for aid in self._ids:
                a = s.get(Asset, aid)
                if a is None:
                    continue
                for f in a.files:
                    if f.fmt.lower() in self._formats:
                        jobs.append((a.name, paths.to_abs(f.relpath), f.fmt))
        return jobs


def available_formats(asset_ids: list[int]) -> set[str]:
    """Formats présents dans le panier (pour cocher uniquement l'utile)."""
    fmts: set[str] = set()
    with get_session() as s:
        for aid in asset_ids:
            a = s.get(Asset, aid)
            if a:
                fmts.update(a.formats())
    return fmts
