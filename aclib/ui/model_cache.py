"""Cache local des modèles glTF pour le viewer 3D.

QtWebEngine ne charge pas de façon fiable un fichier glTF via file:// quand il
est sur un chemin UNC (NAS \\\\serveur\\...) ou contient espaces/accents : le
GLTFLoader renvoie « Erreur de chargement ».

Solution : copier le .glb dans un cache local temporaire avec un nom ASCII
neutre, puis charger CE fichier (chemin local sans espace = OK). La copie est
mémorisée et réutilisée tant que la source n'a pas changé.
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl

_CACHE = Path(tempfile.gettempdir()) / "aclib_modelcache"


def local_url(src: str | Path) -> str | None:
    """Renvoie une URL file:// LOCALE et sûre pour `src` (ou None si absent)."""
    src = Path(src)
    try:
        if not src.exists():
            return None
        _CACHE.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha1(str(src).encode("utf-8")).hexdigest()[:16]
        dst = _CACHE / f"{key}.glb"
        if (not dst.exists()) or dst.stat().st_mtime < src.stat().st_mtime:
            shutil.copy2(src, dst)
        return QUrl.fromLocalFile(str(dst)).toString()
    except OSError:
        return None
