"""
TFG: Sistema de Puntuacio d'Hipotesis Arqueologiques
Avalua cada entitat geocodificada i genera hipotesis
ordenades per score. Usa 6 senyals ponderades.
"""

import csv
import math
from pathlib import Path

WEIGHTS = {
    "confidence":    0.14,
    "entity_type":   0.11,
    "geo_quality":   0.14,
    "description":   0.07,
    "cross_ref":     0.14,
    "river_prox":    0.10,
    "elevation_anomaly":   0.15,
    "terrain_suitability": 0.15,
}

AMAZON_BBOX = {"lat_min": -20, "lat_max": 5, "lon_min": -80, "lon_max": -45}


def inside_amazon_bbox(lat, lon) -> bool:
    """Retorna True si les coordenades cauen dins del bounding box amazonic."""
    return (AMAZON_BBOX["lat_min"] <= lat <= AMAZON_BBOX["lat_max"]
            and AMAZON_BBOX["lon_min"] <= lon <= AMAZON_BBOX["lon_max"])


MAJOR_RIVERS = [
    ("Amazonas",     -3.1300,  -60.0200),
    ("Napo",         -1.0700,  -75.5600),
    ("Maranon",      -4.4500,  -77.5000),
    ("Ucayali",      -8.3800,  -74.5300),
    ("Madeira",      -3.3200,  -58.9500),
    ("Tapajos",      -2.4000,  -54.7200),
    ("Beni",        -14.8200,  -67.5300),
    ("Madre de Dios",-12.5900, -69.1800),
    ("Guapore",     -12.6800,  -63.4200),
    ("Mamor",       -10.1500,  -65.3700),
    ("Itenez",      -12.5000,  -64.0700),
    ("Negro",        -3.0700,  -60.3500),
    ("Putumayo",     -1.5000,  -73.0000),
    ("Xingu",        -3.2000,  -52.2000),
]


def haversine_km(lat1, lon1, lat2, lon2):
    """Distancia haversine entre dos punts en km."""
    R = 6371.0
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def min_river_distance(lat, lon):
    """Distancia minima a un riu principal amazonic (km)."""
    return min(haversine_km(lat, lon, rlat, rlon) for _, rlat, rlon in MAJOR_RIVERS)


def score_confidence(confidence: str) -> float:
    return {"high": 1.0, "medium": 0.6, "low": 0.2}.get(confidence, 0.1)


def score_entity_type(entity_type: str) -> float:
    return {
        "settlement": 1.0,
        "route": 0.7,
        "region": 0.5,
        "mountain": 0.4,
        "river": 0.3,
        "other": 0.2,
    }.get(entity_type, 0.2)


def score_geo_quality(entity) -> float:
    geo_status = entity["geo_status"]
    if geo_status == "gazetteer":
        # Coordenades verificades via gazetteer historic HGIS
        return 0.9
    if geo_status == "found":
        # Geocodificat amb Nominatim: comparar amb estimacio LLM si existeix
        score = 0.7
        lat_llm = entity["lat_llm"]
        lon_llm = entity["lon_llm"]
        lat = entity["lat"]
        lon = entity["lon"]
        if lat_llm and lon_llm and lat and lon:
            dist = haversine_km(lat_llm, lon_llm, lat, lon)
            if dist < 50:
                score = 1.0
            elif dist < 200:
                score = 0.8
            else:
                score = 0.5
        return score
    elif geo_status == "llm_estimated":
        # Coordenades estimades pel LLM: qualitat moderada
        return 0.5
    return 0.0


def score_description(description: str) -> float:
    if not description:
        return 0.0
    length = len(description)
    if length > 200:
        return 1.0
    elif length > 100:
        return 0.7
    elif length > 30:
        return 0.4
    return 0.2


def score_cross_reference(entity_name: str, all_entities: list, current_doc_id: int) -> float:
    """Puntua si l'entitat apareix en multiples documents independents."""
    name_lower = entity_name.lower().strip()
    doc_ids = set()
    for e in all_entities:
        if e["name"].lower().strip() == name_lower:
            doc_ids.add(e["doc_id"])
    n_docs = len(doc_ids)
    if n_docs >= 3:
        return 1.0
    elif n_docs == 2:
        return 0.7
    return 0.0


def score_river_proximity(lat, lon) -> float:
    """Mes a prop d'un riu navegable = mes probable asentament."""
    dist = min_river_distance(lat, lon)
    if dist < 20:
        return 1.0
    elif dist < 50:
        return 0.8
    elif dist < 150:
        return 0.5
    elif dist < 500:
        return 0.2
    return 0.0


def score_elevation_anomaly(lidar_anomaly) -> float:
    """
    Si lidar_anomaly == 1, el punt esta mes alt que el seu entorn.
    Molt interessant arqueologicament (possible plataforma artificial).
    """
    if lidar_anomaly is None:
        return 0.0
    return 1.0 if lidar_anomaly == 1 else 0.0


def score_terrain_suitability(lidar_slope, lidar_elevation) -> float:
    """
    Terreny apte per asentament: pendent baixa + elevacio moderada.
    Els asentaments amazonics solen estar en terreny pla pero lleugerament elevat.
    """
    if lidar_slope is None or lidar_elevation is None:
        return 0.0

    # Pendent: ideal < 5 graus
    if lidar_slope < 2:
        slope_score = 1.0
    elif lidar_slope < 5:
        slope_score = 0.8
    elif lidar_slope < 10:
        slope_score = 0.4
    else:
        slope_score = 0.1

    # Elevacio: zona amazonica, ideal entre 50 i 500m
    if 50 <= lidar_elevation <= 500:
        elev_score = 1.0
    elif 20 <= lidar_elevation < 50 or 500 < lidar_elevation <= 1000:
        elev_score = 0.6
    elif lidar_elevation < 20:
        elev_score = 0.3  # Zona molt baixa, possible inundacio
    else:
        elev_score = 0.2  # Muntanya alta

    return slope_score * 0.6 + elev_score * 0.4


def compute_score(entity, all_entities: list, hypothesis=None) -> float:
    """
    Calcula el score final d'una entitat (0.0 - 1.0).
    Si hypothesis es proporcionat, inclou senyals de terreny.
    """
    signals = {
        "confidence":  score_confidence(entity["confidence"]),
        "entity_type": score_entity_type(entity["entity_type"]),
        "geo_quality": score_geo_quality(entity),
        "description": score_description(entity["description"] or ""),
        "cross_ref":   score_cross_reference(entity["name"], all_entities, entity["doc_id"]),
        "river_prox":  score_river_proximity(entity["lat"], entity["lon"]),
    }

    # Senyals de terreny (si hi ha dades SRTM)
    if hypothesis is not None:
        lidar_anomaly = hypothesis.get("lidar_anomaly") if isinstance(hypothesis, dict) else hypothesis["lidar_anomaly"]
        lidar_slope = hypothesis.get("lidar_slope") if isinstance(hypothesis, dict) else hypothesis["lidar_slope"]
        lidar_elevation = hypothesis.get("lidar_elevation") if isinstance(hypothesis, dict) else hypothesis["lidar_elevation"]
        signals["elevation_anomaly"] = score_elevation_anomaly(lidar_anomaly)
        signals["terrain_suitability"] = score_terrain_suitability(lidar_slope, lidar_elevation)
    else:
        signals["elevation_anomaly"] = 0.0
        signals["terrain_suitability"] = 0.0

    return sum(WEIGHTS[k] * signals[k] for k in WEIGHTS)


def score_all(db) -> int:
    """
    Puntua totes les entitats geocodificades i guarda hipotesis a la DB.
    Retorna el nombre d'hipotesis generades.
    """
    entities = db.conn.execute(
        """SELECT e.*, d.title as doc_title
           FROM entities e JOIN documents d ON e.doc_id = d.id
           WHERE e.lat IS NOT NULL AND e.lon IS NOT NULL"""
    ).fetchall()

    if not entities:
        print("No hi ha entitats geocodificades per puntuar.")
        return 0

    # Filtre geographic: descartar entitats fora del bounding box amazonic
    filtered = [e for e in entities if inside_amazon_bbox(e["lat"], e["lon"])]
    n_dropped = len(entities) - len(filtered)
    if n_dropped:
        print(f"Filtre geographic: {n_dropped} entitats descartades (fora bbox Amazonia)")
    if not filtered:
        print("Cap entitat dins del bounding box amazonic.")
        return 0

    all_entities = db.conn.execute("SELECT name, doc_id FROM entities").fetchall()

    # Guardar dades de terreny existents abans d'esborrar
    terrain_data = {}
    existing = db.conn.execute(
        """SELECT entity_id, lidar_elevation, lidar_slope, lidar_anomaly
           FROM hypotheses
           WHERE lidar_elevation IS NOT NULL"""
    ).fetchall()
    for row in existing:
        terrain_data[row["entity_id"]] = {
            "lidar_elevation": row["lidar_elevation"],
            "lidar_slope": row["lidar_slope"],
            "lidar_anomaly": row["lidar_anomaly"],
        }

    # Netejar hipotesis anteriors
    db.conn.execute("DELETE FROM hypotheses")
    db.conn.commit()

    # Scoring + deduplicacio per nom normalitzat
    best = {}  # clau: nom normalitzat, valor: dict amb la millor hipotesi
    for e in filtered:
        score = compute_score(e, all_entities)
        key = e["name"].lower().strip()

        if key not in best:
            best[key] = {
                "entity_id": e["id"],
                "lat": e["lat"],
                "lon": e["lon"],
                "score": score,
                "doc_title": e["doc_title"],
                "name": e["name"],
                "doc_ids": {e["doc_id"]},
            }
        else:
            best[key]["doc_ids"].add(e["doc_id"])
            if score > best[key]["score"]:
                best[key].update({
                    "entity_id": e["id"],
                    "lat": e["lat"],
                    "lon": e["lon"],
                    "score": score,
                    "doc_title": e["doc_title"],
                })

    count = 0
    for key, h in best.items():
        status = "candidate" if h["score"] >= 0.5 else "low_priority"
        n_docs = len(h["doc_ids"])
        notes = f"Auto-scored from {h['doc_title']}"
        if n_docs > 1:
            notes += f" | Mencionada en {n_docs} documents"

        db.conn.execute(
            """INSERT INTO hypotheses (entity_id, lat, lon, score, status, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (h["entity_id"], h["lat"], h["lon"], round(h["score"], 4), status, notes),
        )
        count += 1

    # Restaurar dades de terreny preservades
    if terrain_data:
        for entity_id, td in terrain_data.items():
            db.conn.execute(
                """UPDATE hypotheses
                   SET lidar_elevation = ?, lidar_slope = ?, lidar_anomaly = ?
                   WHERE entity_id = ?""",
                (td["lidar_elevation"], td["lidar_slope"], td["lidar_anomaly"], entity_id),
            )

    db.conn.commit()
    candidates = db.conn.execute(
        "SELECT COUNT(*) c FROM hypotheses WHERE status='candidate'"
    ).fetchone()["c"]
    print(f"\nScoring completat: {count} hipotesis ({candidates} candidates, {count - candidates} low_priority)")
    return count


def rescore_with_terrain(db) -> int:
    """
    Re-calcula els scores de totes les hipotesis incorporant les dades de terreny
    (lidar_elevation, lidar_slope, lidar_anomaly). S'executa despres de terrain_analyzer.
    Retorna el nombre d'hipotesis actualitzades.
    """
    hypotheses = db.conn.execute(
        """SELECT h.id, h.entity_id, h.lidar_elevation, h.lidar_slope, h.lidar_anomaly
           FROM hypotheses h"""
    ).fetchall()

    if not hypotheses:
        return 0

    # Comprovar si hi ha dades de terreny
    has_terrain = any(h["lidar_elevation"] is not None for h in hypotheses)
    if not has_terrain:
        print("   No hi ha dades de terreny per re-scoring.")
        return 0

    all_entities = db.conn.execute("SELECT name, doc_id FROM entities").fetchall()

    updated = 0
    for hyp in hypotheses:
        entity = db.conn.execute(
            """SELECT e.*, d.title as doc_title
               FROM entities e JOIN documents d ON e.doc_id = d.id
               WHERE e.id = ?""",
            (hyp["entity_id"],),
        ).fetchone()

        if not entity:
            continue

        hyp_dict = {
            "lidar_elevation": hyp["lidar_elevation"],
            "lidar_slope": hyp["lidar_slope"],
            "lidar_anomaly": hyp["lidar_anomaly"],
        }

        new_score = compute_score(entity, all_entities, hypothesis=hyp_dict)
        status = "candidate" if new_score >= 0.5 else "low_priority"

        db.conn.execute(
            "UPDATE hypotheses SET score = ?, status = ? WHERE id = ?",
            (round(new_score, 4), status, hyp["id"]),
        )
        updated += 1

    db.conn.commit()

    candidates = db.conn.execute(
        "SELECT COUNT(*) c FROM hypotheses WHERE status='candidate'"
    ).fetchone()["c"]
    total = len(hypotheses)
    print(f"\nRe-scoring amb terreny: {updated} hipotesis actualitzades "
          f"({candidates} candidates, {total - candidates} low_priority)")
    return updated


def show_ranking(db, top_n: int = 20):
    """Mostra el top N d'hipotesis per score."""
    rows = db.conn.execute(
        """SELECT h.score, h.status, h.lat, h.lon, e.name, e.entity_type,
                  e.confidence, e.description, d.title as doc_title
           FROM hypotheses h
           JOIN entities e ON h.entity_id = e.id
           JOIN documents d ON e.doc_id = d.id
           ORDER BY h.score DESC
           LIMIT ?""",
        (top_n,),
    ).fetchall()

    if not rows:
        print("No hi ha hipotesis per mostrar.")
        return

    print(f"\n{'='*80}")
    print(f"  TOP {top_n} HIPOTESIS ARQUEOLOGIQUES")
    print(f"{'='*80}")
    print(f"  {'#':<4} {'Score':<7} {'Nom':<30} {'Tipus':<12} {'Status':<12} {'Font'}")
    print(f"  {'-'*4} {'-'*7} {'-'*30} {'-'*12} {'-'*12} {'-'*20}")
    for i, r in enumerate(rows, 1):
        print(f"  {i:<4} {r['score']:.3f}  {r['name']:<30} {r['entity_type']:<12} {r['status']:<12} {r['doc_title']}")
    print(f"{'='*80}")


def export_ranking_csv(db, output_path: str = None) -> str:
    """Exporta el ranking complet a CSV."""
    if output_path is None:
        output_path = Path(__file__).parent.parent / "data" / "hypotheses_ranking.csv"
    output_path = Path(output_path)
    output_path.parent.mkdir(exist_ok=True, parents=True)

    rows = db.conn.execute(
        """SELECT h.score, h.status, h.lat, h.lon, e.name, e.entity_type,
                  e.confidence, e.description, d.title as doc_title
           FROM hypotheses h
           JOIN entities e ON h.entity_id = e.id
           JOIN documents d ON e.doc_id = d.id
           ORDER BY h.score DESC"""
    ).fetchall()

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "score", "status", "name", "type", "confidence",
                         "lat", "lon", "description", "source"])
        for i, r in enumerate(rows, 1):
            writer.writerow([
                i, r["score"], r["status"], r["name"], r["entity_type"],
                r["confidence"], r["lat"], r["lon"], r["description"], r["doc_title"],
            ])

    print(f"Ranking exportat a: {output_path} ({len(rows)} files)")
    return str(output_path)
