"""Fenêtre principale Viewer — refonte graphique conforme à CHARTE ET DA.

Deux pages dans un QStackedWidget :
  0. Bibliothèque  : topbar + sidebar (nav + filtres) + grille de cartes
  1. Fiche détail  : viewer 3D + panneau de métadonnées (maquette DA2)

Lecture seule sur la base ; le viewer 3D charge le glTF généré par le Manager.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from aclib import config
from aclib.core import paths
from aclib.db import get_session
from aclib.db.models import Asset, AssetFile, Category, Tag
from aclib.ui import anim, icons, theme, widgets
from aclib.ui.flowlayout import FlowLayout
from aclib.ui.range_slider import RangeSlider
from aclib.viewer import export as export_mod
from aclib.viewer.cart import Cart
from aclib.viewer.cart_dialog import CartDialog
from aclib.viewer.export_dialog import ExportDialog
from aclib.viewer.favorites import Favorites

_VIEWER_HTML = Path(__file__).resolve().parent / "web" / "viewer3d.html"

_TYPES_DEFAULT = ["Flacon", "Pot", "Tube", "Bouteille", "Spray", "Coffret"]
_FORMATS = ["C4D", "FBX", "OBJ", "STEP"]
_CAP_MAX = 500
_HEIGHT_MAX = 400

# Tailles de vignettes (page bibliothèque) : (largeur carte, hauteur vignette).
_CARD_SIZES: dict[str, tuple[int, int]] = {
    "Petite": (184, 112),
    "Moyenne": (244, 150),
    "Grande": (320, 196),
}


class ViewerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("A.C.Lib — Bibliothèque 3D")
        self.resize(1320, 820)
        self.cart = Cart()
        self.favs = Favorites()
        self._card_size = "Moyenne"   # taille de vignette par défaut
        self._current_id: int | None = None
        self._export_worker: export_mod.ExportWorker | None = None

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_topbar())

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_library_page())
        self.stack.addWidget(self._build_detail_page())
        outer.addWidget(self.stack, 1)

        outer.addWidget(self._build_status_bar())
        self.setCentralWidget(root)

        self._populate_categories()
        self._reload_grid()
        self._update_cart_btn()
        self.btn_library.setToolTip(str(config.DATA_DIR))

    # ============================================================ TOP BAR
    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(58)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(12)

        # marque ACL
        mark = QLabel("ACL")
        mark.setFixedSize(30, 30)
        mark.setAlignment(Qt.AlignCenter)
        mark.setStyleSheet(
            f"background: {theme.BLANC_OPTIQUE}; color: {theme.NOIR_CARBONE}; "
            f"font-weight: 800; font-size: 11px; border-radius: 7px;"
        )
        brand = QLabel("A.C.Lib")
        brand.setObjectName("Brand")

        self.breadcrumb = QLabel("·  Bibliothèque 3D  ·  Agency")
        self.breadcrumb.setObjectName("Muted")
        self.breadcrumb.setCursor(Qt.PointingHandCursor)
        self.breadcrumb.mousePressEvent = lambda _e: self._go_library()  # retour accueil

        # recherche
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher un volume, un projet, un tag…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(560)
        self.search.addAction(icons.icon("search", theme.TEXT_DIM, 16), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self._reload_grid)

        # actions droite — choisir le dossier de la bibliothèque indexée
        self.btn_library = QPushButton("  Bibliothèque")
        self.btn_library.setObjectName("Ghost")
        self.btn_library.setIcon(icons.icon("folder", theme.TEXT, 16))
        self.btn_library.setCursor(Qt.PointingHandCursor)
        self.btn_library.clicked.connect(self._choose_library)

        self.btn_cart = QPushButton()
        self.btn_cart.setObjectName("Ghost")
        self.btn_cart.setIcon(icons.icon("cart", theme.TEXT, 18))
        self.btn_cart.setCursor(Qt.PointingHandCursor)
        self.btn_cart.clicked.connect(self._open_cart_menu)

        avatar = QLabel(self._initials())
        avatar.setFixedSize(32, 32)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(
            f"background: {theme.BG_CARD}; color: {theme.TEXT}; border: 1px solid {theme.BORDER}; "
            f"border-radius: 16px; font-size: 11px; font-weight: 700;"
        )

        lay.addWidget(mark)
        lay.addWidget(brand)
        lay.addWidget(self.breadcrumb)
        lay.addStretch(1)
        lay.addWidget(self.search, 2)
        lay.addStretch(1)
        lay.addWidget(self.btn_library)
        lay.addWidget(self.btn_cart)
        lay.addWidget(avatar)
        return bar

    # ============================================================ LIBRARY PAGE
    def _build_library_page(self) -> QWidget:
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_sidebar())
        lay.addWidget(self._build_main_area(), 1)
        return page

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(252)
        outer = QVBoxLayout(side)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setStyleSheet(f"background: {theme.BG_PANEL};")
        lay = QVBoxLayout(content)
        lay.setContentsMargins(16, 18, 16, 18)
        lay.setSpacing(8)

        lay.addWidget(widgets.section_label("Bibliothèque"))
        nav_group = QButtonGroup(self)
        nav_group.setExclusive(True)
        self.nav_all = widgets.NavItem("cube", "Tous les volumes", 0)
        self.nav_all.setChecked(True)
        self.nav_fav = widgets.NavItem("star", "Favoris")
        for n in (self.nav_all, self.nav_fav):
            nav_group.addButton(n)
            n.toggled.connect(self._on_nav_changed)
            lay.addWidget(n)

        lay.addSpacing(8)
        lay.addWidget(self._hsep())
        lay.addSpacing(8)

        # contenance (slider + saisie manuelle min/max)
        lay.addWidget(widgets.section_label("Contenance"))
        self.cap_slider = RangeSlider(0, _CAP_MAX)
        lay.addWidget(self.cap_slider)
        lay.addWidget(self._range_inputs(self.cap_slider, _CAP_MAX, " ml"))

        lay.addSpacing(6)
        lay.addWidget(widgets.section_label("Hauteur"))
        self.height_slider = RangeSlider(0, _HEIGHT_MAX)
        lay.addWidget(self.height_slider)
        lay.addWidget(self._range_inputs(self.height_slider, _HEIGHT_MAX, " mm"))

        lay.addSpacing(8)
        lay.addWidget(widgets.section_label("Catégorie"))
        self.cat_box = QWidget(); self.cat_flow = FlowLayout(self.cat_box, spacing=6)
        lay.addWidget(self.cat_box)
        self.cat_chips: list[widgets.Chip] = []
        self._cat_ids: dict[str, int] = {}  # texte chip -> id catégorie

        lay.addSpacing(8)
        lay.addWidget(widgets.section_label("Format"))
        fmt_box = QWidget(); fmt_flow = FlowLayout(fmt_box, spacing=6)
        self.format_chips: list[widgets.Chip] = []
        for f in _FORMATS:
            chip = widgets.Chip(f)
            chip.toggled.connect(self._reload_grid)
            self.format_chips.append(chip)
            fmt_flow.addWidget(chip)
        lay.addWidget(fmt_box)

        lay.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        return side

    def _range_inputs(self, slider: RangeSlider, maximum: int, suffix: str) -> QWidget:
        """Deux champs min/max éditables synchronisés avec le slider."""
        w = QWidget(); w.setStyleSheet("background: transparent;")
        row = QHBoxLayout(w); row.setContentsMargins(0, 2, 0, 0); row.setSpacing(6)
        lo = QSpinBox(); hi = QSpinBox()
        for sb in (lo, hi):
            sb.setRange(0, maximum); sb.setSuffix(suffix)
            sb.setFixedHeight(28)
        lo.setValue(0); hi.setValue(maximum)

        def from_slider(a: int, b: int) -> None:
            lo.blockSignals(True); hi.blockSignals(True)
            lo.setValue(a); hi.setValue(b)
            lo.blockSignals(False); hi.blockSignals(False)

        def to_slider() -> None:
            slider.set_values(lo.value(), hi.value())

        slider.rangeChanged.connect(from_slider)
        slider.rangeChanged.connect(lambda *_: self._reload_grid())
        lo.editingFinished.connect(to_slider)
        hi.editingFinished.connect(to_slider)

        dash = QLabel("—"); dash.setStyleSheet(f"color: {theme.TEXT_DIM}; background: transparent;")
        row.addWidget(lo, 1); row.addWidget(dash); row.addWidget(hi, 1)
        return w

    def _build_main_area(self) -> QWidget:
        area = QWidget()
        area.setObjectName("MainArea")
        lay = QVBoxLayout(area)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)

        # en-tête
        header = QHBoxLayout()
        left = QVBoxLayout(); left.setSpacing(2)
        self.title = widgets.h1("Tous les volumes")
        self.subtitle = widgets.muted("0 résultat")
        left.addWidget(self.title)
        left.addWidget(self.subtitle)
        header.addLayout(left)
        header.addStretch(1)

        # toggle grille/liste
        self.btn_grid = QPushButton(); self.btn_grid.setObjectName("Ghost")
        self.btn_grid.setIcon(icons.icon("grid", theme.TEXT, 18)); self.btn_grid.setCheckable(True)
        self.btn_grid.setChecked(True); self.btn_grid.setFixedWidth(40)
        self.btn_list = QPushButton(); self.btn_list.setObjectName("Ghost")
        self.btn_list.setIcon(icons.icon("list", theme.TEXT_MUTED, 18)); self.btn_list.setCheckable(True)
        self.btn_list.setFixedWidth(40)
        view_group = QButtonGroup(self); view_group.setExclusive(True)
        view_group.addButton(self.btn_grid); view_group.addButton(self.btn_list)

        self.sort = QComboBox()
        self.sort.addItems(["Récents d'abord", "A → Z", "Contenance ↑", "Contenance ↓"])
        self.sort.currentIndexChanged.connect(self._reload_grid)

        # sélecteur de taille de vignettes
        self.size_box = QComboBox()
        self.size_box.addItems(list(_CARD_SIZES.keys()))
        self.size_box.setCurrentText(self._card_size)
        self.size_box.setToolTip("Taille des vignettes")
        self.size_box.currentTextChanged.connect(self._on_size_changed)

        header.addWidget(self.btn_grid)
        header.addWidget(self.btn_list)
        header.addSpacing(8)
        header.addWidget(self.size_box)
        header.addWidget(self.sort)
        lay.addLayout(header)

        # grille scrollable
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.grid_host = QWidget()
        self.grid_host.setStyleSheet(f"background: {theme.BG_GRID};")
        self.grid = FlowLayout(self.grid_host, margin=0, spacing=16)
        # FlowLayout + QScrollArea : la hauteur calculée par heightForWidth n'est
        # pas propagée -> on force la hauteur mini du host pour que le scroll
        # apparaisse au lieu de rogner les dernières cartes.
        self.grid_host.resizeEvent = self._grid_host_resized
        self.scroll.setWidget(self.grid_host)
        lay.addWidget(self.scroll, 1)
        return area

    def _grid_host_resized(self, e) -> None:
        w = self.grid_host.width()
        h = self.grid.heightForWidth(w)
        if h != self.grid_host.minimumHeight():
            self.grid_host.setMinimumHeight(h)
        QWidget.resizeEvent(self.grid_host, e)

    # ============================================================ DETAIL PAGE
    def _build_detail_page(self) -> QWidget:
        page = QWidget()
        lay = QHBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._build_viewer_pane(), 3)
        lay.addWidget(self._build_right_panel(), 2)
        return page

    def _build_viewer_pane(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("DetailArea")
        lay = QVBoxLayout(pane)
        lay.setContentsMargins(24, 24, 16, 24)

        frame = QFrame()
        frame.setStyleSheet(
            f"background: {theme.BG_VIEWER}; border: 1px solid {theme.BORDER_SOFT}; "
            f"border-radius: {theme.RADIUS_CARD}px;"
        )
        fl = QVBoxLayout(frame); fl.setContentsMargins(0, 0, 0, 0)

        self.web = QWebEngineView()
        s = self.web.settings()
        s.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        self.web.setStyleSheet("background: transparent;")
        self.web.setUrl(QUrl.fromLocalFile(str(_VIEWER_HTML)))
        fl.addWidget(self.web)
        lay.addWidget(frame, 1)

        # overlays posés sur le frame
        self._ov_top = QLabel("Aperçu interactif · glTF", frame)
        self._ov_top.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; background: rgba(11,12,14,0.55); "
            f"padding: 4px 10px; border-radius: 6px; font-size: 12px;"
        )
        self._ov_top.move(16, 16); self._ov_top.adjustSize()

        self._ov_hint = QLabel("Cliquez-glissez pour pivoter · molette pour zoomer", frame)
        self._ov_hint.setStyleSheet(f"color: {theme.TEXT_DIM}; background: transparent; font-size: 11px;")
        self._ov_hint.adjustSize()
        self._viewer_frame = frame
        frame.resizeEvent = self._reposition_overlays
        return pane

    def _reposition_overlays(self, _e=None) -> None:
        f = self._viewer_frame
        self._ov_hint.adjustSize()
        self._ov_hint.move(16, f.height() - self._ov_hint.height() - 14)

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("RightPanel")
        panel.setMaximumWidth(420)
        self.right_panel = panel
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(14)

        self.d_title = QLabel("—")
        self.d_title.setStyleSheet(f"color: {theme.TEXT}; font-size: 20px; font-weight: 700;")
        self.d_title.setWordWrap(True)
        self.d_ref = widgets.muted("—", dim=True)
        outer.addWidget(self.d_title)
        outer.addWidget(self.d_ref)

        # tuiles métadonnées 2x2
        self.meta_host = QWidget()
        self.meta_grid = QHBoxLayout(self.meta_host)  # remplacé dynamiquement
        outer.addWidget(self.meta_host)

        outer.addWidget(widgets.section_label("Informations"))
        self.info_host = QVBoxLayout()
        self.info_host.setSpacing(0)
        info_wrap = QWidget(); info_wrap.setLayout(self.info_host)
        outer.addWidget(info_wrap)

        self.tags_host = QWidget(); self.tags_flow = FlowLayout(self.tags_host, spacing=6)
        outer.addWidget(self.tags_host)

        outer.addStretch(1)

        # boutons
        self.btn_open = QPushButton("  Ouvrir le fichier source")
        self.btn_open.setObjectName("Primary")
        self.btn_open.setIcon(icons.icon("download", theme.NOIR_CARBONE, 16))
        self.btn_open.setCursor(Qt.PointingHandCursor)
        self.btn_open.clicked.connect(self._open_source)

        self.btn_copy = QPushButton("  Copier le chemin")
        self.btn_copy.setIcon(icons.icon("copy", theme.TEXT, 16))
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.clicked.connect(self._copy_path)

        self.btn_addcart = QPushButton("  Ajouter au panier")
        self.btn_addcart.setIcon(icons.icon("cart", theme.TEXT, 16))
        self.btn_addcart.setCursor(Qt.PointingHandCursor)
        self.btn_addcart.clicked.connect(self._toggle_cart)

        for b in (self.btn_open, self.btn_copy, self.btn_addcart):
            b.setMinimumHeight(40)
            outer.addWidget(b)
        anim.install_hover(self.btn_open, blur=22, offset_y=4)  # halo bouton primaire
        return panel

    # ============================================================ STATUS BAR
    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(30)
        bar.setStyleSheet(f"background: {theme.BG_APP}; border-top: 1px solid {theme.BORDER_SOFT};")
        lay = QHBoxLayout(bar); lay.setContentsMargins(16, 0, 16, 0)
        self.status = widgets.muted("Prêt.", dim=True)
        self.export_progress = QProgressBar(); self.export_progress.setVisible(False)
        self.export_progress.setMaximumWidth(220)
        lay.addWidget(self.status)
        lay.addStretch(1)
        lay.addWidget(self.export_progress)
        return bar

    # ============================================================ HELPERS
    @staticmethod
    def _hsep() -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet(f"background: {theme.BORDER_SOFT}; max-height: 1px; border: none;")
        return f

    @staticmethod
    def _initials() -> str:
        return "SE"

    def _populate_categories(self) -> None:
        # purge (cas d'un changement de bibliothèque)
        for c in self.cat_chips:
            c.deleteLater()
        self.cat_chips = []
        self._cat_ids = {}
        with get_session() as s:
            cats = [(c.id, c.name) for c in s.query(Category).order_by(Category.name).all()]
        for cid, name in cats:
            chip = widgets.Chip(name)
            chip.toggled.connect(self._reload_grid)
            self._cat_ids[name] = cid
            self.cat_chips.append(chip)
            self.cat_flow.addWidget(chip)

    def _checked(self, chips: list[widgets.Chip]) -> list[str]:
        return [c.text() for c in chips if c.isChecked()]

    def _on_size_changed(self, name: str) -> None:
        if name in _CARD_SIZES:
            self._card_size = name
            self._reload_grid()

    def _on_nav_changed(self, checked: bool) -> None:
        if not checked:
            return
        self.title.setText("Favoris" if self.nav_fav.isChecked() else "Tous les volumes")
        self._reload_grid()

    # ============================================================ QUERY + GRID
    def _query_assets(self) -> list[Asset]:
        with get_session() as s:
            q = s.query(Asset)
            text = self.search.text().strip()
            if text:
                like = f"%{text}%"
                q = q.outerjoin(Asset.tags).filter(
                    Asset.name.ilike(like) | Asset.project.ilike(like)
                    | Asset.client.ilike(like) | Tag.name.ilike(like)
                ).distinct()
            if getattr(self, "nav_fav", None) is not None and self.nav_fav.isChecked():
                fav_ids = self.favs.ids
                q = q.filter(Asset.id.in_(fav_ids)) if fav_ids else q.filter(False)
            cat_names = self._checked(self.cat_chips)
            if cat_names:
                ids = [self._cat_ids[n] for n in cat_names if n in self._cat_ids]
                if ids:
                    q = q.join(Asset.categories).filter(Category.id.in_(ids)).distinct()
            fmts = [f.lower() for f in self._checked(self.format_chips)]
            if fmts:
                q = q.join(AssetFile).filter(AssetFile.fmt.in_(fmts)).distinct()
            lo, hi = self.cap_slider.values()
            if lo > 0:
                q = q.filter(Asset.capacity_ml >= lo)
            if hi < _CAP_MAX:
                q = q.filter(Asset.capacity_ml <= hi)
            hlo, hhi = self.height_slider.values()
            if hlo > 0:
                q = q.filter(Asset.height_mm >= hlo)
            if hhi < _HEIGHT_MAX:
                q = q.filter(Asset.height_mm <= hhi)

            order = self.sort.currentIndex()
            if order == 1:
                q = q.order_by(Asset.name)
            elif order == 2:
                q = q.order_by(Asset.capacity_ml.asc().nulls_last())
            elif order == 3:
                q = q.order_by(Asset.capacity_ml.desc().nulls_last())
            else:
                q = q.order_by(Asset.created_at.desc())

            assets = q.all()
            return [self._to_dict(a) for a in assets]

    def _to_dict(self, a: Asset) -> dict:
        src = a.source_file()
        thumb = str(config.PREVIEW_DIR / a.thumbnail_relpath) if a.thumbnail_relpath else None
        return {
            "id": a.id, "name": a.name, "capacity_label": a.capacity_label,
            "primary_format": (src.fmt if src else (a.formats()[0] if a.formats() else None)),
            "thumb_path": thumb, "height_mm": a.height_mm, "diameter_mm": a.diameter_mm,
            "weight_bytes": a.weight_bytes, "favorite": a.id in self.favs,
        }

    def _clear_layout(self, layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _reload_grid(self) -> None:
        data = self._query_assets()
        self._clear_layout(self.grid)
        cw, th = _CARD_SIZES.get(self._card_size, _CARD_SIZES["Moyenne"])
        for d in data:
            card = widgets.AssetCard(d, card_w=cw, thumb_h=th)
            card.clicked.connect(self._open_detail)
            card.favoriteToggled.connect(self._on_favorite_toggled)
            self.grid.addWidget(card)
        n = len(data)
        self.subtitle.setText(f"{n} résultat" + ("s" if n != 1 else ""))
        self.status.setText(f"{n} volume(s).")
        # recalcule la hauteur du host pour la barre de défilement
        self.grid_host.setMinimumHeight(self.grid.heightForWidth(self.grid_host.width()))

    def _on_favorite_toggled(self, asset_id: int, on: bool) -> None:
        self.favs.toggle(asset_id)
        # si on est dans la vue Favoris, retirer une étoile doit rafraîchir la grille
        if self.nav_fav.isChecked() and not on:
            self._reload_grid()

    # ============================================================ DETAIL
    def _open_detail(self, asset_id: int) -> None:
        self._current_id = asset_id
        with get_session() as s:
            a = s.get(Asset, asset_id)
            if a is None:
                return
            src = a.source_file()
            self.d_title.setText(a.name or "—")
            from datetime import datetime
            ref = f"Réf. {a.id:05d}"
            if a.year:
                ref += f" · {a.year}"
            self.d_ref.setText(ref)

            # tuiles
            self._rebuild_meta([
                ("Contenance", a.capacity_label or "—"),
                ("Hauteur totale", f"{round(a.height_mm)} mm" if a.height_mm else "—"),
                ("Diamètre", f"{round(a.diameter_mm)} mm" if a.diameter_mm else "—"),
                ("Poids modèle", f"{a.weight_bytes/1048576:.1f} Mo" if a.weight_bytes else "—"),
            ])

            # informations
            self._clear_layout(self.info_host)
            self.info_host.addWidget(widgets.info_row("Projet d'origine", a.project or "—"))
            self.info_host.addWidget(widgets.info_row("Client", a.client or "—"))
            self.info_host.addWidget(widgets.info_row("Format source", src.relpath.split("/")[-1] if src else "—"))
            self.info_host.addWidget(widgets.info_row("Auteur", a.author or "—"))
            self.info_host.addWidget(widgets.info_row("Polygones", f"{a.poly_count:,} tris".replace(",", " ") if a.poly_count else "—"))

            # tags
            self._clear_layout(self.tags_flow)
            for t in a.tags:
                self.tags_flow.addWidget(widgets.Chip(t.name, checkable=False))

            self.btn_addcart.setText("  Retirer du panier" if a.id in self.cart else "  Ajouter au panier")

            # 3D — passe par le cache local (file:// NAS UNC non fiable en WebEngine)
            url = ""
            if a.gltf_relpath:
                from aclib.ui import model_cache
                url = model_cache.local_url(config.PREVIEW_DIR / a.gltf_relpath) or ""
            self.web.page().runJavaScript(f'window.loadModel && window.loadModel("{url}");')

        self.breadcrumb.setText(f"·  Bibliothèque 3D  ›  {self.d_title.text()}")
        self.stack.setCurrentIndex(1)
        self._reposition_overlays()
        # entrée animée du panneau d'infos : glissement seul (contenu visible)
        anim.slide_in(self.right_panel, dy=18)

    def _rebuild_meta(self, tiles: list[tuple[str, str]]) -> None:
        # reconstruit une grille 2x2 de MetaTile
        old = self.meta_host.layout()
        if old is not None:
            self._clear_layout(old)
            QWidget().setLayout(old)  # détache l'ancien layout
        grid = QVBoxLayout(self.meta_host)
        grid.setContentsMargins(0, 0, 0, 0); grid.setSpacing(10)
        for i in range(0, len(tiles), 2):
            row = QHBoxLayout(); row.setSpacing(10)
            for label, value in tiles[i:i + 2]:
                row.addWidget(widgets.MetaTile(label, value))
            grid.addLayout(row)

    def _go_library(self) -> None:
        self.breadcrumb.setText("·  Bibliothèque 3D  ·  Agency")
        self.stack.setCurrentIndex(0)

    # ============================================================ FILE ACTIONS
    def _current_source_relpath(self) -> str | None:
        if self._current_id is None:
            return None
        with get_session() as s:
            a = s.get(Asset, self._current_id)
            src = a.source_file() if a else None
            return src.relpath if src else None

    def _open_source(self) -> None:
        rel = self._current_source_relpath()
        if not rel:
            return
        abs_path = paths.to_abs(rel)
        if not abs_path.exists():
            QMessageBox.warning(self, "Introuvable", f"Fichier absent (NAS monté ?) :\n{abs_path}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(abs_path)))

    def _copy_path(self) -> None:
        rel = self._current_source_relpath()
        if rel:
            QGuiApplication.clipboard().setText(str(paths.to_abs(rel)))
            self.status.setText("Chemin copié.")

    # ============================================================ CART + EXPORT
    def _toggle_cart(self) -> None:
        if self._current_id is None:
            return
        present = self.cart.toggle(self._current_id)
        self.btn_addcart.setText("  Retirer du panier" if present else "  Ajouter au panier")
        self._update_cart_btn()

    def _update_cart_btn(self) -> None:
        n = len(self.cart)
        self.btn_cart.setText(f"  {n}" if n else "")
        self.status.setText(f"Panier : {n} volume(s).")

    def _open_cart_menu(self) -> None:
        if len(self.cart) == 0:
            QMessageBox.information(self, "Panier vide", "Ajouter des volumes au panier d'abord.")
            return
        dlg = CartDialog(self.cart, self)
        result = dlg.exec()
        # le panier a pu changer (retraits / vidage) -> rafraîchit le badge + la fiche
        self._update_cart_btn()
        if self._current_id is not None:
            self.btn_addcart.setText(
                "  Retirer du panier" if self._current_id in self.cart else "  Ajouter au panier"
            )
        if result == CartDialog.Accepted:
            self._send_cart(dlg.selected_formats(), dlg.dest())

    def _send_cart(self, formats: set[str], dest: str) -> None:
        if not formats or not dest:
            return
        self.export_progress.setVisible(True); self.export_progress.setValue(0)
        self._export_worker = export_mod.ExportWorker(self.cart.ids, formats, dest)
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.done.connect(self._on_export_done)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_worker.start()

    def _export(self) -> None:
        formats = export_mod.available_formats(self.cart.ids)
        dlg = ExportDialog(formats, self)
        if dlg.exec() != ExportDialog.Accepted:
            return
        self.export_progress.setVisible(True); self.export_progress.setValue(0)
        self._export_worker = export_mod.ExportWorker(self.cart.ids, dlg.selected_formats(), dlg.dest())
        self._export_worker.progress.connect(self._on_export_progress)
        self._export_worker.done.connect(self._on_export_done)
        self._export_worker.failed.connect(self._on_export_failed)
        self._export_worker.start()

    def _on_export_progress(self, msg: str, cur: int, total: int) -> None:
        self.export_progress.setMaximum(total); self.export_progress.setValue(cur)
        self.status.setText(f"Export : {msg} ({cur}/{total})")

    def _on_export_done(self, copied: int, skipped: int) -> None:
        self.export_progress.setVisible(False)
        QMessageBox.information(self, "Export terminé", f"{copied} fichier(s) copié(s), {skipped} ignoré(s).")
        self.status.setText("Export terminé.")

    def _on_export_failed(self, msg: str) -> None:
        self.export_progress.setVisible(False)
        QMessageBox.critical(self, "Export échoué", msg)

    # ============================================================ BIBLIOTHÈQUE
    def _choose_library(self) -> None:
        from aclib import library

        start = str(library.current())
        folder = QFileDialog.getExistingDirectory(
            self, "Dossier de la bibliothèque (base + aperçus indexés)", start
        )
        if not folder:
            return
        library.switch(folder)
        self._refresh_library()
        QMessageBox.information(
            self, "Bibliothèque",
            f"Bibliothèque : {folder}\n\n"
            "C'est le dossier rempli par le Manager (base library.db + previews). "
            "Pointe le Manager ET le Viewer sur le MÊME dossier (ex. sur le NAS) "
            "pour qu'ils partagent les mêmes volumes.",
        )

    def _refresh_library(self) -> None:
        """Recharge l'UI après changement de bibliothèque."""
        from aclib import library

        for c in self.format_chips:
            c.setChecked(False)
        self.cap_slider.set_values(0, _CAP_MAX)
        self.height_slider.set_values(0, _HEIGHT_MAX)
        self.search.clear()
        self._populate_categories()
        self._reload_grid()
        self._go_library()
        self.btn_library.setToolTip(str(library.current()))
        self.status.setText(f"Bibliothèque : {library.current()}")
