"""Thème A.C.Lib — palette de la charte + feuille de style Qt (QSS).

Couleurs reprises au pixel de CHARTE ET DA :
  charte « palette / code couleur » + tons UI échantillonnés sur les maquettes.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

# --- Palette officielle (charte) --------------------------------------------
BLANC_OPTIQUE = "#F5F5F2"
GRIS_BRUME = "#D9DCE0"
GRIS_MINERAL = "#A7ADB5"
GRIS_ANTHRACITE = "#2A2E33"
NOIR_CARBONE = "#0B0C0E"
NOIR_UI = "#14171A"

# --- Tons UI échantillonnés sur les maquettes -------------------------------
BG_APP = "#0B0C0E"        # fond appli + topbar
BG_PANEL = "#101113"      # panneaux (sidebar, header)
BG_GRID = "#131414"       # fond de la grille
BG_CARD = "#1C1D1F"       # carte produit
BG_CARD_HOVER = "#232427"
BG_THUMB = "#242525"      # zone vignette dans la carte
BG_VIEWER = "#181818"     # fond viewer 3D
BG_FIELD = "#16181B"      # champs / boutons sombres
BORDER = "#2A2E33"        # bordures, séparateurs, pills
BORDER_SOFT = "#1F2225"
TEXT = "#F5F5F2"          # texte principal
TEXT_MUTED = "#A7ADB5"    # labels, secondaire
TEXT_DIM = "#6B7178"      # tertiaire

ACCENT = "#F5F5F2"        # accent = blanc optique (UI monochrome)

# Inter installé système ; fallback propre Win/Mac.
FONT_STACK = '"Inter", "Segoe UI", -apple-system, "SF Pro Text", "Helvetica Neue", sans-serif'

RADIUS = 10
RADIUS_SM = 8
RADIUS_CARD = 12


def qcolor(hex_str: str) -> QColor:
    return QColor(hex_str)


def build_qss() -> str:
    return f"""
* {{
    font-family: {FONT_STACK};
    color: {TEXT};
    font-size: 13px;
}}
QMainWindow, QWidget {{
    background: {BG_APP};
}}

/* --- conteneurs nommés --- */
#TopBar {{
    background: {BG_APP};
    border-bottom: 1px solid {BORDER_SOFT};
}}
#Sidebar {{
    background: {BG_PANEL};
    border-right: 1px solid {BORDER_SOFT};
}}
#MainArea, #DetailArea {{
    background: {BG_GRID};
}}
#RightPanel {{
    background: {BG_PANEL};
    border-left: 1px solid {BORDER_SOFT};
}}

/* --- titres / labels --- */
#H1 {{ font-size: 22px; font-weight: 700; color: {TEXT}; }}
#H2 {{ font-size: 16px; font-weight: 600; color: {TEXT}; }}
#Muted {{ color: {TEXT_MUTED}; }}
#Dim {{ color: {TEXT_DIM}; font-size: 12px; }}
#SectionLabel {{
    color: {TEXT_DIM};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}}
#Brand {{ font-size: 15px; font-weight: 700; letter-spacing: .3px; }}

/* --- champ de recherche --- */
QLineEdit {{
    background: {BG_FIELD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
    padding: 8px 12px;
    selection-background-color: {GRIS_ANTHRACITE};
}}
QLineEdit:focus {{ border: 1px solid {GRIS_MINERAL}; }}
QLineEdit::placeholder {{ color: {TEXT_DIM}; }}

/* --- boutons --- */
QPushButton {{
    background: {BG_FIELD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    padding: 8px 14px;
    color: {TEXT};
}}
QPushButton:hover {{ background: {BG_CARD_HOVER}; border-color: {GRIS_ANTHRACITE}; }}
QPushButton:pressed {{ background: {NOIR_UI}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; border-color: {BORDER_SOFT}; }}

/* bouton primaire (objectName Primary) — filled clair, texte sombre */
QPushButton#Primary {{
    background: {BLANC_OPTIQUE};
    color: {NOIR_CARBONE};
    border: none;
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background: #FFFFFF; }}
QPushButton#Primary:pressed {{ background: {GRIS_BRUME}; }}
QPushButton#Primary:disabled {{ background: {GRIS_ANTHRACITE}; color: {TEXT_DIM}; }}

/* bouton fantôme (icône topbar) */
QPushButton#Ghost {{ background: transparent; border: 1px solid {BORDER_SOFT}; }}
QPushButton#Ghost:hover {{ background: {BG_CARD}; }}

/* toggle Mode édition : éteint = sobre, allumé = accent vert */
QPushButton#EditToggle {{
    background: {BG_FIELD}; border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px; padding: 8px 16px; font-weight: 600;
}}
QPushButton#EditToggle:hover {{ border-color: {GRIS_MINERAL}; }}
QPushButton#EditToggle:checked {{
    background: #1E3A2A; color: #6FE3A0; border: 1px solid #2E5E43;
}}

/* --- chips / tags --- */
QPushButton#Chip {{
    background: transparent;
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 5px 12px;
    color: {TEXT_MUTED};
    font-size: 12px;
}}
QPushButton#Chip:hover {{ border-color: {GRIS_MINERAL}; color: {TEXT}; }}
QPushButton#Chip:checked {{
    background: {BLANC_OPTIQUE};
    color: {NOIR_CARBONE};
    border-color: {BLANC_OPTIQUE};
}}

/* --- item de sidebar --- */
QPushButton#NavItem {{
    background: transparent;
    border: none;
    border-radius: {RADIUS_SM}px;
    padding: 9px 12px;
    text-align: left;
    color: {TEXT_MUTED};
}}
QPushButton#NavItem:hover {{ background: {BG_CARD}; color: {TEXT}; }}
QPushButton#NavItem:checked {{ background: {BG_CARD}; color: {TEXT}; }}

/* --- combobox (tri) --- */
QComboBox {{
    background: {BG_FIELD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    padding: 6px 10px;
}}
QComboBox:hover {{ border-color: {GRIS_ANTHRACITE}; }}
QComboBox QAbstractItemView {{
    background: {NOIR_UI};
    border: 1px solid {BORDER};
    selection-background-color: {GRIS_ANTHRACITE};
    outline: none;
}}
QComboBox::drop-down {{ border: none; width: 22px; }}

/* --- scrollbars discrètes --- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {GRIS_ANTHRACITE}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {GRIS_MINERAL}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ border: none; background: {BG_GRID}; }}

/* --- progress / spin --- */
QProgressBar {{
    background: {BG_FIELD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    text-align: center;
    height: 8px;
}}
QProgressBar::chunk {{ background: {GRIS_MINERAL}; border-radius: 5px; }}
QSpinBox {{
    background: {BG_FIELD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 6px;
}}

/* --- formulaire Manager --- */
QTextEdit {{
    background: {BG_FIELD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
}}
QListWidget {{ background: {BG_GRID}; border: none; outline: none; }}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {BG_CARD}; color: {TEXT}; }}
QToolTip {{ background: {NOIR_UI}; color: {TEXT}; border: 1px solid {BORDER}; }}
"""


def apply(app: QApplication) -> None:
    """Applique le thème global. Inter est chargée depuis les fontes système."""
    # s'assurer qu'Inter est résolvable ; sinon le fallback du QSS prend le relais
    families = set(QFontDatabase.families())
    if "Inter" not in families:
        # tentative de chargement de fontes embarquées (assets/fonts) si présentes
        from pathlib import Path

        fonts_dir = Path(__file__).resolve().parent / "fonts"
        if fonts_dir.is_dir():
            for ttf in fonts_dir.glob("*.ttf"):
                QFontDatabase.addApplicationFont(str(ttf))

    # police de base de l'application (résolution fiable, indépendante du QSS)
    base = QFont("Inter" if "Inter" in QFontDatabase.families() else "Segoe UI", 10)
    base.setStyleStrategy(QFont.PreferAntialias)
    app.setFont(base)

    app.setStyleSheet(build_qss())
