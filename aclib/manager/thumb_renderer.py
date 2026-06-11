"""Génère les VRAIES miniatures : rend chaque modèle glTF dans une vue web
cachée (même studio que le viewer) et capture le canvas en PNG.

Tourne sur le thread principal (QtWebEngine = GUI). Asynchrone, piloté par
QTimer, un modèle à la fois. Remplace le placeholder par le rendu du volume.
"""
from __future__ import annotations

import base64
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, Qt
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from aclib import config
from aclib.db import get_session
from aclib.db.models import Asset
from aclib.ui import model_cache

_VIEWER_HTML = Path(__file__).resolve().parents[1] / "viewer" / "web" / "viewer3d.html"
_SIZE = 512
_LOAD_MS = 1100   # délai chargement + rendu avant capture


class ThumbRenderer(QObject):
    progress = Signal(int, int)   # courant, total
    done = Signal(int)            # nombre rendu

    def __init__(self, jobs: list[tuple[int, str, str]], parent=None) -> None:
        """jobs = [(asset_id, glb_abspath, thumb_abspath)]"""
        super().__init__(parent)
        self._jobs = jobs
        self._i = 0
        self._rendered = 0
        self.view = QWebEngineView(parent)
        self.view.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.view.resize(_SIZE, _SIZE)
        self.view.settings().setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        self.view.loadFinished.connect(self._on_page)
        self.view.show()
        self.view.setUrl(QUrl.fromLocalFile(str(_VIEWER_HTML)))

    def _on_page(self, ok: bool) -> None:
        if not ok:
            self.done.emit(0)
            return
        QTimer.singleShot(200, self._next)

    def _next(self) -> None:
        if self._i >= len(self._jobs):
            self.view.deleteLater()
            self.done.emit(self._rendered)
            return
        self.progress.emit(self._i + 1, len(self._jobs))
        _aid, glb, _out = self._jobs[self._i]
        url = model_cache.local_url(glb) or ""
        self.view.page().runJavaScript(f'window.loadModel && window.loadModel("{url}");')
        QTimer.singleShot(_LOAD_MS, self._capture)

    def _capture(self) -> None:
        self.view.page().runJavaScript("window.snapshot ? window.snapshot() : ''", self._save)

    def _save(self, dataurl) -> None:
        aid, _glb, out = self._jobs[self._i]
        try:
            if dataurl and "," in dataurl:
                raw = base64.b64decode(dataurl.split(",", 1)[1])
                Path(out).parent.mkdir(parents=True, exist_ok=True)
                Path(out).write_bytes(raw)
                with get_session() as s:
                    a = s.get(Asset, aid)
                    if a:
                        a.thumb_rendered = True
                self._rendered += 1
        except Exception:  # noqa: BLE001 — une miniature ratée ne bloque pas le reste
            pass
        self._i += 1
        QTimer.singleShot(60, self._next)


def pending_jobs() -> list[tuple[int, str, str]]:
    """Volumes ayant un glTF mais pas encore de vraie miniature rendue."""
    from aclib.core import paths  # noqa: F401 (cohérence)

    jobs: list[tuple[int, str, str]] = []
    with get_session() as s:
        for a in s.query(Asset).filter(Asset.gltf_relpath.isnot(None)).all():
            if a.thumb_rendered:
                continue
            glb = config.PREVIEW_DIR / a.gltf_relpath
            if not glb.exists():
                continue
            thumb_rel = a.thumbnail_relpath or f"{a.id}_thumb.png"
            jobs.append((a.id, str(glb), str(config.PREVIEW_DIR / thumb_rel)))
            if not a.thumbnail_relpath:
                a.thumbnail_relpath = thumb_rel
    return jobs
