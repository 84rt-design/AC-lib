"""Widgets réutilisables conformes à la charte : chips, items sidebar, cartes
produit, tuiles de métadonnées. Tout le style vient du QSS global (theme.py),
ici on assemble la structure.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from aclib.ui import anim, icons, theme
from aclib.ui.flowlayout import FlowLayout


# ---------------------------------------------------------------- petits blocs
def section_label(text: str) -> QLabel:
    lbl = QLabel(text.upper())
    lbl.setObjectName("SectionLabel")
    return lbl


def h1(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("H1")
    return lbl


def muted(text: str, dim: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Dim" if dim else "Muted")
    return lbl


class Chip(QPushButton):
    """Pill outline ; cochable pour les filtres, statique pour les tags."""

    def __init__(self, text: str, checkable: bool = True, parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Chip")
        self.setCheckable(checkable)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


class _RemovableChip(QPushButton):
    """Chip avec « × » ; clic = se retire."""

    removed = Signal(str)

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(f"{text}   ✕", parent)
        self._value = text
        self.setObjectName("Chip")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.clicked.connect(lambda: self.removed.emit(self._value))


class TagEditor(QWidget):
    """Éditeur de tags : chips supprimables + champ de saisie (Entrée pour ajouter)."""

    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tags: list[str] = []
        self._flow = FlowLayout(self, spacing=6)
        self._input = QLineEdit()
        self._input.setPlaceholderText("ajouter un tag + Entrée")
        self._input.setFixedWidth(170)
        self._input.returnPressed.connect(self._on_enter)
        self._rebuild()

    def set_tags(self, tags: list[str]) -> None:
        self._tags = list(dict.fromkeys(t.strip() for t in tags if t.strip()))
        self._rebuild()

    def tags(self) -> list[str]:
        return list(self._tags)

    def _on_enter(self) -> None:
        val = self._input.text().strip()
        if val and val not in self._tags:
            self._tags.append(val)
            self._input.clear()
            self._rebuild()
            self.changed.emit()
        else:
            self._input.clear()

    def _remove(self, value: str) -> None:
        if value in self._tags:
            self._tags.remove(value)
            self._rebuild()
            self.changed.emit()

    def _rebuild(self) -> None:
        while self._flow.count():
            item = self._flow.takeAt(0)
            w = item.widget()
            if w is not None and w is not self._input:
                w.deleteLater()
        for t in self._tags:
            chip = _RemovableChip(t)
            chip.removed.connect(self._remove)
            self._flow.addWidget(chip)
        self._flow.addWidget(self._input)


class NavItem(QPushButton):
    """Item de navigation sidebar : icône + libellé + compteur optionnel."""

    def __init__(self, icon_name: str, text: str, count: int | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("NavItem")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setIcon(icons.icon(icon_name, theme.TEXT_MUTED, 18))
        self.setIconSize(QSize(18, 18))

        lay = QHBoxLayout(self)
        lay.setContentsMargins(34, 0, 10, 0)  # place pour l'icône dessinée par Qt
        lbl = QLabel(text)
        lbl.setStyleSheet("background: transparent;")
        lay.addWidget(lbl)
        lay.addStretch(1)
        if count is not None:
            badge = QLabel(f"{count:,}".replace(",", " "))
            badge.setObjectName("Dim")
            badge.setStyleSheet(f"color: {theme.TEXT_DIM}; background: transparent;")
            lay.addWidget(badge)


class _Badge(QLabel):
    """Petit badge posé sur la vignette (contenance / format)."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setStyleSheet(
            f"background: rgba(11,12,14,0.72); color: {theme.TEXT}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 6px; "
            f"padding: 2px 7px; font-size: 11px; font-weight: 600;"
        )
        self.adjustSize()


_FAV_GOLD = "#E0B23B"


class _FavStar(QLabel):
    """Étoile favori posée sur la vignette ; clic = bascule (or si actif)."""

    toggled = Signal(bool)

    def __init__(self, on: bool, parent=None) -> None:
        super().__init__(parent)
        self._on = on
        self.setFixedSize(26, 26)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self._render()

    def _render(self) -> None:
        color = _FAV_GOLD if self._on else theme.TEXT_DIM
        self.setPixmap(icons.pixmap("star", color, 16))
        self.setStyleSheet("background: rgba(11,12,14,0.6); border-radius: 13px;")

    def mousePressEvent(self, e) -> None:  # noqa: N802 — consomme le clic (n'ouvre pas la fiche)
        self._on = not self._on
        self._render()
        self.toggled.emit(self._on)
        e.accept()


class MetaTile(QFrame):
    """Tuile de la fiche détail : libellé en capitales + valeur en gras."""

    def __init__(self, label: str, value: str, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"background: {theme.BG_FIELD}; border: 1px solid {theme.BORDER_SOFT}; "
            f"border-radius: {theme.RADIUS_SM}px;"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(3)
        lbl = QLabel(label.upper())
        lbl.setObjectName("SectionLabel")
        lbl.setStyleSheet(f"color: {theme.TEXT_DIM}; background: transparent;")
        val = QLabel(value)
        val.setStyleSheet(f"color: {theme.TEXT}; font-size: 17px; font-weight: 700; background: transparent;")
        lay.addWidget(lbl)
        lay.addWidget(val)


def info_row(label: str, value: str) -> QWidget:
    """Ligne d'information : libellé muted à gauche, valeur à droite."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 6, 0, 6)
    left = QLabel(label)
    left.setStyleSheet(f"color: {theme.TEXT_MUTED}; background: transparent;")
    right = QLabel(value or "—")
    right.setStyleSheet(f"color: {theme.TEXT}; background: transparent;")
    right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    right.setTextInteractionFlags(Qt.TextSelectableByMouse)
    lay.addWidget(left)
    lay.addStretch(1)
    lay.addWidget(right)
    return w


# ---------------------------------------------------------------- carte produit
def _fmt_specs(diameter, height, weight_bytes) -> str:
    parts = []
    if diameter:
        parts.append(f"Ø {round(diameter)} mm")
    if height:
        parts.append(f"H {round(height)} mm")
    line = "   ".join(parts)
    if weight_bytes:
        mo = weight_bytes / (1024 * 1024)
        line += f"  ·  {mo:.1f} Mo"
    return line or "—"


class AssetCard(QFrame):
    """Carte de la grille : vignette + badges (contenance/format) + titre + specs."""

    clicked = Signal(int)
    favoriteToggled = Signal(int, bool)  # (asset_id, est_favori)

    CARD_W = 244
    THUMB_H = 150

    def __init__(self, data: dict, parent=None) -> None:
        super().__init__(parent)
        self._id = int(data["id"])
        self.setObjectName("AssetCard")
        self.setFixedWidth(self.CARD_W)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style(hover=False)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_thumb(data))
        root.addWidget(self._build_body(data))

        # micro-interaction : soulèvement + ombre portée au survol
        anim.install_hover(self, lift=6, blur=32, offset_y=12)

    # style (géré ici car état hover dynamique)
    def _apply_style(self, hover: bool) -> None:
        bg = theme.BG_CARD_HOVER if hover else theme.BG_CARD
        border = theme.GRIS_ANTHRACITE if hover else theme.BORDER_SOFT
        self.setStyleSheet(
            f"#AssetCard {{ background: {bg}; border: 1px solid {border}; "
            f"border-radius: {theme.RADIUS_CARD}px; }}"
        )

    def _build_thumb(self, data: dict) -> QWidget:
        thumb = QWidget()
        thumb.setFixedHeight(self.THUMB_H)
        thumb.setStyleSheet(
            f"background: {theme.BG_THUMB}; "
            f"border-top-left-radius: {theme.RADIUS_CARD}px; "
            f"border-top-right-radius: {theme.RADIUS_CARD}px;"
        )
        # image centrée
        img = QLabel(thumb)
        img.setGeometry(0, 0, self.CARD_W, self.THUMB_H)
        img.setAlignment(Qt.AlignCenter)
        img.setStyleSheet("background: transparent;")
        path = data.get("thumb_path")
        if path and Path(path).exists():
            pm = QPixmap(str(path)).scaled(
                self.CARD_W - 24, self.THUMB_H - 16,
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            img.setPixmap(pm)
        else:
            img.setPixmap(icons.pixmap("bottle", theme.TEXT_DIM, 48))

        # badges
        cap = data.get("capacity_label")
        if cap:
            b = _Badge(cap, thumb)
            b.move(10, 10)
        fmt = data.get("primary_format")
        if fmt:
            b = _Badge(fmt.upper(), thumb)
            b.move(self.CARD_W - b.width() - 10, self.THUMB_H - b.height() - 10)  # bas-droite
        # étoile favori (haut-droite)
        star = _FavStar(bool(data.get("favorite")), thumb)
        star.move(self.CARD_W - star.width() - 8, 8)
        star.toggled.connect(lambda on: self.favoriteToggled.emit(self._id, on))
        return thumb

    def _build_body(self, data: dict) -> QWidget:
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(12, 11, 12, 13)
        lay.setSpacing(5)

        title = QLabel(data.get("name", ""))
        title.setStyleSheet(f"color: {theme.TEXT}; font-size: 13px; font-weight: 600; background: transparent;")
        title.setWordWrap(False)

        specs = QLabel(_fmt_specs(data.get("diameter_mm"), data.get("height_mm"), data.get("weight_bytes")))
        specs.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px; background: transparent;")

        lay.addWidget(title)
        lay.addWidget(specs)
        return body

    # interactions
    def enterEvent(self, _e) -> None:  # noqa: N802
        self._apply_style(hover=True)

    def leaveEvent(self, _e) -> None:  # noqa: N802
        self._apply_style(hover=False)

    def mouseReleaseEvent(self, _e) -> None:  # noqa: N802
        self.clicked.emit(self._id)
