"""RangeSlider — slider à deux poignées (filtre contenance / hauteur).

Reprend le visuel des filtres de la maquette : piste fine, deux poignées
rondes, valeurs min/max affichées. Émet `rangeChanged(lo, hi)`.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPaintEvent
from PySide6.QtWidgets import QWidget

from aclib.ui import theme


class RangeSlider(QWidget):
    rangeChanged = Signal(int, int)

    def __init__(self, minimum: int, maximum: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min = minimum
        self._max = maximum
        self._lo = minimum
        self._hi = maximum
        self._drag: str | None = None  # "lo" | "hi"
        self.setMinimumHeight(34)
        self.setMouseTracking(True)

    # --- valeurs ---
    def values(self) -> tuple[int, int]:
        return self._lo, self._hi

    def set_values(self, lo: int, hi: int) -> None:
        self._lo = max(self._min, min(lo, self._max))
        self._hi = max(self._min, min(hi, self._max))
        if self._lo > self._hi:
            self._lo, self._hi = self._hi, self._lo
        self.update()
        self.rangeChanged.emit(self._lo, self._hi)

    # --- géométrie ---
    def _track_rect(self) -> QRectF:
        pad = 9
        return QRectF(pad, self.height() / 2 - 2, self.width() - 2 * pad, 4)

    def _pos(self, value: int) -> float:
        tr = self._track_rect()
        span = max(1, self._max - self._min)
        return tr.left() + (value - self._min) / span * tr.width()

    def _value_at(self, x: float) -> int:
        tr = self._track_rect()
        span = self._max - self._min
        ratio = (x - tr.left()) / max(1.0, tr.width())
        return round(self._min + ratio * span)

    # --- peinture ---
    def paintEvent(self, _e: QPaintEvent) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        tr = self._track_rect()

        # piste
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.BORDER))
        p.drawRoundedRect(tr, 2, 2)

        # segment actif
        x_lo, x_hi = self._pos(self._lo), self._pos(self._hi)
        active = QRectF(x_lo, tr.top(), x_hi - x_lo, tr.height())
        p.setBrush(QColor(theme.GRIS_MINERAL))
        p.drawRoundedRect(active, 2, 2)

        # poignées
        p.setBrush(QColor(theme.BLANC_OPTIQUE))
        for x in (x_lo, x_hi):
            p.drawEllipse(QRectF(x - 7, self.height() / 2 - 7, 14, 14))

    # --- souris ---
    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        x = e.position().x()
        self._drag = "lo" if abs(x - self._pos(self._lo)) <= abs(x - self._pos(self._hi)) else "hi"
        self._move_to(x)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._drag:
            self._move_to(e.position().x())

    def mouseReleaseEvent(self, _e: QMouseEvent) -> None:  # noqa: N802
        self._drag = None

    def _move_to(self, x: float) -> None:
        v = self._value_at(x)
        if self._drag == "lo":
            self.set_values(min(v, self._hi), self._hi)
        elif self._drag == "hi":
            self.set_values(self._lo, max(v, self._lo))
