"""Extraction de métadonnées depuis le NOM du fichier (nomenclature).

Beaucoup de fichiers suivent un schéma « TYPE CONTENANCE CLIENT », ex :
  « TUBE 50 GOUACHE »      -> type=Tube, contenance=50 ml, client=GOUACHE
  « TUBE 150 ml ELSEVE »   -> type=Tube, contenance=150 ml, client=ELSEVE
  « FLACON 250 LANCASTER » -> type=Flacon, contenance=250 ml, client=LANCASTER

On remplit AU MIEUX, sans jamais écraser une valeur déjà saisie (voir indexer).
Résultat partiel accepté : on ne renvoie que ce qu'on reconnaît.
"""
from __future__ import annotations

import re

# mot-clé (en MAJ) -> type normalisé
_TYPES = {
    "TUBE": "Tube",
    "FLACON": "Flacon", "FLAC": "Flacon",
    "POT": "Pot",
    "BOUTEILLE": "Bouteille", "BTL": "Bouteille", "BOTTLE": "Bouteille",
    "SPRAY": "Spray", "BRUME": "Spray",
    "COFFRET": "Coffret", "ETUI": "Coffret",
    "BOUCHON": "Bouchon", "CAPSULE": "Bouchon", "CAP": "Bouchon",
    "JAR": "Pot",
    "STICK": "Stick",
    "ROLLON": "Roll-on", "ROLL": "Roll-on",
    "POMPE": "Flacon",
}

# nombre (contenance) éventuellement suivi d'une unité ; pas collé à une lettre
_CAP_RE = re.compile(r"(?<![A-Za-z])(\d{1,5})(?:[.,](\d+))?\s*(ml|cl|l)?\b", re.IGNORECASE)

_UNIT_TO_ML = {"ml": 1.0, "cl": 10.0, "l": 1000.0, "": 1.0, None: 1.0}

# tokens ignorés pour deviner le client
_STOP = {"ML", "CL", "L", "V1", "V2", "V3", "DEF", "FINAL", "OK", "BAT"}


def _tokens(stem: str) -> list[str]:
    return [t for t in re.split(r"[\s_\-]+", stem.strip()) if t]


def parse(stem: str) -> dict:
    """Renvoie {volume_type?, capacity_ml?, capacity_label?, client?} (clés
    présentes seulement si reconnues)."""
    out: dict = {}
    toks = _tokens(stem)
    if not toks:
        return out

    used = set()  # indices consommés (type / contenance / unité)

    # --- type : 1er token reconnu ---
    for i, t in enumerate(toks):
        key = re.sub(r"[^A-Za-z]", "", t).upper()
        if key in _TYPES:
            out["volume_type"] = _TYPES[key]
            used.add(i)
            break

    # --- contenance : 1er nombre plausible (1..10000 ml) ---
    m = _CAP_RE.search(stem)
    if m:
        whole, frac, unit = m.group(1), m.group(2), (m.group(3) or "").lower()
        val = float(f"{whole}.{frac}") if frac else float(whole)
        ml = val * _UNIT_TO_ML.get(unit, 1.0)
        if 1 <= ml <= 100000:
            out["capacity_ml"] = ml
            label_val = int(ml) if ml.is_integer() else ml
            out["capacity_label"] = f"{label_val} ml"
            # marque les tokens correspondant au nombre + unité comme consommés
            for i, t in enumerate(toks):
                tl = t.lower().rstrip("mlcl.")
                if t == whole or t.startswith(whole):
                    used.add(i)
                if t.lower() in ("ml", "cl", "l"):
                    used.add(i)

    # --- client : tokens restants significatifs ---
    rest = []
    for i, t in enumerate(toks):
        if i in used:
            continue
        if t.upper() in _STOP:
            continue
        if re.fullmatch(r"[\d.,]+", t):  # nombre résiduel
            continue
        rest.append(t)
    if rest:
        out["client"] = " ".join(rest)

    return out
