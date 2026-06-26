"""
TFG: Test de Significança Estadística (Monte Carlo)
=====================================================
Verifica que el hit rate observat del sistema (43,1%) no és atribuïble
a l'atzar. Per fer-ho, genera milers de distribucions aleatòries de
punts dins de la zona d'estudi i calcula quin hit rate s'obtindria per
pura casualitat.

Metodologia:
  1. Es generen N_SIM (1.000) distribucions aleatòries de N_CAND (130)
     punts uniformement distribuïts dins del bounding box de la zona
     d'estudi (lat [-20, 5], lon [-80, -45]).
  2. Per a cada distribució, es calcula el hit rate a THRESHOLD (50 km)
     contra els mateixos 1.708 jaciments de Walker et al. utilitzats
     per validar les hipòtesis reals.
  3. La distribució dels 1.000 hit rates aleatoris dona la base de
     referència. Es calcula el Z-score i el p-value del valor observat.

Ús des de la terminal (des de TFG/src/):

  python monte_carlo.py
  python monte_carlo.py --sims 5000 --threshold 25
"""

import argparse
import csv
import random
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path
from statistics import mean, pstdev

# ── Configuració per defecte ─────────────────────────────────────────────────

WALKER_CSV   = Path("data/walker_2023/submit.csv")  # columnes: type, x=lon, y=lat
N_SIM        = 1000      # nombre de simulacions
N_CAND       = 130       # nombre de punts per simulació (= hipòtesis candidates)
THRESHOLD_KM = 50        # llindar de hit en km
OBSERVED     = 43.1      # hit rate observat del sistema (%)

# Bounding box de la zona d'estudi (igual que geo_filter.py)
LAT_MIN, LAT_MAX = -20.0, 5.0
LON_MIN, LON_MAX = -80.0, -45.0


# ── Utilitats ────────────────────────────────────────────────────────────────

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distància en km entre dos punts (fórmula Haversine)."""
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def load_walker_sites(path: Path = WALKER_CSV) -> list[tuple[float, float]]:
    """
    Carrega els jaciments de Walker et al. (2023) des del CSV.
    Retorna una llista de tuples (lat, lon).
    Filtra els jaciments fora del bounding box de la zona d'estudi
    per ser coherent amb la validació de les hipòtesis.
    """
    sites = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                lat = float(row["y"])
                lon = float(row["x"])
            except (ValueError, KeyError):
                continue
            if (LAT_MIN <= lat <= LAT_MAX) and (LON_MIN <= lon <= LON_MAX):
                sites.append((lat, lon))
    return sites


def random_hit_rate(walker: list[tuple[float, float]],
                    n_points: int, threshold: float) -> float:
    """
    Genera n_points aleatoris dins del bounding box i calcula quin
    percentatge cau a menys de `threshold` km d'algun jaciment Walker.
    """
    hits = 0
    for _ in range(n_points):
        lat = random.uniform(LAT_MIN, LAT_MAX)
        lon = random.uniform(LON_MIN, LON_MAX)
        min_dist = min(haversine(lat, lon, w[0], w[1]) for w in walker)
        if min_dist < threshold:
            hits += 1
    return hits / n_points * 100


# ── Simulació principal ──────────────────────────────────────────────────────

def run_simulation(n_sim: int = N_SIM, n_cand: int = N_CAND,
                   threshold: float = THRESHOLD_KM,
                   observed: float = OBSERVED) -> dict:
    """
    Executa la simulació Monte Carlo completa i imprimeix els resultats.
    Retorna un diccionari amb les estadístiques.
    """
    print("\n" + "=" * 55)
    print("  TEST DE MONTE CARLO — SIGNIFICANÇA ESTADÍSTICA")
    print("=" * 55)

    walker = load_walker_sites()
    print(f"  Jaciments Walker (dins zona): {len(walker)}")
    print(f"  Simulacions:                  {n_sim}")
    print(f"  Punts per simulació:          {n_cand}")
    print(f"  Llindar de hit:               {threshold} km")
    print(f"  Hit rate observat:            {observed}%")
    print("\n  Executant simulacions...")

    hit_rates = []
    for i in range(n_sim):
        if i % 100 == 0 and i > 0:
            print(f"     {i}/{n_sim}...")
        hit_rates.append(random_hit_rate(walker, n_cand, threshold))

    # ── Estadístiques ────────────────────────────────────────────────────
    mu = mean(hit_rates)
    sigma = pstdev(hit_rates)
    z_score = (observed - mu) / sigma if sigma > 0 else float("inf")

    # p-value empíric: proporció de simulacions que igualen o superen l'observat
    n_exceed = sum(1 for hr in hit_rates if hr >= observed)
    p_empiric = n_exceed / n_sim
    p_text = "< 0,001" if p_empiric == 0 else f"= {p_empiric:.4f}"

    # ── Resultats ────────────────────────────────────────────────────────
    print("\n" + "-" * 55)
    print("  RESULTATS")
    print("-" * 55)
    print(f"  Hit rate aleatori esperat:  {mu:.1f}% ± {sigma:.1f}%")
    print(f"  Hit rate observat:          {observed}%")
    print(f"  Z-score:                    {z_score:.1f}")
    print(f"  p-value:                    {p_text}")
    print("-" * 55)

    if z_score > 3:
        print(f"\n  ✅ El resultat és estadísticament significatiu (p {p_text}).")
        print(f"     El {observed}% se situa a {z_score:.1f} desviacions estàndard")
        print("     per sobre de la mitjana aleatòria. La correlació entre les")
        print("     hipòtesis i els jaciments coneguts NO és atribuïble a l'atzar.")
    else:
        print(f"\n  ⚠️  El resultat NO és clarament significatiu (Z = {z_score:.1f}).")
    print("=" * 55)

    return {
        "random_mean": mu,
        "random_std": sigma,
        "observed": observed,
        "z_score": z_score,
        "p_value": p_empiric,
        "hit_rates": hit_rates,
    }


# ── Punt d'entrada ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test de Monte Carlo per a la significança del hit rate"
    )
    parser.add_argument("--sims", type=int, default=N_SIM,
                        help=f"Nombre de simulacions (per defecte {N_SIM})")
    parser.add_argument("--points", type=int, default=N_CAND,
                        help=f"Punts per simulació (per defecte {N_CAND})")
    parser.add_argument("--threshold", type=float, default=THRESHOLD_KM,
                        help=f"Llindar de hit en km (per defecte {THRESHOLD_KM})")
    parser.add_argument("--observed", type=float, default=OBSERVED,
                        help=f"Hit rate observat en %% (per defecte {OBSERVED})")
    args = parser.parse_args()

    run_simulation(
        n_sim=args.sims,
        n_cand=args.points,
        threshold=args.threshold,
        observed=args.observed,
    )
