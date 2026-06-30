"""Fenêtre principale Manager — création / mise à jour des fiches.

Gauche : catégories (dossiers) + liste des volumes (multi-sélection Shift/Ctrl,
drag-drop vers une catégorie, clic-droit). Droite : fiche en lecture, déver-
rouillée par « Éditer » puis « Valider ». Import par glisser-déposer + scan.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStyle,
    QStyledItemDelegate,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from aclib import config
from aclib.core import paths
from aclib.db import get_session
from aclib.db.models import Asset, Category, Tag
from aclib.ui import anim, icons, theme, widgets
from aclib.manager.index_worker import IndexWorker

_TYPES = ["Flacon", "Pot", "Tube", "Bouteille", "Spray", "Coffret", "Bouchon", "Autre"]
_VIEWER_HTML = Path(__file__).resolve().parents[1] / "viewer" / "web" / "viewer3d.html"

_DOT_OK = "#5BD68A"
_DOT_KO = "#E0B23B"

# sentinelles de filtre (catégories virtuelles, pas en base)
_UNCAT = "__uncat__"   # volumes sans aucune catégorie
_NEW = "__new__"       # nouveaux volumes non encore validés (reviewed == False)


def _status_of(a: Asset) -> str:
    return "complet" if (a.volume_type and a.capacity_ml) else "incomplet"


# ============================================================ DELEGATE (lignes)
class VolumeDelegate(QStyledItemDelegate):
    """Dessine une ligne volume (vignette + nom + sous-titre + pastille statut).

    Via un delegate (et non setItemWidget) pour garder la sélection multiple
    Shift/Ctrl et le drag natifs de QListWidget.
    """

    ROW_H = 60

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._cache: dict[str, QPixmap] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def sizeHint(self, opt, idx) -> QSize:  # noqa: N802
        return QSize(opt.rect.width(), self.ROW_H)

    def _thumb(self, path: str | None) -> QPixmap:
        key = path or "_bottle"
        pm = self._cache.get(key)
        if pm is None:
            if path and Path(path).exists():
                pm = QPixmap(path).scaled(42, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            else:
                pm = icons.pixmap("bottle", theme.TEXT_DIM, 24)
            self._cache[key] = pm
        return pm

    def paint(self, p: QPainter, opt, idx) -> None:  # noqa: N802
        d = idx.data(Qt.UserRole) or {}
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = opt.rect.adjusted(4, 2, -6, -2)

        selected = bool(opt.state & QStyle.State_Selected)
        hover = bool(opt.state & QStyle.State_MouseOver)
        p.setPen(Qt.NoPen)
        if selected:
            p.setBrush(QColor(theme.BG_CARD)); p.drawRoundedRect(r, 8, 8)
        elif hover:
            p.setBrush(QColor(theme.BG_FIELD)); p.drawRoundedRect(r, 8, 8)

        # vignette
        th = QRect(r.left() + 8, r.top() + (r.height() - 42) // 2, 42, 42)
        p.setBrush(QColor(theme.BG_THUMB)); p.drawRoundedRect(th, 7, 7)
        pm = self._thumb(d.get("thumb_path"))
        p.drawPixmap(int(th.center().x() - pm.width() / 2), int(th.center().y() - pm.height() / 2), pm)

        # textes
        tx = th.right() + 12
        right = r.right() - 24
        f = QFont(p.font()); f.setBold(True); f.setPointSize(10); p.setFont(f)
        fm = QFontMetrics(f)
        p.setPen(QColor(theme.TEXT))
        p.drawText(QRect(tx, r.top() + 11, right - tx, 20), Qt.AlignVCenter | Qt.AlignLeft,
                   fm.elidedText(d.get("name", ""), Qt.ElideRight, right - tx))
        f2 = QFont(p.font()); f2.setBold(False); f2.setPointSize(8); p.setFont(f2)
        p.setPen(QColor(theme.TEXT_DIM))
        p.drawText(QRect(tx, r.top() + 31, right - tx, 18), Qt.AlignVCenter | Qt.AlignLeft,
                   d.get("sub", ""))

        # NEW (jamais édité) : badge accent ; sinon pastille de statut
        if d.get("new"):
            bw, bh = 34, 16
            badge = QRect(r.right() - bw - 2, r.center().y() - bh // 2, bw, bh)
            p.setBrush(QColor("#6FE3A0")); p.setPen(Qt.NoPen)
            p.drawRoundedRect(badge, 5, 5)
            bf = QFont(p.font()); bf.setBold(True); bf.setPointSize(7); p.setFont(bf)
            p.setPen(QColor(theme.NOIR_CARBONE))
            p.drawText(badge, Qt.AlignCenter, "NEW")
        else:
            p.setBrush(QColor(_DOT_OK if d.get("status") == "complet" else _DOT_KO))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPoint(r.right() - 8, r.center().y()), 5, 5)
        p.restore()


# ============================================================ CATEGORIES (drop)
class CategoryList(QListWidget):
    """Liste des catégories : accepte le dépôt de volumes (drag depuis la liste)."""

    dropVolumes = Signal(object)  # id de catégorie (None = « Tous »)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def _is_internal(self, e) -> bool:
        return e.source() is not None and e.source() is not self

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if self._is_internal(e):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e) -> None:  # noqa: N802
        if self._is_internal(e):
            it = self.itemAt(e.position().toPoint())
            if it is not None:
                self.setCurrentItem(it)
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e) -> None:  # noqa: N802
        if self._is_internal(e):
            it = self.itemAt(e.position().toPoint())
            if it is not None:
                self.dropVolumes.emit(it.data(Qt.UserRole))
                e.acceptProposedAction()
                return
        e.ignore()


class ManagerWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("A.C.Lib Manager — création & mise à jour")
        self.resize(1180, 760)
        self.setAcceptDrops(True)
        self._worker: IndexWorker | None = None
        self._current_id: int | None = None
        self._filter_cat: int | None = None  # catégorie filtrée (None = toutes)
        self._editing = False

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        outer.addWidget(self._build_topbar())

        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._build_list_panel())
        split.addWidget(self._build_edit_panel())
        split.setStretchFactor(0, 0); split.setStretchFactor(1, 1)
        split.setSizes([380, 800])
        outer.addWidget(split, 1)

        outer.addWidget(self._build_status_bar())
        self.setCentralWidget(root)
        self._reload_categories()
        self._reload_list()
        self._show_empty_edit()

    # ============================================================ TOP BAR
    def _build_topbar(self) -> QWidget:
        bar = QWidget(); bar.setObjectName("TopBar"); bar.setFixedHeight(58)
        lay = QHBoxLayout(bar); lay.setContentsMargins(16, 0, 16, 0); lay.setSpacing(12)

        mark = QLabel("ACL"); mark.setFixedSize(30, 30); mark.setAlignment(Qt.AlignCenter)
        mark.setStyleSheet(
            f"background: {theme.BLANC_OPTIQUE}; color: {theme.NOIR_CARBONE}; "
            f"font-weight: 800; font-size: 11px; border-radius: 7px;"
        )
        brand = QLabel("A.C.Lib Manager"); brand.setObjectName("Brand")
        crumb = QLabel("·  Indexation & fiches"); crumb.setObjectName("Muted")

        self.btn_library = QPushButton("  Bibliothèque")
        self.btn_library.setObjectName("Ghost")
        self.btn_library.setIcon(icons.icon("cube", theme.TEXT, 16))
        self.btn_library.setCursor(Qt.PointingHandCursor)
        self.btn_library.clicked.connect(self._choose_library)
        self.btn_library.setToolTip(str(config.DATA_DIR))

        self.btn_refresh = QPushButton()
        self.btn_refresh.setObjectName("Ghost")
        self.btn_refresh.setIcon(icons.icon("rotate", theme.TEXT, 16))
        self.btn_refresh.setToolTip("Rafraîchir (nouveaux volumes)")
        self.btn_refresh.setFixedWidth(40)
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(self._refresh)

        # --- bouton DEV (temporaire) : régénère tous les aperçus + miniatures ---
        self.btn_regen = QPushButton("⟳ Régén (dev)")
        self.btn_regen.setCursor(Qt.PointingHandCursor)
        self.btn_regen.setStyleSheet(
            "QPushButton { background: #3a2a12; color: #E0B23B; border: 1px dashed #E0B23B; "
            "border-radius: 8px; padding: 8px 12px; font-weight: 600; }"
            "QPushButton:hover { background: #4a360f; }"
        )
        self.btn_regen.setToolTip("DEV : force la reconversion glb (fix_normals) + re-rendu des miniatures de TOUTE la bibliothèque")
        self.btn_regen.clicked.connect(self._force_regen)

        self.btn_folder = QPushButton("  Indexer un dossier…")
        self.btn_folder.setObjectName("Primary")
        self.btn_folder.setIcon(icons.icon("import", theme.NOIR_CARBONE, 16))
        self.btn_folder.setCursor(Qt.PointingHandCursor)
        self.btn_folder.clicked.connect(self._index_folder)
        anim.install_hover(self.btn_folder, blur=20, offset_y=4)

        avatar = QLabel("SE"); avatar.setFixedSize(32, 32); avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(
            f"background: {theme.BG_CARD}; color: {theme.TEXT}; border: 1px solid {theme.BORDER}; "
            f"border-radius: 16px; font-size: 11px; font-weight: 700;"
        )

        lay.addWidget(mark); lay.addWidget(brand); lay.addWidget(crumb)
        lay.addStretch(1)
        lay.addWidget(self.btn_regen)
        lay.addWidget(self.btn_library); lay.addWidget(self.btn_refresh)
        lay.addWidget(self.btn_folder); lay.addWidget(avatar)
        return bar

    # ============================================================ LIST PANEL
    def _build_list_panel(self) -> QWidget:
        panel = QWidget(); panel.setObjectName("Sidebar"); panel.setMinimumWidth(360)
        lay = QVBoxLayout(panel); lay.setContentsMargins(16, 18, 12, 18); lay.setSpacing(16)

        # ===== Encart Catégories =====
        cat_card = QFrame(); cat_card.setObjectName("SideCard")
        cat_card.setStyleSheet(self._card_qss())
        cl = QVBoxLayout(cat_card); cl.setContentsMargins(14, 12, 14, 14); cl.setSpacing(10)

        chead = QHBoxLayout()
        chead.addWidget(widgets.section_label("Catégories"))
        chead.addStretch(1)
        btn_newcat = QPushButton()
        btn_newcat.setObjectName("Ghost"); btn_newcat.setFixedSize(26, 22)
        btn_newcat.setIcon(icons.icon("plus", theme.TEXT, 15))
        btn_newcat.setToolTip("Nouvelle catégorie"); btn_newcat.setCursor(Qt.PointingHandCursor)
        btn_newcat.clicked.connect(lambda: self._new_category())
        chead.addWidget(btn_newcat)
        cl.addLayout(chead)

        self.cat_list = CategoryList()
        self.cat_list.setMaximumHeight(140)
        self.cat_list.setStyleSheet(self._list_qss())
        self.cat_list.currentItemChanged.connect(self._on_category_changed)
        self.cat_list.dropVolumes.connect(self._assign_selected_to)
        self.cat_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cat_list.customContextMenuRequested.connect(self._category_menu)
        cl.addWidget(self.cat_list)
        lay.addWidget(cat_card)

        # ===== Encart Volumes =====
        vol_card = QFrame(); vol_card.setObjectName("SideCard")
        vol_card.setStyleSheet(self._card_qss())
        vl = QVBoxLayout(vol_card); vl.setContentsMargins(14, 12, 14, 14); vl.setSpacing(10)

        head = QHBoxLayout()
        self.lbl_count = QLabel("Volumes"); self.lbl_count.setObjectName("H2")
        head.addWidget(self.lbl_count); head.addStretch(1)
        vl.addLayout(head)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filtrer par nom, projet…")
        self.search.setFixedHeight(30)   # champ compact
        self.search.setStyleSheet("padding: 4px 10px; font-size: 12px;")
        self.search.addAction(icons.icon("search", theme.TEXT_DIM, 15), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self._reload_list)
        vl.addWidget(self.search)

        self.vol_list = QListWidget()
        self._delegate = VolumeDelegate(self.vol_list)
        self.vol_list.setItemDelegate(self._delegate)
        self.vol_list.setSelectionMode(QAbstractItemView.ExtendedSelection)  # Shift + Ctrl
        self.vol_list.setMouseTracking(True)
        self.vol_list.setDragEnabled(True)
        self.vol_list.setDragDropMode(QAbstractItemView.DragOnly)
        self.vol_list.setUniformItemSizes(True)
        self.vol_list.setSpacing(1)
        self.vol_list.setStyleSheet(self._list_qss())
        self.vol_list.currentItemChanged.connect(self._on_volume_changed)
        self.vol_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.vol_list.customContextMenuRequested.connect(self._volume_menu)
        vl.addWidget(self.vol_list, 1)
        lay.addWidget(vol_card, 1)
        return panel

    @staticmethod
    def _card_qss() -> str:
        return (
            f"QFrame#SideCard {{ background: {theme.BG_CARD}; "
            f"border: 1px solid {theme.BORDER_SOFT}; border-radius: {theme.RADIUS_CARD}px; }}"
        )

    @staticmethod
    def _list_qss() -> str:
        return (
            f"QListWidget {{ background: {theme.BG_PANEL}; border: none; outline: none; }}"
            f"QListWidget::item {{ color: {theme.TEXT}; padding: 6px 8px; border-radius: 7px; }}"
            f"QListWidget::item:selected {{ background: {theme.BG_CARD}; color: {theme.TEXT}; }}"
            # scrollbar fine et discrète
            f"QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px; }}"
            f"QScrollBar::handle:vertical {{ background: {theme.GRIS_ANTHRACITE}; border-radius: 3px; min-height: 24px; }}"
            f"QScrollBar::handle:vertical:hover {{ background: {theme.GRIS_MINERAL}; }}"
            f"QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}"
            f"QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}"
        )

    # ============================================================ EDIT PANEL
    def _build_edit_panel(self) -> QWidget:
        wrap = QWidget(); wrap.setObjectName("MainArea")
        outer = QVBoxLayout(wrap); outer.setContentsMargins(0, 0, 0, 0)

        self.edit_scroll = QScrollArea(); self.edit_scroll.setWidgetResizable(True)
        host = QWidget(); host.setStyleSheet(f"background: {theme.BG_GRID};")
        lay = QVBoxLayout(host); lay.setContentsMargins(28, 24, 28, 24); lay.setSpacing(16)

        head = QHBoxLayout()
        self.f_name = QLineEdit(); self.f_name.setPlaceholderText("Nom du volume")
        self.f_name.setStyleSheet(
            f"font-size: 20px; font-weight: 700; background: transparent; border: none; "
            f"border-bottom: 1px solid {theme.BORDER_SOFT}; border-radius: 0; padding: 4px 0;"
        )
        self.lbl_status = QLabel("—"); self.lbl_status.setStyleSheet(f"color: {theme.TEXT_DIM};")
        head.addWidget(self.f_name, 1); head.addWidget(self.lbl_status)
        lay.addLayout(head)

        lay.addWidget(self._build_preview3d())

        lay.addWidget(widgets.section_label("Caractéristiques (saisi)"))
        form = QFormLayout(); form.setSpacing(10); form.setLabelAlignment(Qt.AlignRight)
        self.f_type = QComboBox(); self.f_type.setEditable(True); self.f_type.addItems([""] + _TYPES)
        self.f_cap_label = QLineEdit(); self.f_cap_label.setPlaceholderText("250 ml")
        self.f_cap_ml = QSpinBox(); self.f_cap_ml.setMaximum(1_000_000); self.f_cap_ml.setSuffix(" ml")
        self.f_project = QLineEdit()
        self.f_client = QLineEdit()
        self.f_year = QSpinBox(); self.f_year.setRange(0, 2100)
        self.f_author = QLineEdit()
        self.f_notes = QTextEdit(); self.f_notes.setFixedHeight(70)
        form.addRow("Type", self.f_type)
        form.addRow("Contenance", self.f_cap_label)
        form.addRow("Contenance (ml)", self.f_cap_ml)
        form.addRow("Projet", self.f_project)
        form.addRow("Client", self.f_client)
        form.addRow("Année", self.f_year)
        form.addRow("Auteur", self.f_author)
        form.addRow("Notes", self.f_notes)
        lay.addLayout(form)

        lay.addWidget(widgets.section_label("Tags"))
        self.f_tags = widgets.TagEditor()
        lay.addWidget(self.f_tags)

        lay.addWidget(widgets.section_label("Auto (lecture seule)"))
        self.meta_host = QWidget(); QVBoxLayout(self.meta_host)
        lay.addWidget(self.meta_host)
        self.lbl_source = QLabel("—"); self.lbl_source.setObjectName("Dim")
        self.lbl_source.setWordWrap(True); self.lbl_source.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.lbl_source)

        # champs verrouillables
        self._fields = [
            self.f_name, self.f_type, self.f_cap_label, self.f_cap_ml,
            self.f_project, self.f_client, self.f_year, self.f_author,
            self.f_notes, self.f_tags,
        ]

        self.edit_scroll.setWidget(host)

        # --- barre d'actions FIXE (hors du scroll, toujours visible) ---
        # vue = [Éditer][Supprimer] ; édition = [Valider][Annuler][Supprimer]
        self.action_bar = QWidget()
        self.action_bar.setObjectName("ActionBar")
        # sélecteur #ActionBar : le fond ne « fuit » PAS sur les boutons enfants
        # (sinon le texte noir du bouton Primary devient invisible sur fond sombre)
        self.action_bar.setStyleSheet(
            f"#ActionBar {{ background: {theme.BG_PANEL}; border-top: 1px solid {theme.BORDER_SOFT}; }}"
        )
        ab = QHBoxLayout(self.action_bar); ab.setContentsMargins(28, 12, 28, 12); ab.setSpacing(10)

        # toggle persistant : Mode édition <-> Stop édition
        self.btn_edit = QPushButton("Mode édition")
        self.btn_edit.setObjectName("EditToggle")
        self.btn_edit.setCheckable(True)
        self.btn_edit.clicked.connect(lambda: self._set_editing(self.btn_edit.isChecked()))

        # Valider : enregistre MAIS reste en mode édition (saisie rapide en série)
        self.btn_save = QPushButton("Valider")
        self.btn_save.setObjectName("Primary")
        self.btn_save.clicked.connect(self._save)

        self.btn_cancel = QPushButton("Annuler")
        self.btn_cancel.clicked.connect(self._cancel_edit)

        self.btn_delete = QPushButton("Supprimer")
        self.btn_delete.setIcon(icons.icon("trash", theme.TEXT, 16))
        self.btn_delete.clicked.connect(self._delete)

        for b in (self.btn_edit, self.btn_save, self.btn_cancel, self.btn_delete):
            b.setCursor(Qt.PointingHandCursor); b.setMinimumHeight(38)
        ab.addWidget(self.btn_edit)
        ab.addWidget(self.btn_save, 1)
        ab.addWidget(self.btn_cancel)
        ab.addStretch(0)
        ab.addWidget(self.btn_delete)

        outer.addWidget(self.edit_scroll, 1)
        outer.addWidget(self.action_bar)

        self.empty_edit = QLabel("Sélectionnez un volume — ou glissez des fichiers 3D ici.")
        self.empty_edit.setAlignment(Qt.AlignCenter)
        self.empty_edit.setStyleSheet(f"color: {theme.TEXT_DIM}; background: {theme.BG_GRID};")
        outer.addWidget(self.empty_edit, 1)
        return wrap

    def _build_preview3d(self) -> QWidget:
        frame = QFrame(); frame.setMinimumHeight(360)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        frame.setStyleSheet(
            f"background: {theme.BG_VIEWER}; border: 1px solid {theme.BORDER_SOFT}; "
            f"border-radius: {theme.RADIUS_CARD}px;"
        )
        fl = QVBoxLayout(frame); fl.setContentsMargins(0, 0, 0, 0)
        self.web = QWebEngineView()
        s = self.web.settings()
        s.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        self.web.setUrl(QUrl.fromLocalFile(str(_VIEWER_HTML)))
        fl.addWidget(self.web)

        self._ov = QLabel("Aperçu 3D · glTF", frame)
        self._ov.setStyleSheet(
            f"color: {theme.TEXT_MUTED}; background: rgba(11,12,14,0.55); "
            f"padding: 3px 9px; border-radius: 6px; font-size: 11px;"
        )
        self._ov.move(12, 12); self._ov.adjustSize()
        return frame

    def _load_preview(self, gltf_relpath: str | None) -> None:
        url = ""
        if gltf_relpath:
            from aclib.ui import model_cache
            url = model_cache.local_url(config.PREVIEW_DIR / gltf_relpath) or ""
        self.web.page().runJavaScript(f'window.loadModel && window.loadModel("{url}");')

    # ============================================================ STATUS BAR
    def _build_status_bar(self) -> QWidget:
        bar = QWidget(); bar.setFixedHeight(30)
        bar.setStyleSheet(f"background: {theme.BG_APP}; border-top: 1px solid {theme.BORDER_SOFT};")
        lay = QHBoxLayout(bar); lay.setContentsMargins(16, 0, 16, 0)
        self.status = widgets.muted(f"NAS : {self._nas_label()}", dim=True)
        self.progress = QProgressBar(); self.progress.setVisible(False); self.progress.setMaximumWidth(240)
        lay.addWidget(self.status); lay.addStretch(1); lay.addWidget(self.progress)
        return bar

    @staticmethod
    def _nas_label() -> str:
        try:
            return str(config.nas_root())
        except Exception:
            return "non configuré"

    # ============================================================ DRAG & DROP (fichiers)
    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802
        paths_ = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        paths_ = [p for p in paths_ if p]
        if paths_:
            # un .c4d déposé est IMPORTÉ dans la biblio (copie native + export
            # FBX/OBJ via c4dpy) puis indexé.
            self._run_index(paths_, materialize_c4d=True)

    # ============================================================ CATÉGORIES
    def _reload_categories(self) -> None:
        prev = self._filter_cat
        self.cat_list.blockSignals(True)
        self.cat_list.clear()
        all_item = QListWidgetItem("  Tous les volumes")
        all_item.setIcon(icons.icon("cube", theme.TEXT_MUTED, 16))
        all_item.setData(Qt.UserRole, None)
        self.cat_list.addItem(all_item)
        select_item = all_item
        with get_session() as s:
            cats = s.query(Category).order_by(Category.name).all()
            counts = {c.id: len(c.assets) for c in cats}
            names = {c.id: c.name for c in cats}
            uncat = s.query(Asset).filter(~Asset.categories.any()).count()
            new_count = s.query(Asset).filter(Asset.reviewed.is_(False)).count()
        # entrée « Nouveaux » (volumes non encore validés ; sortent à la validation)
        new_item = QListWidgetItem(f"  Nouveaux   ({new_count})")
        new_item.setIcon(icons.icon("star", theme.TEXT_DIM, 16))
        new_item.setData(Qt.UserRole, _NEW)
        self.cat_list.addItem(new_item)
        if prev == _NEW:
            select_item = new_item
        # entrée « Sans catégorie » (volumes non classés)
        uncat_item = QListWidgetItem(f"  Sans catégorie   ({uncat})")
        uncat_item.setIcon(icons.icon("folder", theme.TEXT_DIM, 16))
        uncat_item.setData(Qt.UserRole, _UNCAT)
        self.cat_list.addItem(uncat_item)
        if prev == _UNCAT:
            select_item = uncat_item
        for cid, name in names.items():
            it = QListWidgetItem(f"  {name}   ({counts.get(cid, 0)})")
            it.setIcon(icons.icon("folder", theme.TEXT_MUTED, 16))
            it.setData(Qt.UserRole, cid)
            self.cat_list.addItem(it)
            if cid == prev:
                select_item = it
        self.cat_list.setCurrentItem(select_item)
        self.cat_list.blockSignals(False)

    def _on_category_changed(self, cur, _prev) -> None:
        self._filter_cat = cur.data(Qt.UserRole) if cur else None
        self._reload_list()

    def _new_category(self, preselect_assets: list[int] | None = None) -> int | None:
        name, ok = QInputDialog.getText(self, "Nouvelle catégorie", "Nom de la catégorie :")
        name = name.strip()
        if not (ok and name):
            return None
        with get_session() as s:
            cat = s.query(Category).filter(Category.name == name).first()
            if cat is None:
                cat = Category(name=name); s.add(cat); s.flush()
            cid = cat.id
            if preselect_assets:
                for aid in preselect_assets:
                    a = s.get(Asset, aid)
                    if a and cat not in a.categories:
                        a.categories.append(cat)
        self._reload_categories()
        self._reload_list()
        return cid

    def _assign_selected_to(self, cat_id) -> None:
        if cat_id is None:
            return  # dépôt sur « Tous » = sans effet
        ids = self._selected_ids()
        if not ids:
            return
        with get_session() as s:
            cat = s.get(Category, cat_id)
            if cat is None:
                return
            for aid in ids:
                a = s.get(Asset, aid)
                if a and cat not in a.categories:
                    a.categories.append(cat)
            cname = cat.name
        self._reload_categories()
        self._reload_list()
        self.status.setText(f"{len(ids)} volume(s) ajouté(s) à « {cname} ».")

    def _remove_selected_from(self, cat_id) -> None:
        ids = self._selected_ids()
        if not ids or cat_id is None:
            return
        with get_session() as s:
            cat = s.get(Category, cat_id)
            for aid in ids:
                a = s.get(Asset, aid)
                if a and cat in a.categories:
                    a.categories.remove(cat)
        self._reload_categories()
        self._reload_list()

    def _category_menu(self, pos) -> None:
        it = self.cat_list.itemAt(pos)
        if it is None or it.data(Qt.UserRole) is None:
            return
        cid = it.data(Qt.UserRole)
        menu = QMenu(self)
        menu.addAction("Renommer…", lambda: self._rename_category(cid))
        menu.addAction("Supprimer la catégorie", lambda: self._delete_category(cid))
        menu.exec(self.cat_list.mapToGlobal(pos))

    def _rename_category(self, cid: int) -> None:
        with get_session() as s:
            cat = s.get(Category, cid)
            old = cat.name if cat else ""
        name, ok = QInputDialog.getText(self, "Renommer", "Nom :", text=old)
        if ok and name.strip():
            with get_session() as s:
                cat = s.get(Category, cid)
                if cat:
                    cat.name = name.strip()
            self._reload_categories()

    def _delete_category(self, cid: int) -> None:
        if QMessageBox.question(self, "Supprimer la catégorie",
                                "Supprimer la catégorie ? (les volumes ne sont pas touchés)") != QMessageBox.Yes:
            return
        with get_session() as s:
            cat = s.get(Category, cid)
            if cat:
                s.delete(cat)
        if self._filter_cat == cid:
            self._filter_cat = None
        self._reload_categories()
        self._reload_list()

    # ============================================================ VOLUMES LIST
    def _selected_ids(self) -> list[int]:
        return [it.data(Qt.UserRole)["id"] for it in self.vol_list.selectedItems()]

    def _reload_list(self) -> None:
        text = self.search.text().strip().lower()
        with get_session() as s:
            q = s.query(Asset)
            if self._filter_cat == _NEW:
                q = q.filter(Asset.reviewed.is_(False))
            elif self._filter_cat == _UNCAT:
                q = q.filter(~Asset.categories.any())
            elif self._filter_cat is not None:
                q = q.join(Asset.categories).filter(Category.id == self._filter_cat)
            assets = q.order_by(Asset.name).all()
            rows = []
            for a in assets:
                if text and text not in (a.name or "").lower() and text not in (a.project or "").lower():
                    continue
                thumb = str(config.PREVIEW_DIR / a.thumbnail_relpath) if a.thumbnail_relpath else None
                rows.append({
                    "id": a.id, "name": a.name,
                    "sub": f"{', '.join(a.formats()) or '—'}  ·  {a.capacity_label or '? ml'}",
                    "thumb_path": thumb, "status": _status_of(a), "new": not a.reviewed,
                })
            total = s.query(Asset).count()

        self.vol_list.blockSignals(True)
        self.vol_list.clear()
        keep = None
        for r in rows:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, r)
            self.vol_list.addItem(it)
            if r["id"] == self._current_id:
                keep = it
        self.vol_list.blockSignals(False)
        self.lbl_count.setText(f"Volumes  ({len(rows)}/{total})")
        if keep is not None:
            self.vol_list.setCurrentItem(keep)

    def _on_volume_changed(self, cur, _prev) -> None:
        if cur is None:
            self._current_id = None
            self._show_empty_edit()
            return
        self._select(cur.data(Qt.UserRole)["id"])

    def _volume_menu(self, pos) -> None:
        if not self.vol_list.selectedItems():
            return
        n = len(self.vol_list.selectedItems())
        menu = QMenu(self)
        add = menu.addMenu(f"Ajouter au dossier  ({n})")
        with get_session() as s:
            cats = [(c.id, c.name) for c in s.query(Category).order_by(Category.name).all()]
        for cid, name in cats:
            add.addAction(name, lambda c=cid: self._assign_selected_to(c))
        add.addSeparator()
        add.addAction("Nouvelle catégorie…", lambda: self._new_category(self._selected_ids()))
        if self._filter_cat is not None:
            menu.addAction("Retirer de cette catégorie", lambda: self._remove_selected_from(self._filter_cat))
        menu.addSeparator()
        menu.addAction(f"Supprimer ({n})", self._delete_selected)
        menu.exec(self.vol_list.mapToGlobal(pos))

    # ============================================================ SELECT / EDIT
    def _select(self, asset_id: int) -> None:
        self._current_id = asset_id
        self.empty_edit.hide()
        self.edit_scroll.show()
        self.action_bar.show()
        with get_session() as s:
            a = s.get(Asset, asset_id)
            if a is None:
                return
            self.f_name.setText(a.name or "")
            self.f_type.setCurrentText(a.volume_type or "")
            self.f_cap_label.setText(a.capacity_label or "")
            self.f_cap_ml.setValue(int(a.capacity_ml or 0))
            self.f_project.setText(a.project or "")
            self.f_client.setText(a.client or "")
            self.f_year.setValue(a.year or 0)
            self.f_author.setText(a.author or "")
            self.f_notes.setPlainText(a.notes or "")
            self.f_tags.set_tags([t.name for t in a.tags])
            st = _status_of(a)
            self.lbl_status.setText("● complet" if st == "complet" else "● incomplet")
            self.lbl_status.setStyleSheet(f"color: {_DOT_OK if st == 'complet' else _DOT_KO};")
            self._load_preview(a.gltf_relpath)

            # dimensions recalculées depuis la bbox (robuste, indépendant de l'axe up) :
            # hauteur = plus grande dimension, Ø = 2e plus grande.
            dims = [d for d in (a.bbox_x_mm, a.bbox_y_mm, a.bbox_z_mm) if d]
            if len(dims) == 3:
                h = round(max(dims)); dia = round(sorted(dims)[-2])
                hxo = f"{h} × {dia} mm"
            else:
                hxo = "—"
            self._rebuild_meta([
                ("Hauteur × Ø", hxo),
                ("Triangles", f"{a.poly_count:,}".replace(",", " ") if a.poly_count else "—"),
                ("Poids", f"{a.weight_bytes/1048576:.1f} Mo" if a.weight_bytes else "—"),
                ("Formats", ", ".join(f.upper() for f in a.formats()) or "—"),
            ])
            src = a.source_file()
            self.lbl_source.setText(f"Source : {src.relpath if src else '—'}")
        self._apply_editing()  # conserve le mode édition courant (persistant)

    def _set_editing(self, on: bool) -> None:
        """Mode édition PERSISTANT (reste actif quand on change de volume)."""
        self._editing = on
        self._apply_editing()

    def _apply_editing(self) -> None:
        on = self._editing
        for w in self._fields:
            w.setEnabled(on)
        self.btn_edit.setChecked(on)
        self.btn_edit.setText("Stop édition" if on else "Mode édition")
        self.btn_save.setEnabled(on)
        self.btn_cancel.setEnabled(on)

    def _cancel_edit(self) -> None:
        if self._current_id is not None:
            self._select(self._current_id)  # recharge = annule (reste en édition)

    def _rebuild_meta(self, tiles: list[tuple[str, str]]) -> None:
        old = self.meta_host.layout()
        if old is not None:
            while old.count():
                it = old.takeAt(0)
                if it.widget():
                    it.widget().deleteLater()
                elif it.layout():
                    self._kill_layout(it.layout())
            QWidget().setLayout(old)
        grid = QVBoxLayout(self.meta_host); grid.setContentsMargins(0, 0, 0, 0); grid.setSpacing(10)
        for i in range(0, len(tiles), 2):
            row = QHBoxLayout(); row.setSpacing(10)
            for label, value in tiles[i:i + 2]:
                row.addWidget(widgets.MetaTile(label, value))
            grid.addLayout(row)

    @staticmethod
    def _kill_layout(layout) -> None:
        while layout.count():
            it = layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _show_empty_edit(self) -> None:
        self.edit_scroll.hide()
        self.action_bar.hide()
        self.empty_edit.show()

    # ============================================================ SAVE / DELETE
    def _save(self) -> None:
        if self._current_id is None:
            return
        with get_session() as s:
            a = s.get(Asset, self._current_id)
            if a is None:
                return
            a.name = self.f_name.text().strip() or a.name
            a.volume_type = self.f_type.currentText().strip() or None
            a.capacity_label = self.f_cap_label.text().strip() or None
            a.capacity_ml = float(self.f_cap_ml.value()) or None
            a.project = self.f_project.text().strip() or None
            a.client = self.f_client.text().strip() or None
            a.year = self.f_year.value() or None
            a.author = self.f_author.text().strip() or None
            a.notes = self.f_notes.toPlainText().strip() or None
            a.tags = self._resolve_tags(s, self.f_tags.tags())
            a.reviewed = True  # édité par l'utilisateur -> retire la pastille NEW
        self.status.setText("Fiche enregistrée ✓ (mode édition conservé).")
        self._reload_categories()  # maj compteur « Nouveaux » (la fiche en sort)
        self._reload_list()        # met à jour la liste ; reste en mode édition

    @staticmethod
    def _resolve_tags(session, names: list[str]) -> list[Tag]:
        out: list[Tag] = []
        for name in names:
            tag = session.query(Tag).filter(Tag.name == name).first()
            if tag is None:
                tag = Tag(name=name); session.add(tag)
            out.append(tag)
        return out

    def _delete(self) -> None:
        if self._current_id is None:
            return
        if QMessageBox.question(self, "Supprimer",
                                "Supprimer cette fiche ? (le fichier source n'est pas touché)") != QMessageBox.Yes:
            return
        with get_session() as s:
            a = s.get(Asset, self._current_id)
            if a:
                s.delete(a)
        self._current_id = None
        self._reload_categories()
        self._reload_list()
        self._show_empty_edit()
        self.status.setText("Fiche supprimée.")

    def _delete_selected(self) -> None:
        ids = self._selected_ids()
        if not ids:
            return
        if QMessageBox.question(self, "Supprimer",
                                f"Supprimer {len(ids)} fiche(s) ? (fichiers sources non touchés)") != QMessageBox.Yes:
            return
        with get_session() as s:
            for aid in ids:
                a = s.get(Asset, aid)
                if a:
                    s.delete(a)
        self._current_id = None
        self._reload_categories()
        self._reload_list()
        self._show_empty_edit()
        self.status.setText(f"{len(ids)} fiche(s) supprimée(s).")

    # ============================================================ BIBLIOTHÈQUE / REFRESH
    def _choose_library(self) -> None:
        from aclib import library

        folder = QFileDialog.getExistingDirectory(
            self, "Dossier de la bibliothèque (base + aperçus)", str(library.current())
        )
        if not folder:
            return
        library.switch(folder)
        self.btn_library.setToolTip(folder)
        self._current_id = None
        self._filter_cat = None
        self._reload_categories()
        self._reload_list()
        self._show_empty_edit()
        self.status.setText(f"Bibliothèque : {folder}")

    def _force_regen(self) -> None:
        """DEV : force la régénération de TOUS les aperçus (glb + miniatures)."""
        from aclib import settings

        watch = [d for d in (settings.get("watch_dirs", []) or []) if Path(d).exists()]
        if not watch:
            QMessageBox.information(self, "Régénération",
                                    "Indexe d'abord un dossier (le chemin sera mémorisé).")
            return
        if QMessageBox.question(
            self, "Régénérer tout (dev)",
            "Re-convertir TOUS les glb (fix_normals) + re-rendre toutes les miniatures ?\n"
            "Peut prendre du temps selon le nombre de volumes.",
        ) != QMessageBox.Yes:
            return
        self.status.setText("Régénération forcée des aperçus…")
        self._run_index(watch, force=True)

    def _refresh(self) -> None:
        """Re-balaye les dossiers indexés (capte les NOUVEAUX fichiers ajoutés),
        puis recharge. Rapide : les aperçus déjà générés ne sont pas refaits.
        """
        from aclib import settings

        watch = [d for d in (settings.get("watch_dirs", []) or []) if Path(d).exists()]
        if watch:
            self.status.setText("Rafraîchissement (scan des nouveaux fichiers)…")
            self._run_index(watch)
        else:
            from aclib.db import reset, init_db
            reset(); init_db()
            self._reload_categories(); self._reload_list()
            self.status.setText(
                "Aucun dossier indexé mémorisé — utilise « Indexer un dossier… » une fois."
            )

    # ============================================================ INDEXING
    def _index_folder(self) -> None:
        start = self._nas_label() if self._nas_label() != "non configuré" else str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Dossier à indexer", start)
        if folder:
            self._run_index([folder])

    def _run_index(self, targets: list[str], force: bool = False,
                   materialize_c4d: bool = False) -> None:
        self._remember_dirs(targets)
        self.btn_folder.setEnabled(False); self.btn_refresh.setEnabled(False)
        self.btn_regen.setEnabled(False)
        self.progress.setVisible(True); self.progress.setValue(0)
        self._worker = IndexWorker(targets, make_previews=True, force=force,
                                   materialize_c4d=materialize_c4d)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_index_done)
        self._worker.failed.connect(self._on_index_failed)
        self._worker.start()

    @staticmethod
    def _remember_dirs(targets: list[str]) -> None:
        """Mémorise les DOSSIERS indexés pour que Refresh les re-balaye."""
        from aclib import settings
        from pathlib import Path as _P

        dirs = [str(_P(t)) for t in targets if _P(t).is_dir()]
        if not dirs:
            return
        known = settings.get("watch_dirs", []) or []
        merged = list(dict.fromkeys(known + dirs))
        settings.set("watch_dirs", merged)

    def _on_progress(self, msg: str, cur: int, total: int) -> None:
        self.progress.setMaximum(max(total, 1)); self.progress.setValue(cur)
        self.status.setText(f"Indexation : {msg} ({cur}/{total})")

    def _on_index_done(self, stats: dict) -> None:
        self.btn_folder.setEnabled(True); self.btn_refresh.setEnabled(True)
        self.btn_regen.setEnabled(True)
        self.progress.setVisible(False)
        self.status.setText(
            f"Indexé — {stats['new']} nouveaux · {stats['updated']} maj · "
            f"{stats['previews']} aperçus · {stats['errors']} conversions à faire"
        )
        self._reload_categories()
        self._reload_list()
        self._render_thumbnails()

    def _render_thumbnails(self) -> None:
        """Génère les vraies miniatures (rendu du volume) en tâche de fond."""
        from aclib.manager.thumb_renderer import ThumbRenderer, pending_jobs

        jobs = pending_jobs()
        if not jobs:
            return
        self.status.setText(f"Génération des miniatures… (0/{len(jobs)})")
        self._thumbs = ThumbRenderer(jobs, self)
        self._thumbs.progress.connect(
            lambda c, t: self.status.setText(f"Miniatures… ({c}/{t})")
        )
        self._thumbs.done.connect(self._on_thumbs_done)

    def _on_thumbs_done(self, n: int) -> None:
        self._delegate.clear_cache()   # vide le cache pixmap pour afficher les rendus
        self._reload_list()
        self.status.setText(f"{n} miniature(s) générée(s).")

    def _on_index_failed(self, msg: str) -> None:
        self.btn_folder.setEnabled(True); self.btn_refresh.setEnabled(True)
        self.btn_regen.setEnabled(True)
        self.progress.setVisible(False)
        QMessageBox.critical(self, "Indexation échouée", msg)
