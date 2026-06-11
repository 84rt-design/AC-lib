"""Génération de vignettes PNG.

Essaie un rendu offscreen via trimesh ; à défaut (pas de contexte GL en
headless), écrit une vignette de remplacement avec le nom du modèle. La vraie
vignette pourra venir du worker C4D (rendu natif Cinema 4D, plus joli).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def render(scene: Any, out_path: Path, size: int = 512) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) rendu offscreen trimesh (nécessite pyglet + contexte GL dispo).
    try:
        png = scene.save_image(resolution=(size, size), visible=False)
        if png:
            out_path.write_bytes(png)
            return out_path
    except Exception:
        pass  # pas de GL headless -> fallback

    # 2) fallback : placeholder Pillow.
    _placeholder(out_path, size, label=out_path.stem)
    return out_path


def _placeholder(out_path: Path, size: int, label: str) -> None:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (size, size), (38, 40, 46))
    draw = ImageDraw.Draw(img)
    draw.rectangle([8, 8, size - 8, size - 8], outline=(90, 95, 105), width=2)
    text = (label[:22] + "…") if len(label) > 23 else label
    draw.text((size // 2, size // 2), text, anchor="mm", fill=(170, 175, 185))
    img.save(out_path, "PNG")
