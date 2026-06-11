# A.C.Lib — guide Claude Code

Bibliothèque 3D interne (packaging : flacons, pots, tubes, bouteilles, coffrets).
**Little Agency** — outil de recherche et réutilisation de volumes 3D.

## Deux applications, une base

| App | Rôle | Lancement |
|-----|------|-----------|
| **Manager** | Indexe, convertit, édite fiches, catégories, vignettes 3D | `python -m aclib.manager` |
| **Viewer** | Consultation : grille, filtres, viewer 3D, panier, export | `python -m aclib.viewer` |

Les fichiers 3D sources **restent sur le NAS** — jamais déplacés par l'app.
La base (`library.db`) + aperçus (`previews/`) vivent dans le **dossier bibliothèque** choisi.

## Règles d'architecture (ne pas violer)

1. **Chemins relatifs en base** — `AssetFile.relpath` est relatif à la racine NAS (`config.nas_root()`). Jamais de chemin absolu stocké en DB.
2. **Ne pas indexer `.glb` / `.gltf`** — ce sont des aperçus générés, pas des sources (`config.MODEL_EXTENSIONS`).
3. **Bibliothèque partagée** — Manager et Viewer pointent le même `data_dir` via `~/.aclib/settings.json` (bouton « Bibliothèque » → `aclib.library.switch()`).
4. **Regroupement** — fichiers de même nom dans un dossier (`flacon_250.c4d` + `.fbx` + `.obj`) = **un** volume, plusieurs formats.
5. **Champs auto vs saisi** — l'indexeur remplit bbox, formats, nomenclature ; l'utilisateur complète type, contenance, tags via le Manager. Ne pas écraser un champ saisi (`indexer._autofill_nomenclature`).
6. **Pastille NEW** — `Asset.reviewed == False` tant que la fiche n'est pas validée.
7. **Schéma DB** — migration légère via `db/session.py::_migrate` (ADD COLUMN). Ne pas supprimer de colonnes sans script de migration.

## Stack

- Python **3.12+**, **PySide6** (QtWebEngine pour le viewer three.js)
- **SQLAlchemy 2** + SQLite (Postgres possible via `ACLIB_DB_URL`)
- Conversion mesh : **trimesh**, **pygltflib**, **Pillow**
- Viewer 3D : `aclib/viewer/web/viewer3d.html` (three.js vendorisé, offline)

## Structure du code

```
aclib/
  config.py           NAS par OS, data_dir, extensions, set_data_dir()
  settings.py         ~/.aclib/settings.json (data_dir partagé)
  library.py          switch() — bascule bibliothèque à chaud
  db/models.py        Asset, AssetFile, Tag, Category
  db/session.py       engine, init_db(), reset(), migration auto
  core/
    paths.py          relpath <-> absolu
    indexer.py        scan, regroupement, previews
    nomenclature.py   parse nom fichier → type/contenance/client
    conversion/       c4d, step, fbx, mesh, thumbnail
  manager/            IndexWorker (QThread), ThumbRenderer, main_window
  viewer/             grille, panier (cart.py), export, export_dialog
  ui/                 theme.py (charte DA), anim, widgets, AssetCard…
scripts/
  build_portable.py   PyInstaller → dist/AClibViewer, dist/AClibManager
  smoke_test.py       test index + UI offscreen
  test_c4d_pipeline.py validation C4D (lancer avec c4dpy)
```

## État actuel (juin 2026)

**Fait :**
- UI conforme charte DA (fond sombre, Inter, animations `ui/anim.py`)
- Manager : import drag-drop, index dossier, édition fiche, catégories, multi-sélection, mode édition persistant
- Viewer : bibliothèque + fiche détail, filtres (type, format, contenance, dimensions), panier, export multi-format
- Nomenclature auto depuis noms de fichiers
- Vignettes 3D (`ThumbRenderer`) + flag `thumb_rendered`
- Versions portables (`scripts/build_portable.py`, `dist/AClibManager/`, `dist/AClibViewer/`)
- Choix dossier bibliothèque partagé Manager ↔ Viewer

**Partiel / dépendances externes :**
- Conversion **C4D** → nécessite `c4dpy` (Cinema 4D installé)
- Conversion **STEP** → `pythonocc-core` (conda)
- Conversion **FBX** → FBX2glTF ou assimp sur le PATH
- FBX/OBJ/Ply/Stl s'indexent sans C4D ; C4D/STEP sans convertisseur = fiche sans glTF

## Config & variables d'env

Préfixe `ACLIB_` (voir `config.py`) :

| Variable | Usage |
|----------|-------|
| `ACLIB_DATA_DIR` | Force le dossier bibliothèque (base + previews) |
| `ACLIB_NAS_ROOT_WIN` / `_MAC` / `_LINUX` | Racine NAS par OS |
| `ACLIB_DB_URL` | Postgres si besoin multi-utilisateurs |

Dev : venv `.venv`, `pip install -r requirements.txt`.

## Commandes utiles

```bash
.venv\Scripts\activate
python -m aclib.manager
python -m aclib.viewer
python scripts/smoke_test.py
python scripts/build_portable.py          # Viewer
python scripts/build_portable.py --manager # + Manager
```

## Build portable

- PyInstaller **onedir** (QtWebEngine)
- Exe figé : `data/` à côté de l'exe (bibliothèque portable)
- Manager et Viewer doivent pointer le **même** dossier bibliothèque

## Instructions pour Claude (sessions)

1. **Ne pas rescanner tout le repo** — lire `CLAUDE.md` + les fichiers concernés par la tâche.
2. **Reprise de session** — demander à l'utilisateur le sujet précis ; lire 2–5 fichiers max avant d'agir.
3. **UI** — respecter `aclib/ui/theme.py` (palette charte). Pas de styles ad hoc hors thème.
4. **Tests** — `scripts/smoke_test.py` pour valider index + UI ; `compileall` pour syntaxe.
5. **Modifs DB** — ajouter colonne dans `models.py` + s'appuyer sur `_migrate` ; ne pas recréer la base.
6. **Réponses** — français, concis, code aligné sur les conventions existantes (type hints, docstrings module).

## Fichiers à lire selon la tâche

| Sujet | Fichiers |
|-------|----------|
| Indexation / import | `core/indexer.py`, `core/nomenclature.py`, `manager/index_worker.py` |
| Conversion 3D | `core/conversion/*.py` |
| Manager UI | `manager/main_window.py`, `manager/thumb_renderer.py` |
| Viewer UI / 3D | `viewer/main_window.py`, `viewer/web/viewer3d.html` |
| Panier / export | `viewer/cart.py`, `viewer/export.py`, `viewer/export_dialog.py` |
| Bibliothèque partagée | `library.py`, `settings.py`, `config.py` |
| Thème / composants | `ui/theme.py`, `ui/widgets.py`, `ui/anim.py` |
| Portable | `scripts/build_portable.py` |

## Contexte métier (cadrage)

- Cible : équipe 3D packaging, réutilisation de volumes existants
- Workflow : browse → sélection panier → export vers nouveau projet
- Formats sources : C4D, FBX, OBJ, STEP (+ ply/stl/off)
- Aperçus : vignette PNG + glTF allégé dans `previews/`
