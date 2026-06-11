"""Boîte de dialogue du panier : contenu courant + retrait + envoi.

Affiche les volumes du panier (un par ligne, avec bouton retirer), un champ
« adresse de destination » (dossier local ou chemin réseau \\\\serveur\\…) et
les formats à copier. « Envoyer » lance l'export vers cette adresse.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from aclib import config
from aclib.db import get_session
from aclib.db.models import Asset
from aclib.ui import icons, theme
from aclib.viewer import export as export_mod
from aclib.viewer.cart import Cart


class CartDialog(QDialog):
    """Panier : liste éditable + adresse + formats. `exec()` → Accepted si envoi."""

    def __init__(self, cart: Cart, parent=None) -> None:
        super().__init__(parent)
        self.cart = cart
        self.setWindowTitle("Panier")
        self.setMinimumWidth(460)
        self._dest = ""
        self._checks: dict[str, QCheckBox] = {}

        root = QVBoxLayout(self)
        root.setSpacing(12)

        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet(f"color: {theme.TEXT}; font-size: 15px; font-weight: 700;")
        root.addWidget(self._count_lbl)

        # liste scrollable des volumes
        self._scroll = QScrollArea(); self._scroll.setWidgetResizable(True)
        self._scroll.setFixedHeight(220)
        self._scroll.setStyleSheet("border: none;")
        self._list_host = QWidget()
        self._list_lay = QVBoxLayout(self._list_host)
        self._list_lay.setContentsMargins(0, 0, 0, 0); self._list_lay.setSpacing(6)
        self._scroll.setWidget(self._list_host)
        root.addWidget(self._scroll)

        # formats à copier
        self._fmt_label = QLabel("Formats à copier :")
        self._fmt_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        root.addWidget(self._fmt_label)
        self._fmt_row = QHBoxLayout(); self._fmt_row.setSpacing(10)
        root.addLayout(self._fmt_row)

        # adresse de destination
        addr_lbl = QLabel("Adresse de destination :")
        addr_lbl.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        root.addWidget(addr_lbl)
        addr = QHBoxLayout()
        self._dest_edit = QLineEdit()
        self._dest_edit.setPlaceholderText(r"Dossier local ou réseau (ex. \\serveur\projets\...)")
        browse = QPushButton("Parcourir…")
        browse.setCursor(Qt.PointingHandCursor)
        browse.clicked.connect(self._pick_dest)
        addr.addWidget(self._dest_edit, 1); addr.addWidget(browse)
        root.addLayout(addr)

        # actions
        actions = QHBoxLayout()
        self._btn_clear = QPushButton("Vider le panier")
        self._btn_clear.setObjectName("Ghost")
        self._btn_clear.setCursor(Qt.PointingHandCursor)
        self._btn_clear.clicked.connect(self._clear_cart)
        cancel = QPushButton("Fermer")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        self._btn_send = QPushButton("  Envoyer")
        self._btn_send.setObjectName("Primary")
        self._btn_send.setIcon(icons.icon("import", theme.NOIR_CARBONE, 16))
        self._btn_send.setCursor(Qt.PointingHandCursor)
        self._btn_send.clicked.connect(self._send)
        actions.addWidget(self._btn_clear)
        actions.addStretch(1)
        actions.addWidget(cancel)
        actions.addWidget(self._btn_send)
        root.addLayout(actions)

        self._rebuild()

    # ------------------------------------------------------------------
    def _rebuild(self) -> None:
        """Reconstruit la liste des volumes + les cases de formats."""
        # vide la liste
        while self._list_lay.count():
            it = self._list_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        ids = self.cart.ids
        self._count_lbl.setText(f"{len(ids)} volume(s) dans le panier")
        with get_session() as s:
            rows = [(a.id, a.name, a.formats()) for a in (s.get(Asset, i) for i in ids) if a]
        for aid, name, fmts in rows:
            self._list_lay.addWidget(self._make_row(aid, name, fmts))
        self._list_lay.addStretch(1)

        # cases de formats (recalcule selon le contenu courant)
        while self._fmt_row.count():
            it = self._fmt_row.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        self._checks = {}
        for fmt in sorted(export_mod.available_formats(ids)):
            cb = QCheckBox(fmt.upper()); cb.setChecked(True)
            self._checks[fmt] = cb
            self._fmt_row.addWidget(cb)
        self._fmt_row.addStretch(1)

        empty = len(ids) == 0
        self._btn_send.setEnabled(not empty)
        self._btn_clear.setEnabled(not empty)
        self._fmt_label.setVisible(not empty)

    def _make_row(self, aid: int, name: str, fmts: list[str]) -> QWidget:
        row = QFrame()
        row.setStyleSheet(
            f"background: {theme.BG_CARD}; border: 1px solid {theme.BORDER_SOFT}; "
            f"border-radius: 8px;"
        )
        lay = QHBoxLayout(row); lay.setContentsMargins(12, 8, 8, 8); lay.setSpacing(8)
        lbl = QLabel(name or f"Volume {aid}")
        lbl.setStyleSheet(f"color: {theme.TEXT}; background: transparent; border: none;")
        sub = QLabel(", ".join(f.upper() for f in fmts) or "—")
        sub.setStyleSheet(f"color: {theme.TEXT_DIM}; background: transparent; border: none; font-size: 11px;")
        col = QVBoxLayout(); col.setSpacing(1); col.addWidget(lbl); col.addWidget(sub)
        lay.addLayout(col, 1)
        rm = QPushButton(); rm.setFixedSize(28, 28)
        rm.setObjectName("Ghost"); rm.setCursor(Qt.PointingHandCursor)
        rm.setIcon(icons.icon("trash", theme.TEXT_MUTED, 15))
        rm.setToolTip("Retirer du panier")
        rm.clicked.connect(lambda _=False, i=aid: self._remove(i))
        lay.addWidget(rm)
        return row

    # ------------------------------------------------------------------
    def _remove(self, asset_id: int) -> None:
        self.cart.remove(asset_id)
        self._rebuild()

    def _clear_cart(self) -> None:
        self.cart.clear()
        self._rebuild()

    def _pick_dest(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Adresse de destination")
        if d:
            self._dest_edit.setText(d)

    def _send(self) -> None:
        self._dest = self._dest_edit.text().strip()
        if self._dest and self.selected_formats():
            self.accept()

    # --- résultats ---
    def selected_formats(self) -> set[str]:
        return {fmt for fmt, cb in self._checks.items() if cb.isChecked()}

    def dest(self) -> str:
        return self._dest
