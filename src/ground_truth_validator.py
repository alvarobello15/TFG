"""
TFG: Validacio contra Ground Truth (Walker et al. 2023)
=========================================================
Compara les hipotesis generades pel pipeline amb sitis
arqueologics reals del dataset de Walker et al. 2023
(earthworks, geoglyphs, Amazonian Dark Earth).

Dataset: https://doi.org/10.5281/zenodo.7651334
"""

import csv
import math
from pathlib import Path

WALKER_CSV = Path(__file__).parent / "data" / "walker_2023" / "submit.csv"
COOMES_CSV = Path(__file__).parent / "data" / "coomes_2021" / "coomes_sites.csv"

# Llindar de proximitat per considerar un "match" (km)
DEFAULT_THRESHOLD_KM = 50


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def load_walker_sites(csv_path=None):
    """
    Carrega els sitis arqueologics del dataset Walker et al. 2023.
    Retorna una llista de dicts amb keys: type, lat, lon.
    Exclou els punts 'other' (pseudo-absencies).
    """
    path = Path(csv_path) if csv_path else WALKER_CSV
    if not path.exists():
        print(f"   Dataset Walker no trobat: {path}")
        print("   Descarrega'l de: https://github.com/RobertSWalker/ancient_amazonia_archaeology")
        return []

    sites = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            site_type = row.get("type", "").strip()
            if site_type == "other":
                continue
            try:
                lat = float(row["y"])
                lon = float(row["x"])
                sites.append({"type": site_type, "lat": lat, "lon": lon})
            except (ValueError, KeyError):
                continue

    return sites


def load_coomes_sites(csv_path=None):
    """
    Carrega els 415 sitis arqueologics de Coomes et al. 2021
    (Departamento de Loreto, Amazònia peruana).

    Dataset: https://springernature.figshare.com/collections/5262530
    Retorna una llista de dicts amb keys: name, lat, lon, province, district.
    """
    path = Path(csv_path) if csv_path else COOMES_CSV
    if not path.exists():
        print(f"   Dataset Coomes no trobat: {path}")
        return []

    sites = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                lat = float(row["lat"])
                lon = float(row["lon"])
                name = row.get("name", "").strip()
                province = row.get("province", "").strip()
                district = row.get("district", "").strip()
                sites.append({
                    "name": name,
                    "lat": lat,
                    "lon": lon,
                    "province": province,
                    "district": district,
                })
            except (ValueError, KeyError):
                continue

    return sites


def validate_hypotheses(db, threshold_km=DEFAULT_THRESHOLD_KM, csv_path=None):
    """
    Valida les hipotesis del pipeline contra els sitis coneguts de Walker et al. 2023.

    Per a cada hipotesi, calcula la distancia al siti conegut mes proper.
    Una hipotesi es considera un 'hit' si esta a menys de threshold_km d'un siti real.

    Retorna un dict amb metriques de validacio.
    """
    known_sites = load_walker_sites(csv_path)
    if not known_sites:
        return None

    hypotheses = db.conn.execute(
        """SELECT h.id, h.lat, h.lon, h.score, h.status, e.name, e.entity_type
           FROM hypotheses h
           JOIN entities e ON h.entity_id = e.id
           ORDER BY h.score DESC"""
    ).fetchall()

    if not hypotheses:
        print("   No hi ha hipotesis per validar.")
        return None

    n_earthworks = sum(1 for s in known_sites if s["type"] == "earthwork")
    n_ade = sum(1 for s in known_sites if s["type"] == "ADE")

    print(f"\n{'='*70}")
    print(f"  VALIDACIO CONTRA GROUND TRUTH (Walker et al. 2023)")
    print(f"{'='*70}")
    print(f"  Sitis coneguts: {len(known_sites)} ({n_earthworks} earthworks, {n_ade} ADE)")
    print(f"  Hipotesis a validar: {len(hypotheses)}")
    print(f"  Llindar de proximitat: {threshold_km} km")
    print(f"{'='*70}")

    # Per a cada hipotesi, trobar el siti conegut mes proper
    hits = []
    misses = []
    for hyp in hypotheses:
        best_dist = float("inf")
        best_site = None
        for site in known_sites:
            dist = haversine_km(hyp["lat"], hyp["lon"], site["lat"], site["lon"])
            if dist < best_dist:
                best_dist = dist
                best_site = site

        record = {
            "hyp_id": hyp["id"],
            "name": hyp["name"],
            "entity_type": hyp["entity_type"],
            "lat": hyp["lat"],
            "lon": hyp["lon"],
            "score": hyp["score"],
            "status": hyp["status"],
            "nearest_dist_km": round(best_dist, 2),
            "nearest_type": best_site["type"] if best_site else None,
        }

        if best_dist <= threshold_km:
            hits.append(record)
        else:
            misses.append(record)

    # Metriques
    n_total = len(hypotheses)
    n_hits = len(hits)
    hit_rate = n_hits / n_total if n_total else 0

    # Candidates (score >= 0.5) vs low_priority
    candidates = [h for h in hypotheses]
    candidate_hits = [h for h in hits if h["status"] == "candidate"]
    candidate_total = sum(1 for h in hypotheses if h["status"] == "candidate")
    candidate_hit_rate = len(candidate_hits) / candidate_total if candidate_total else 0

    # Distancia mitjana dels hits
    avg_dist_hits = sum(h["nearest_dist_km"] for h in hits) / n_hits if n_hits else 0
    median_dist_hits = sorted(h["nearest_dist_km"] for h in hits)[n_hits // 2] if n_hits else 0

    # Cobertura: quants sitis coneguts tenen almenys una hipotesi a prop?
    matched_sites = set()
    for site in known_sites:
        for hyp in hypotheses:
            dist = haversine_km(hyp["lat"], hyp["lon"], site["lat"], site["lon"])
            if dist <= threshold_km:
                matched_sites.add((site["lat"], site["lon"]))
                break
    coverage = len(matched_sites) / len(known_sites) if known_sites else 0

    # Resultats
    print(f"\n  RESULTATS:")
    print(f"  {'-'*50}")
    print(f"  Hit rate global:       {n_hits}/{n_total} ({hit_rate:.1%})")
    print(f"  Hit rate candidates:   {len(candidate_hits)}/{candidate_total} ({candidate_hit_rate:.1%})")
    print(f"  Cobertura sitis reals: {len(matched_sites)}/{len(known_sites)} ({coverage:.1%})")
    print(f"  Distancia mitjana (hits): {avg_dist_hits:.1f} km")
    print(f"  Distancia mediana (hits): {median_dist_hits:.1f} km")

    # Top hits
    if hits:
        top_hits = sorted(hits, key=lambda h: h["nearest_dist_km"])[:10]
        print(f"\n  TOP 10 HITS (mes propers a sitis coneguts):")
        print(f"  {'Nom':<30} {'Score':<7} {'Dist(km)':<10} {'Tipus siti'}")
        print(f"  {'-'*30} {'-'*7} {'-'*10} {'-'*12}")
        for h in top_hits:
            print(f"  {h['name']:<30} {h['score']:.3f}  {h['nearest_dist_km']:<10.1f} {h['nearest_type']}")

    print(f"\n{'='*70}")

    return {
        "n_known_sites": len(known_sites),
        "n_hypotheses": n_total,
        "n_hits": n_hits,
        "hit_rate": round(hit_rate, 4),
        "candidate_hit_rate": round(candidate_hit_rate, 4),
        "coverage": round(coverage, 4),
        "avg_dist_km": round(avg_dist_hits, 2),
        "median_dist_km": round(median_dist_hits, 2),
        "hits": hits,
        "misses": misses,
    }


def export_validation_csv(results, output_path=None):
    """Exporta els resultats de validacio a CSV."""
    if results is None:
        return
    if output_path is None:
        output_path = Path(__file__).parent.parent / "data" / "validation_results.csv"
    output_path = Path(output_path)
    output_path.parent.mkdir(exist_ok=True, parents=True)

    all_records = sorted(
        results["hits"] + results["misses"],
        key=lambda r: r["score"],
        reverse=True,
    )

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank", "name", "entity_type", "lat", "lon", "score", "status",
            "nearest_known_site_km", "nearest_site_type", "is_hit",
        ])
        for i, r in enumerate(all_records, 1):
            writer.writerow([
                i, r["name"], r["entity_type"], r["lat"], r["lon"],
                r["score"], r["status"], r["nearest_dist_km"],
                r["nearest_type"], r["nearest_dist_km"] <= DEFAULT_THRESHOLD_KM,
            ])

    print(f"   Validacio exportada a: {output_path} ({len(all_records)} registres)")
    return str(output_path)
