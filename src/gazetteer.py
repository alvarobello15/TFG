"""
TFG: Gazetteer Historic HGIS de las Indias
=============================================
Carrega 15.847 llocs colonials d'Hispanoamerica (1701-1808)
i ofereix funcions de lookup per millorar la geocodificacio.

Dataset: HGIS de las Indias — https://www.hgis-indias.net/
"""

import math
import unicodedata
import re
from pathlib import Path

import pandas as pd

CSV_PATH = Path(__file__).parent.parent / "data" / "hgis" / "gz_info_1.csv"

# Bounding box amazonic
AMAZON_BBOX = {"lat_min": -20, "lat_max": 5, "lon_min": -80, "lon_max": -45}

# Paisos prioritaris (zona amazonica / sudamericana)
PRIORITY_COUNTRIES = {"BOL", "PER", "ECU", "COL", "BRA"}

# Equivalencies de noms historics
EQUIVALENCES = {
    "mojos": "moxos", "moxos": "moxos",
    "charcas": "chuquisaca", "chuquisaca": "chuquisaca", "sucre": "chuquisaca",
    "piru": "peru", "peru": "peru", "pirú": "peru",
    "ygnacio": "ignacio", "ignacio": "ignacio",
}

# Prefixos a eliminar per matching parcial
PREFIXES = re.compile(
    r"^(mision\s+de|pueblo\s+de|villa\s+de|ciudad\s+de|reduccion\s+de|"
    r"san\s+|santa\s+|santo\s+|rio\s+|arroyo\s+|laguna\s+de)\s*",
    re.IGNORECASE,
)

# Articles a eliminar
ARTICLES = re.compile(r"\b(los|las|de|del|la|el)\b", re.IGNORECASE)


def _normalize(text):
    """Normalitza un nom: lowercase, strip, elimina accents."""
    if not text or not isinstance(text, str):
        return ""
    # Remove accents
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_text.lower().strip()


def _normalize_deep(text):
    """Normalitzacio profunda: elimina articles i aplica equivalencies."""
    n = _normalize(text)
    # Apply equivalences
    for old, new in EQUIVALENCES.items():
        n = re.sub(r"\b" + re.escape(old) + r"\b", new, n)
    # Remove articles
    n = ARTICLES.sub(" ", n)
    # Collapse whitespace
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _strip_prefix(text):
    """Elimina prefixos com 'mision de', 'pueblo de', etc."""
    return PREFIXES.sub("", _normalize(text)).strip()


def _inside_bbox(lat, lon):
    return (AMAZON_BBOX["lat_min"] <= lat <= AMAZON_BBOX["lat_max"]
            and AMAZON_BBOX["lon_min"] <= lon <= AMAZON_BBOX["lon_max"])


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = rlat2 - rlat1, rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


# Certesa ordering (higher = better)
CERT_ORDER = {
    "Exacta": 5,
    "Geoservice/Satelite": 4,
    "Buena": 3,
    "Suficiente": 2,
    "Interpolada": 1,
    "Identificacion incierta": 0,
    "No localizado": -1,
}


class HistoricalGazetteer:
    """Gazetteer historic HGIS de las Indias amb index de cerca."""

    def __init__(self, csv_path=None):
        path = Path(csv_path) if csv_path else CSV_PATH
        if not path.exists():
            print(f"   Gazetteer no trobat: {path}")
            self.df = pd.DataFrame()
            self._index = {}
            return

        self.df = pd.read_csv(str(path))
        # Drop rows with invalid coords
        self.df = self.df[
            (self.df["lat"].notna()) & (self.df["lon"].notna())
            & (self.df["lat"].abs() <= 90) & (self.df["lon"].abs() <= 180)
        ].copy()
        # Deduplicate by gz_id (keep first)
        self.df = self.df.drop_duplicates(subset="gz_id", keep="first")

        self._build_index()
        print(f"   Gazetteer HGIS carregat: {len(self.df)} llocs")

    def _build_index(self):
        """Construeix un index de cerca: normalized_name -> list of row indices."""
        self._index = {}

        for idx, row in self.df.iterrows():
            names = set()

            # label
            if pd.notna(row.get("label")):
                names.add(_normalize(row["label"]))
            # nombre
            if pd.notna(row.get("nombre")):
                names.add(_normalize(row["nombre"]))
                # Also add nombre without prefix
                names.add(_strip_prefix(row["nombre"]))
            # variantes (pipe-separated)
            if pd.notna(row.get("variantes")):
                for v in str(row["variantes"]).split("|"):
                    v = v.strip()
                    if v and v != "[-]":
                        names.add(_normalize(v))
            # nombrehoy
            if pd.notna(row.get("nombrehoy")):
                names.add(_normalize(row["nombrehoy"]))

            # Also index individual significant words from nombre (>= 5 chars)
            if pd.notna(row.get("nombre")):
                for word in _normalize(row["nombre"]).split():
                    if len(word) >= 5 and word not in {"santo", "santa", "mision", "pueblo",
                        "villa", "ciudad", "reduccion", "fuerte"}:
                        names.add(word)

            for n in names:
                if n:
                    self._index.setdefault(n, []).append(idx)

    def _rank_candidates(self, indices):
        """Ordena candidats per prioritat: BOL/PER > bbox amazonic > pais prioritari > certesa."""
        rows = [self.df.loc[i] for i in indices]

        def sort_key(r):
            pais = r.get("pais", "")
            in_bbox = _inside_bbox(r["lat"], r["lon"])
            # BOL and PER get top priority (core study area)
            core_country = pais in {"BOL", "PER"}
            priority_country = pais in PRIORITY_COUNTRIES
            cert_score = CERT_ORDER.get(r.get("cert", ""), 0)
            return (-int(core_country), -int(in_bbox), -int(priority_country), -cert_score)

        rows.sort(key=sort_key)
        return rows

    def lookup(self, name):
        """
        Busca un nom al gazetteer.

        Ordre de matching:
          1. Exact match contra index normalitzat
          2. Match sense prefix (elimina 'pueblo de', 'mision de', etc.)
          3. Match amb equivalencies ('Mojos' -> 'Moxos')
          4. Match parcial (substring) — nomes si el nom te >= 5 chars

        Retorna dict amb {name, lat, lon, categoria, pais, source} o None.
        """
        if not name or self.df.empty:
            return None

        # 1. Exact match
        norm = _normalize(name)
        if norm in self._index:
            candidates = self._rank_candidates(self._index[norm])
            if candidates:
                return self._format_result(candidates[0])

        # 2. Match without prefix
        stripped = _strip_prefix(name)
        if stripped and stripped != norm and stripped in self._index:
            candidates = self._rank_candidates(self._index[stripped])
            if candidates:
                return self._format_result(candidates[0])

        # 3. Match with equivalences
        deep = _normalize_deep(name)
        if deep != norm and deep in self._index:
            candidates = self._rank_candidates(self._index[deep])
            if candidates:
                return self._format_result(candidates[0])

        # Also try equivalences on the index side
        for idx_name, indices in self._index.items():
            if _normalize_deep(idx_name) == deep and deep:
                candidates = self._rank_candidates(indices)
                if candidates:
                    return self._format_result(candidates[0])

        # 3b. Try with/without trailing 's' (Omagua ↔ Omaguas)
        for variant in [norm + "s", norm.rstrip("s")] if len(norm) >= 4 else []:
            if variant and variant != norm and variant in self._index:
                candidates = self._rank_candidates(self._index[variant])
                if candidates:
                    return self._format_result(candidates[0])

        # 4. Partial match — only if query is a full word inside a longer name
        #    e.g. "San Ignacio" matches "San Ignacio de Moxos"
        #    but "Chiquitos" does NOT match "Quito"
        if len(norm) >= 6:
            partial_matches = []
            for idx_name, indices in self._index.items():
                # Query must be a full word boundary match inside the index name
                if len(idx_name) > len(norm) and re.search(r"\b" + re.escape(norm) + r"\b", idx_name):
                    partial_matches.extend(indices)
            if partial_matches:
                partial_matches = list(set(partial_matches))
                candidates = self._rank_candidates(partial_matches)
                if candidates:
                    return self._format_result(candidates[0])

        return None

    def _format_result(self, row):
        return {
            "name": row.get("nombre") or row.get("label", ""),
            "lat": float(row["lat"]),
            "lon": float(row["lon"]),
            "categoria": row.get("categoria", ""),
            "pais": row.get("pais", ""),
            "cert": row.get("cert", ""),
            "source": "hgis_gazetteer",
        }

    def lookup_batch(self, names):
        """Fa lookup de multiples noms. Retorna dict {name: result_or_None}."""
        return {name: self.lookup(name) for name in names}


# ── CLI per testejar ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    gz = HistoricalGazetteer()
    test_names = [
        "Omagua", "San Ignacio", "Chiquitos", "Moxos", "Mojos",
        "Trinidad", "Santa Cruz", "Cochabamba", "Machiparo",
        "Carmen de Moxos", "San Javier", "Loreto", "Cobija",
        "ciudad de Baeza", "pueblo de Aparia",
    ]
    print(f"\n{'Nom':<30} {'Resultat':<40} {'Coords':<25} {'Pais'}")
    print("-" * 120)
    for name in test_names:
        r = gz.lookup(name)
        if r:
            print(f"{name:<30} {r['name'][:40]:<40} ({r['lat']:.4f}, {r['lon']:.4f})  {r['pais']}")
        else:
            print(f"{name:<30} {'— no trobat':<40}")
