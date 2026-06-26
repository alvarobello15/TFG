"""
TFG: Analisi Topografic SRTM
Per a cada hipotesi amb coordenades, descarrega elevacio SRTM
i calcula anomalies topografiques que podrien indicar estructures
precolombines (plataformes elevades, rases, geoglifs).

Usa la llibreria `srtm` (pip install srtm) amb fallback a l'API
Open-Elevation.

Executable de forma independent:
  python terrain_analyzer.py
"""

import math
import time
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "tfg.db"


RING_RADIUS_KM = 1.5          # Radi de l'anell de mostreig (km)
RING_POINTS = 12               # Punts distribuits en l'anell
ANOMALY_THRESHOLD_M = 2.0     # Metres per sobre de la mitjana per marcar anomalia
API_DELAY_S = 0.3              # Delay entre peticions API (segons)


def offset_point(lat, lon, bearing_deg, distance_km):
    """
    Calcula un nou punt (lat, lon) a partir d'un punt origen,
    un rumb (bearing) en graus i una distancia en km.
    """
    R = 6371.0
    d = distance_km / R
    bearing = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)

    lat2 = math.asin(
        math.sin(lat1) * math.cos(d)
        + math.cos(lat1) * math.sin(d) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(d) * math.cos(lat1),
        math.cos(d) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


def ring_points(lat, lon, radius_km, n_points):
    """Genera n punts distribuits uniformement en un cercle al voltant de (lat, lon)."""
    points = []
    for i in range(n_points):
        bearing = 360.0 * i / n_points
        p = offset_point(lat, lon, bearing, radius_km)
        points.append(p)
    return points


def calculate_slope(elevations_ring, radius_km):
    """
    Estima la pendent del terreny en graus a partir de les elevacions
    dels punts de l'anell. Usa la diferencia maxima d'elevacio entre
    punts oposats de l'anell.
    """
    n = len(elevations_ring)
    if n < 4:
        return None

    max_slope = 0.0
    for i in range(n // 2):
        opposite = i + n // 2
        if opposite >= n:
            break
        elev_diff = abs(elevations_ring[i] - elevations_ring[opposite])
        horizontal_dist = 2 * radius_km * 1000  # metres
        if horizontal_dist > 0:
            slope_rad = math.atan(elev_diff / horizontal_dist)
            slope_deg = math.degrees(slope_rad)
            max_slope = max(max_slope, slope_deg)

    return round(max_slope, 2)


def _get_srtm_provider():
    """Intenta importar i retornar el proveidor srtm."""
    try:
        import srtm
        data = srtm.get_data()
        return data
    except Exception:
        return None


def get_elevation_srtm(srtm_data, lat, lon):
    """Obte l'elevacio d'un punt amb la llibreria srtm."""
    try:
        elev = srtm_data.get_elevation(lat, lon)
        if elev is not None:
            return float(elev)
    except Exception:
        pass
    return None


def get_elevations_batch_srtm(srtm_data, points):
    """Obte elevacions per a una llista de punts amb srtm."""
    results = []
    for lat, lon in points:
        elev = get_elevation_srtm(srtm_data, lat, lon)
        results.append(elev)
    return results


def get_elevations_batch_api(points, delay=API_DELAY_S):
    """
    Obte elevacions per a una llista de punts usant l'API Open-Elevation.
    Fa una sola peticio POST amb tots els punts.
    """
    import urllib.request
    import json

    url = "https://api.open-elevation.com/api/v1/lookup"
    locations = [{"latitude": lat, "longitude": lon} for lat, lon in points]
    payload = json.dumps({"locations": locations}).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )

    try:
        time.sleep(delay)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return [r.get("elevation") for r in data.get("results", [])]
    except Exception as e:
        print(f"   [!] Error API Open-Elevation: {e}")
        return [None] * len(points)


def analyze_point(lat, lon, srtm_data=None):
    """
    Analitza un punt: obte elevacio central i del ring,
    calcula anomalia i pendent.

    Retorna dict amb: elevation, mean_ring, anomaly_m, slope, is_anomaly
    o None si no es possible obtenir dades.
    """
    # Generar punts del ring
    ring = ring_points(lat, lon, RING_RADIUS_KM, RING_POINTS)
    all_points = [(lat, lon)] + ring  # centre + ring

    # Obtenir elevacions
    if srtm_data is not None:
        elevations = get_elevations_batch_srtm(srtm_data, all_points)
    else:
        elevations = get_elevations_batch_api(all_points)

    center_elev = elevations[0]
    ring_elevs = elevations[1:]

    # Filtrar Nones
    if center_elev is None:
        return None

    valid_ring = [e for e in ring_elevs if e is not None]
    if len(valid_ring) < 4:
        # No hi ha prou dades de l'entorn
        return {
            "elevation": center_elev,
            "mean_ring": None,
            "anomaly_m": None,
            "slope": None,
            "is_anomaly": False,
        }

    mean_ring = sum(valid_ring) / len(valid_ring)
    anomaly_m = center_elev - mean_ring
    slope = calculate_slope(valid_ring, RING_RADIUS_KM)
    is_anomaly = anomaly_m > ANOMALY_THRESHOLD_M

    return {
        "elevation": round(center_elev, 1),
        "mean_ring": round(mean_ring, 1),
        "anomaly_m": round(anomaly_m, 2),
        "slope": slope,
        "is_anomaly": is_anomaly,
    }


def analyze_all(db_path=DB_PATH):
    """
    Analitza totes les hipotesis amb coordenades.
    Actualitza lidar_elevation, lidar_slope i lidar_anomaly a la taula hypotheses.
    Retorna el nombre de punts analitzats amb exit.
    """
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row

    hypotheses = conn.execute(
        "SELECT id, lat, lon FROM hypotheses WHERE lat IS NOT NULL AND lon IS NOT NULL"
    ).fetchall()

    if not hypotheses:
        print("No hi ha hipotesis amb coordenades per analitzar.")
        conn.close()
        return 0

    total = len(hypotheses)
    print(f"\nAnalisi topografic SRTM: {total} punts\n")

    # Intentar usar srtm library
    srtm_data = _get_srtm_provider()
    if srtm_data:
        print("   Usant llibreria srtm (tiles locals/SRTM 30m)")
    else:
        print("   Llibreria srtm no disponible, usant API Open-Elevation")

    analyzed = 0
    errors = 0

    for i, hyp in enumerate(hypotheses, 1):
        lat, lon = hyp["lat"], hyp["lon"]
        print(f"   [{i}/{total}] Hipotesi #{hyp['id']} ({lat:.4f}, {lon:.4f})...", end=" ")

        try:
            result = analyze_point(lat, lon, srtm_data)

            if result is None:
                print("sense dades SRTM")
                errors += 1
                continue

            conn.execute(
                """UPDATE hypotheses
                   SET lidar_elevation = ?,
                       lidar_slope     = ?,
                       lidar_anomaly   = ?
                   WHERE id = ?""",
                (
                    result["elevation"],
                    result["slope"],
                    1 if result["is_anomaly"] else 0,
                    hyp["id"],
                ),
            )
            conn.commit()
            analyzed += 1

            status = "ANOMALIA!" if result["is_anomaly"] else "normal"
            elev_str = f"{result['elevation']}m"
            slope_str = f"{result['slope']}deg" if result['slope'] is not None else "N/A"
            anom_str = f"{result['anomaly_m']:+.1f}m" if result['anomaly_m'] is not None else "N/A"
            print(f"elev={elev_str}  pendent={slope_str}  anomalia={anom_str}  [{status}]")

        except Exception as e:
            print(f"ERROR: {e}")
            errors += 1
            continue

        # Delay entre punts si usem API
        if srtm_data is None and i < total:
            time.sleep(API_DELAY_S)

    conn.close()

    anomalies = analyzed  # recalculem desde la DB
    conn2 = sqlite3.connect(str(db_path))
    n_anom = conn2.execute(
        "SELECT COUNT(*) c FROM hypotheses WHERE lidar_anomaly = 1"
    ).fetchone()[0]
    conn2.close()

    print(f"\nAnalisi completat: {analyzed}/{total} punts analitzats")
    if errors:
        print(f"   {errors} punts sense dades SRTM")
    print(f"   {n_anom} anomalies topografiques detectades")

    return analyzed


def analyze_all_with_db(db):
    """
    Versio que accepta un objecte DB ja obert (per integracio amb pipeline).
    """
    hypotheses = db.conn.execute(
        "SELECT id, lat, lon FROM hypotheses WHERE lat IS NOT NULL AND lon IS NOT NULL"
    ).fetchall()

    if not hypotheses:
        print("No hi ha hipotesis amb coordenades per analitzar.")
        return 0

    total = len(hypotheses)
    print(f"\nAnalisi topografic SRTM: {total} punts\n")

    srtm_data = _get_srtm_provider()
    if srtm_data:
        print("   Usant llibreria srtm (tiles locals/SRTM 30m)")
    else:
        print("   Llibreria srtm no disponible, usant API Open-Elevation")

    analyzed = 0
    errors = 0

    for i, hyp in enumerate(hypotheses, 1):
        lat, lon = hyp["lat"], hyp["lon"]
        print(f"   [{i}/{total}] Hipotesi #{hyp['id']} ({lat:.4f}, {lon:.4f})...", end=" ")

        try:
            result = analyze_point(lat, lon, srtm_data)

            if result is None:
                print("sense dades SRTM")
                errors += 1
                continue

            db.conn.execute(
                """UPDATE hypotheses
                   SET lidar_elevation = ?,
                       lidar_slope     = ?,
                       lidar_anomaly   = ?
                   WHERE id = ?""",
                (
                    result["elevation"],
                    result["slope"],
                    1 if result["is_anomaly"] else 0,
                    hyp["id"],
                ),
            )
            db.conn.commit()
            analyzed += 1

            status = "ANOMALIA!" if result["is_anomaly"] else "normal"
            elev_str = f"{result['elevation']}m"
            slope_str = f"{result['slope']}deg" if result['slope'] is not None else "N/A"
            anom_str = f"{result['anomaly_m']:+.1f}m" if result['anomaly_m'] is not None else "N/A"
            print(f"elev={elev_str}  pendent={slope_str}  anomalia={anom_str}  [{status}]")

        except Exception as e:
            print(f"ERROR: {e}")
            errors += 1
            continue

        if srtm_data is None and i < total:
            time.sleep(API_DELAY_S)

    n_anom = db.conn.execute(
        "SELECT COUNT(*) c FROM hypotheses WHERE lidar_anomaly = 1"
    ).fetchone()["c"]

    print(f"\nAnalisi completat: {analyzed}/{total} punts analitzats")
    if errors:
        print(f"   {errors} punts sense dades SRTM")
    print(f"   {n_anom} anomalies topografiques detectades")

    return analyzed


 ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  TFG - Analisi Topografic SRTM")
    print("=" * 60)
    n = analyze_all()
    if n == 0:
        print("\nExecuta primer el pipeline per generar hipotesis:")
        print("  python pipeline.py")
