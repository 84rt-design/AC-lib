"""Boîte de dialogue d'export : cases à cocher par format + dossier cible.

Seuls les formats réellement présents dans le panier sont proposés
(« choix par export »).
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class ExportDialog(QDialog):
    def __init__(self, available_formats: set[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exporter le panier")
        self.setMinimumWidth(420)
        self._checks: dict[str, QCheckBox] = {}
        self._dest = ""

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Formats à copier :"))
        for fmt in sorted(available_formats):
            cb = QCheckBox(fmt.upper())
            cb.setChecked(True)
            self._checks[fmt] = cb
            root.addWidget(cb)
        if not available_formats:
            root.addWidget(QLabel("Panier vide ou sans fichier."))

        # dossier cible
        row = QHBoxLayout()
        self._dest_edit = QLineEdit()
        self._dest_edit.setPlaceholderText("Dossier de destination…")
        browse = QPushButton("Parcourir…")
        browse.clicked.connect(self._pick_dest)
        row.addWidget(self._dest_edit, 1)
        row.addWidget(browse)
        root.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _pick_dest(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Dossier de destination")
        if d:
            self._dest_edit.setText(d)

    def _accept(self) -> None:
        self._dest = self._dest_edit.text().strip()
        if self._dest and self.selected_formats():
            self.accept()

    # --- résultats ---
    def selected_formats(self) -> set[str]:
        return {fmt for fmt, cb in self._checks.items() if cb.isChecked()}

    def dest(self) -> str:
        return self._dest
