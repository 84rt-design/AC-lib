"""Moteur + session SQLAlchemy.

SQLite par défaut (config.DB_URL). Pour passer en Postgres (multi-utilisateurs
NAS), surcharger ACLIB_DB_URL — aucun autre changement de code requis.
"""
from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from aclib import config
from aclib.db.models import Base

_engine: Engine | None = None
_Session: sessionmaker[Session] | None = None


def _make_engine() -> Engine:
    is_sqlite = config.DB_URL.startswith("sqlite")
    kwargs: dict = {"future": True}
    if is_sqlite:
        # check_same_thread=False : l'UI Qt lit depuis plusieurs threads (export).
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(config.DB_URL, **kwargs)
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _pragma(dbapi_conn, _rec):  # pragma: no cover
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            # WAL est INCOMPATIBLE avec un partage réseau (SMB/NAS) : il exige
            # mémoire partagée + verrous POSIX absents du réseau -> "database is
            # locked" / base vue vide depuis un autre poste (Mac lisant la base
            # serveur ecrite par le Manager PC). La base A.C.Lib vit sur le NAS
            # et est partagée Manager(PC) <-> Viewer(Mac) : on force donc le
            # journal DELETE (rollback classique, compatible reseau).
            cur.execute("PRAGMA journal_mode=DELETE")
            cur.execute("PRAGMA busy_timeout=5000")  # tolère un lock transitoire SMB
            cur.close()

    return engine


def _migrate(engine: Engine) -> None:
    """Migration légère : ajoute les colonnes manquantes aux tables existantes
    (SQLAlchemy create_all ne le fait pas). Gère l'évolution du schéma sans
    perdre les données déjà saisies. SQLite : ADD COLUMN simple suffit.
    """
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all s'en charge
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                coltype = col.type.compile(engine.dialect)
                ddl = f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'
                default = getattr(col.default, "arg", None)
                if default is not None and not callable(default):
                    if isinstance(default, bool):
                        ddl += f" DEFAULT {1 if default else 0}"
                    elif isinstance(default, (int, float)):
                        ddl += f" DEFAULT {default}"
                    elif isinstance(default, str):
                        ddl += f" DEFAULT '{default}'"
                try:
                    conn.execute(text(ddl))
                except Exception:  # noqa: BLE001 — colonne déjà là / non supportée
                    pass


def init_db() -> Engine:
    """Crée le moteur, les dossiers et les tables. Idempotent."""
    global _engine, _Session
    if _engine is None:
        config.ensure_dirs()
        _engine = _make_engine()
        _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
        Base.metadata.create_all(_engine)
        _migrate(_engine)
    return _engine


def reset() -> None:
    """Ferme le moteur courant pour rebrancher une autre base (après
    config.set_data_dir). Le prochain get_session()/init_db() repart à neuf.
    """
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _Session = None


@contextmanager
def get_session() -> Iterator[Session]:
    """Session transactionnelle : commit si OK, rollback si exception."""
    if _Session is None:
        init_db()
    assert _Session is not None
    session = _Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
