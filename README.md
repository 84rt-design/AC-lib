# A.C.Lib — Bibliothèque 3D centralisée

Outil interne de recherche et réutilisation des modèles 3D packaging
(flacons, pots, tubes, bouteilles, coffrets).

Deux applications, une base commune.

```
[A.C.Lib Manager]  création/MAJ assets : indexe les dossiers projets,
                   convertit C4D/STEP -> glTF, génère vignettes,
                   édite fiches + tags.  Besoin : C4D installé, OpenCASCADE.

[A.C.Lib Viewer]   consultation : recherche, filtres, viewer 3D interactif,
                   panier, export multi-format dans un dossier choisi.
                   Léger, cross-platform pur (aucune dépendance lourde).
```

## Principe

Les fichiers 3D lourds **ne sont jamais déplacés** (restent sur le NAS).
L'app gère une **base de fiches** qui pointe vers ces fichiers, plus des
**aperçus légers** (vignette PNG + glTF allégé) générés à l'indexation.

```
[Manager/Indexeur]  ─écrit─►  [Base fiches + aperçus sur NAS]  ◄─lit─  [Viewer]
   (où C4D installé)
```

## Structure

```
aclib/
  config.py              racines NAS par OS, chemins base/aperçus
  db/                    modèles SQLAlchemy + session
  core/
    paths.py             chemin relatif <-> absolu selon l'OS
    indexer.py           parcourt dossiers, détecte 3D, pré-remplit fiches
    conversion/          C4D / STEP / mesh -> glTF, vignettes (stubs)
  manager/               app Manager (PySide6)
  viewer/                app Viewer (PySide6) — grille, panier, export
    web/viewer3d.html    viewer glTF three.js embarqué
scripts/
  test_c4d_pipeline.py   validation critique C4D->glTF (à lancer avec c4dpy)
```

## Installation

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### Dépendances Manager (conversion lourde)

- **STEP** : `pythonocc-core` s'installe via conda, pas pip :
  `conda install -c conda-forge pythonocc-core`
- **C4D** : `c4dpy` est fourni par l'installation Cinema 4D (Maxon).
  Le script `scripts/test_c4d_pipeline.py` se lance avec `c4dpy`, pas `python`.

Le **Viewer** n'a besoin d'aucune de ces deux : il lit les glTF déjà générés.

## Lancement

```bash
python -m aclib.manager      # app de création/MAJ
python -m aclib.viewer       # app de consultation
```

## Config

Éditer `aclib/config.py` (ou variables d'env, voir le fichier) :

- `NAS_ROOTS` — racine du NAS par OS (`\\serveur\projets` sur Windows,
  `/Volumes/projets` sur macOS). Les fiches stockent des chemins **relatifs**
  à cette racine — jamais d'absolu en dur.
- `DB_PATH` — emplacement de la base SQLite (sur le NAS pour le partage).
- `PREVIEW_DIR` — dossier des aperçus (vignettes + glTF).

## État

Squelette. La conversion C4D/STEP est **stubée** (voir `core/conversion/`).
Étape critique suivante : valider `scripts/test_c4d_pipeline.py` sur un
fichier réel avant d'investir plus.
