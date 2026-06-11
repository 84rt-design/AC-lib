"""Modèles SQLAlchemy — schéma de la base de fiches.

Calqué sur §4 du cadrage (caractéristiques suivies par volume).
Marqueurs « auto » = extraits du fichier à l'indexation ; « saisi » = entrés
une fois à l'import via le Manager.

Tous les chemins (`*_relpath`) sont RELATIFS à la racine NAS (voir config.py).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# Association volume <-> tags (saisi) ----------------------------------------
asset_tags = Table(
    "asset_tags",
    Base.metadata,
    Column("asset_id", ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

# Association volume <-> catégories (dossiers/collections de la sidebar) ------
asset_categories = Table(
    "asset_categories",
    Base.metadata,
    Column("asset_id", ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)


class Asset(Base):
    """Une fiche = un volume."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)

    # --- Identité (saisi) ---
    name: Mapped[str] = mapped_column(String(255), index=True)
    volume_type: Mapped[str | None] = mapped_column(String(80), index=True)  # Flacon, Pot, Tube...
    project: Mapped[str | None] = mapped_column(String(160), index=True)
    client: Mapped[str | None] = mapped_column(String(160), index=True)

    # --- Contenance ---
    # Valeur numérique en ml pour filtrer par plage ; label pour l'affichage.
    capacity_ml: Mapped[float | None] = mapped_column(Float, index=True)
    capacity_label: Mapped[str | None] = mapped_column(String(40))  # "250 ml"

    # --- Dimensions (auto, bounding box) en mm ---
    height_mm: Mapped[float | None] = mapped_column(Float, index=True)   # H
    diameter_mm: Mapped[float | None] = mapped_column(Float, index=True)  # Ø
    bbox_x_mm: Mapped[float | None] = mapped_column(Float)
    bbox_y_mm: Mapped[float | None] = mapped_column(Float)
    bbox_z_mm: Mapped[float | None] = mapped_column(Float)

    # --- Provenance (auto / saisi) ---
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    author: Mapped[str | None] = mapped_column(String(120))

    # --- Géométrie (auto) ---
    poly_count: Mapped[int | None] = mapped_column(Integer)   # tris
    weight_bytes: Mapped[int | None] = mapped_column(Integer)  # poids fichier source

    # --- Aperçus générés (relpath dans PREVIEW_DIR) ---
    thumbnail_relpath: Mapped[str | None] = mapped_column(String(512))
    gltf_relpath: Mapped[str | None] = mapped_column(String(512))

    # --- Divers ---
    notes: Mapped[str | None] = mapped_column(Text)
    # reviewed = False tant que l'utilisateur n'a pas édité/validé la fiche
    # (sert à afficher la pastille « NEW » sur les volumes fraîchement indexés).
    reviewed: Mapped[bool] = mapped_column(default=False)
    # thumb_rendered = True quand la vraie miniature 3D (capture du modèle) a été
    # générée (sinon vignette placeholder). Évite de re-rendre à chaque refresh.
    thumb_rendered: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    # --- Relations ---
    files: Mapped[list["AssetFile"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", lazy="selectin"
    )
    tags: Mapped[list["Tag"]] = relationship(
        secondary=asset_tags, back_populates="assets", lazy="selectin"
    )
    categories: Mapped[list["Category"]] = relationship(
        secondary=asset_categories, back_populates="assets", lazy="selectin"
    )

    def source_file(self) -> "AssetFile | None":
        """Fichier marqué source (sinon le premier)."""
        for f in self.files:
            if f.is_source:
                return f
        return self.files[0] if self.files else None

    def formats(self) -> list[str]:
        """Liste des formats disponibles, ex. ['c4d', 'fbx']."""
        return sorted({f.fmt for f in self.files})

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Asset {self.id} {self.name!r} {self.capacity_label}>"


class AssetFile(Base):
    """Un fichier concret d'un volume. Un volume peut exister en plusieurs
    formats (C4D + FBX + OBJ + STEP) — une ligne par format.
    """

    __tablename__ = "asset_files"
    __table_args__ = (UniqueConstraint("asset_id", "fmt", name="uq_asset_fmt"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)

    fmt: Mapped[str] = mapped_column(String(12), index=True)   # c4d, fbx, obj, step
    relpath: Mapped[str] = mapped_column(String(1024))         # RELATIF racine NAS
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    is_source: Mapped[bool] = mapped_column(default=False)     # fichier d'origine

    asset: Mapped["Asset"] = relationship(back_populates="files")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AssetFile {self.fmt} {self.relpath!r}>"


class Tag(Base):
    """Tag libre (saisi). Ex : cosmétique, verre, premium."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)

    assets: Mapped[list["Asset"]] = relationship(
        secondary=asset_tags, back_populates="tags"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Tag {self.name!r}>"


class Category(Base):
    """Catégorie / dossier de la sidebar (ex : « Campagne PV », « Flacons verre »).

    Many-to-many : un volume peut appartenir à plusieurs catégories.
    """

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)

    assets: Mapped[list["Asset"]] = relationship(
        secondary=asset_categories, back_populates="categories"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Category {self.name!r}>"
