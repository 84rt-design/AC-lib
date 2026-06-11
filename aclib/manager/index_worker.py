"""Thread d'indexation — garde l'UI Manager réactive pendant le scan/convert.

Accepte un dossier unique OU une liste de chemins (fichiers/dossiers) pour le
glisser-déposer.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from aclib.core import indexer


class IndexWorker(QThread):
    progress = Signal(str, int, int)   # message, courant, total
    done = Signal(dict)                # stats
    failed = Signal(str)               # message d'erreur

    def __init__(self, targets, make_previews: bool = True, force: bool = False) -> None:
        super().__init__()
        # un seul dossier (str/Path) ou une liste de chemins
        if isinstance(targets, (str, Path)):
            self._targets = [Path(targets)]
        else:
            self._targets = [Path(t) for t in targets]
        self._make_previews = make_previews
        self._force = force

    def run(self) -> None:  # exécuté dans le thread
        try:
            stats = indexer.index_paths(
                self._targets,
                make_previews=self._make_previews,
                progress=lambda m, c, t: self.progress.emit(m, c, t),
                force=self._force,
            )
            self.done.emit(stats)
        except Exception as exc:  # noqa: BLE001 — remonté à l'UI
            self.failed.emit(str(exc))
