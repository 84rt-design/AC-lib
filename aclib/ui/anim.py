"""Boîte à outils d'animations UI — micro-interactions « classes ».

Qt/QSS ne fait pas de transitions : tout passe par QPropertyAnimation et les
QGraphics*Effect. Helpers réutilisables, durées et courbes cohérentes.

⚠️ Ne jamais poser un QGraphicsOpacityEffect sur un widget contenant un
QWebEngineView (fenêtre native) — l'effet ne s'applique pas et clignote.
"""
from __future__ import annotations

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QGraphicsOpacityEffect, QWidget

# Réglages globaux (cohérence du « feel »).
DUR = 180          # durée standard (ms)
DUR_SLOW = 240
CURVE = QEasingCurve.OutCubic
SHADOW = QColor(0, 0, 0, 150)


def _keep(widget: QWidget, anim: QPropertyAnimation) -> None:
    """Garde une référence vivante (sinon l'anim est ramassée par le GC)."""
    store = getattr(widget, "_anims", None)
    if store is None:
        store = []
        widget._anims = store
    store[:] = [a for a in store if a.state() != QAbstractAnimation.State.Stopped]
    store.append(anim)


def fade_in(widget: QWidget, duration: int = DUR_SLOW, start: float = 0.0, on_finish=None) -> None:
    """Fondu d'apparition. Retire l'effet à la fin (réutilisable)."""
    eff = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(eff)
    eff.setOpacity(start)
    a = QPropertyAnimation(eff, b"opacity", widget)
    a.setDuration(duration)
    a.setStartValue(start)
    a.setEndValue(1.0)
    a.setEasingCurve(CURVE)

    def _done():
        widget.setGraphicsEffect(None)
        if on_finish:
            on_finish()

    a.finished.connect(_done)
    _keep(widget, a)
    a.start()


def slide_in(widget: QWidget, dy: int = 16, duration: int = DUR_SLOW) -> None:
    """Glissement vers sa place (position SEULE, sans opacité).

    Sûr : le contenu reste toujours visible (pas d'effet qui pourrait le
    masquer s'il est interrompu). Idéal pour un panneau de contenu.
    """
    base = widget.pos()
    a = QPropertyAnimation(widget, b"pos", widget)
    a.setDuration(duration)
    a.setStartValue(QPoint(base.x(), base.y() + dy))
    a.setEndValue(base)
    a.setEasingCurve(CURVE)
    _keep(widget, a)
    a.start()


class _Hover(QObject):
    """Ombre portée (+ lift optionnel) animée au survol."""

    def __init__(self, w: QWidget, lift: int, blur: int, offset_y: int) -> None:
        super().__init__(w)
        self.w = w
        self.lift = lift
        self.blur = blur
        self.offset_y = offset_y
        self._base: QPoint | None = None
        self.sh = QGraphicsDropShadowEffect(w)
        self.sh.setBlurRadius(0)
        self.sh.setOffset(0, 0)
        self.sh.setColor(QColor(0, 0, 0, 0))
        w.setGraphicsEffect(self.sh)
        w.installEventFilter(self)

    def eventFilter(self, obj, ev):  # noqa: N802
        t = ev.type()
        if t == QEvent.Type.Enter:
            self._animate(True)
        elif t == QEvent.Type.Leave:
            self._animate(False)
        return False

    def _animate(self, on: bool) -> None:
        blur = QPropertyAnimation(self.sh, b"blurRadius", self.w)
        blur.setDuration(DUR); blur.setEndValue(float(self.blur if on else 0)); blur.setEasingCurve(CURVE)

        col = QPropertyAnimation(self.sh, b"color", self.w)
        col.setDuration(DUR); col.setEndValue(SHADOW if on else QColor(0, 0, 0, 0))

        off = QPropertyAnimation(self.sh, b"offset", self.w)
        off.setDuration(DUR); off.setEndValue(QPointF(0, self.offset_y if on else 0)); off.setEasingCurve(CURVE)

        anims = [blur, col, off]
        if self.lift:
            if self._base is None:
                self._base = self.w.pos()
            pos = QPropertyAnimation(self.w, b"pos", self.w)
            pos.setDuration(DUR); pos.setEasingCurve(CURVE)
            pos.setEndValue(QPoint(self._base.x(), self._base.y() - (self.lift if on else 0)))
            anims.append(pos)

        for a in anims:
            _keep(self.w, a)
            a.start()


def install_hover(widget: QWidget, lift: int = 0, blur: int = 24, offset_y: int = 6) -> _Hover:
    """Ajoute une ombre portée animée au survol (lift>0 = soulève le widget)."""
    return _Hover(widget, lift, blur, offset_y)
