"""
TFG: Pipeline Principal
Orquestra tot el flux automaticament:
  fitxer raw -> DB -> LLM -> geocodificacio -> scoring -> GeoJSON

Us des de la terminal (des de TFG/src/):

  python pipeline.py --files ..\\data\\carvajal_1542.txt
  python pipeline.py
  python pipeline.py --status
  python pipeline.py --geocode
  python pipeline.py --score
  python pipeline.py --export
  python pipeline.py --reset
"""

import argparse
import math
from pathlib import Path

from database         import DB
from corpus_loader    import load_from_data_dir, load_files
from entity_extractor import extract_entities
from geocoder         import geocode_all_db
from text_cleaner     import clean_ocr_text
from hypothesis_scorer import score_all, rescore_with_terrain, show_ranking, export_ranking_csv
from terrain_analyzer import analyze_all_with_db
from ground_truth_validator import validate_hypotheses, export_validation_csv
from gazetteer        import HistoricalGazetteer


def ingest_and_process(db: DB, docs: list[dict]):
    print(f"\nIngestio de {len(docs)} fitxers...\n")
    new_ids = []
    for doc in docs:
        doc["text"] = clean_ocr_text(doc["text"])
        doc_id = db.add_document(
            title       = doc["name"],
            content     = doc["text"],
            file_path   = doc.get("file_path"),
            source_type = doc.get("source_type", "unknown"),
        )
        if doc_id:
            new_ids.append(doc_id)

    pending = db.get_pending()
    if not pending:
        print("\nNo hi ha documents nous per processar.")
        return

    print(f"\nExtraient entitats de {len(pending)} documents amb LLM...\n")
    for doc in pending:
        content = db.get_content(doc["id"])
        if not content:
            continue

        print(f"\n'{doc['title']}' ({doc['char_count']:,} cars.)")
        entities = extract_entities(content, source_name=doc["title"])

        entity_dicts = [{
            "name":        e.name,
            "entity_type": e.entity_type,
            "description": e.description,
            "context":     e.context,
            "confidence":  e.confidence,
            "lat_llm":     e.lat,
            "lon_llm":     e.lon,
        } for e in entities]

        n = db.add_entities(doc["id"], entity_dicts)
        db.mark_processed(doc["id"])
        print(f"   {n} entitats guardades")

        # Copiar coordenades LLM a lat/lon i marcar com llm_estimated
        db.conn.execute(
            """UPDATE entities
               SET lat = lat_llm, lon = lon_llm, geo_status = 'llm_estimated'
               WHERE doc_id = ? AND lat_llm IS NOT NULL AND lon_llm IS NOT NULL AND lat IS NULL""",
            (doc["id"],),
        )
        db.conn.commit()

    # Filtre geographic: esborrar entitats fora del bounding box amazonic
    deleted = db.conn.execute(
        """DELETE FROM entities
           WHERE lat IS NOT NULL AND lon IS NOT NULL
             AND NOT (lat BETWEEN -20 AND 5 AND lon BETWEEN -80 AND -45)"""
    ).rowcount
    db.conn.commit()
    if deleted:
        print(f"\nFiltre bbox: {deleted} entitats eliminades (fora Amazonia)")


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = rlat2 - rlat1, rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def geocode_with_gazetteer(db: DB, max_distance_km=500):
    """
    Geocodificacio en cascada: busca entitats al gazetteer HGIS
    i actualitza coordenades si el match es fiable (< max_distance_km del LLM).
    """
    print("\nGeocodificacio en cascada amb gazetteer HGIS...\n")

    gz = HistoricalGazetteer()
    if gz.df.empty:
        print("   Gazetteer buit o no trobat.")
        return

    rows = db.conn.execute(
        """SELECT id, name, lat, lon, geo_status
           FROM entities
           WHERE lat IS NOT NULL AND lon IS NOT NULL"""
    ).fetchall()
    entities = [dict(r) for r in rows]

    if not entities:
        print("   No hi ha entitats amb coordenades.")
        return

    total = len(entities)
    matched = 0
    skipped_far = 0
    distances = []
    updates = []  # batch updates to avoid DB lock

    for ent in entities:
        result = gz.lookup(ent["name"])
        if result is None:
            continue

        # Check distance between LLM coords and gazetteer coords
        dist = _haversine(ent["lat"], ent["lon"], result["lat"], result["lon"])

        if dist > max_distance_km:
            skipped_far += 1
            print(f"   {ent['name']}: gazetteer ({result['lat']:.2f}, {result['lon']:.2f}) "
                  f"massa lluny del LLM ({ent['lat']:.2f}, {ent['lon']:.2f}) "
                  f"— {dist:.0f}km > {max_distance_km}km — ignorat")
            continue

        updates.append((result["lat"], result["lon"], ent["id"]))
        matched += 1
        distances.append(dist)

        print(f"   {ent['name']}: LLM ({ent['lat']:.2f}, {ent['lon']:.2f}) "
              f"→ Gazetteer ({result['lat']:.2f}, {result['lon']:.2f}) "
              f"[Δ {dist:.0f}km] [{result['pais']}]")

    # Batch update
    db.conn.executemany(
        "UPDATE entities SET lat=?, lon=?, geo_status='gazetteer' WHERE id=?",
        updates,
    )
    db.conn.commit()

    n_llm = total - matched
    avg_dist = sum(distances) / len(distances) if distances else 0

    print(f"\n{'='*60}")
    print(f"   Geocodificacio en cascada:")
    print(f"     Gazetteer HGIS: {matched}/{total} ({matched/total*100:.1f}%)")
    print(f"     LLM estimat:   {n_llm}/{total} ({n_llm/total*100:.1f}%)")
    if skipped_far:
        print(f"     Ignorats (massa lluny): {skipped_far}")
    if distances:
        print(f"     Distancia mitjana corregida: {avg_dist:.1f} km")
    print(f"{'='*60}")

    return matched


def normalize_coordinates(db: DB):
    """
    Normalitza coordenades: per a entitats amb el mateix nom (lowercase+strip),
    copia lat/lon/lat_llm/lon_llm de l'entitat amb la confidence mes alta
    a totes les altres del mateix nom.
    """
    print("\nNormalitzant coordenades d'entitats duplicades...\n")

    rows = db.conn.execute(
        "SELECT id, name, confidence, lat, lon, lat_llm, lon_llm FROM entities"
    ).fetchall()

    # Agrupar per nom normalitzat
    groups = {}
    for r in rows:
        key = r["name"].lower().strip()
        if key not in groups:
            groups[key] = []
        groups[key].append(dict(r))

    conf_order = {"high": 3, "medium": 2, "low": 1}
    updated = 0

    for name_key, ents in groups.items():
        if len(ents) < 2:
            continue

        # Escollir la millor: la de confidence mes alta (first occurrence on tie)
        best = max(ents, key=lambda e: conf_order.get(e["confidence"], 0))

        if best["lat"] is None and best["lon"] is None:
            continue

        for e in ents:
            if e["id"] == best["id"]:
                continue
            if (e["lat"] == best["lat"] and e["lon"] == best["lon"]
                    and e["lat_llm"] == best["lat_llm"]
                    and e["lon_llm"] == best["lon_llm"]):
                continue

            db.conn.execute(
                """UPDATE entities
                   SET lat = ?, lon = ?, lat_llm = ?, lon_llm = ?
                   WHERE id = ?""",
                (best["lat"], best["lon"], best["lat_llm"], best["lon_llm"], e["id"]),
            )
            updated += 1

    db.conn.commit()
    print(f"   Normalitzades {updated} entitats amb coordenades inconsistents")
    return updated


def reset_database(db: DB):
    """
    Neteja la DB: esborra entitats i hipotesis, re-aplica la neteja
    de text als documents ja guardats, i marca tot com a no processat.
    """
    print("\nRESET: Netejant base de dades...\n")

    # Esborrar entitats i hipotesis
    n_ent = db.conn.execute("SELECT COUNT(*) c FROM entities").fetchone()["c"]
    n_hyp = db.conn.execute("SELECT COUNT(*) c FROM hypotheses").fetchone()["c"]
    db.conn.execute("DELETE FROM entities")
    db.conn.execute("DELETE FROM hypotheses")
    db.conn.commit()
    print(f"   Esborrades {n_ent} entitats i {n_hyp} hipotesis")

    # Re-aplicar neteja de text
    docs = db.conn.execute("SELECT id, title, content, char_count FROM documents").fetchall()
    print(f"\n   Re-netejant {len(docs)} documents...\n")
    for doc in docs:
        original = doc["content"]
        original_len = doc["char_count"] or len(original)
        cleaned = clean_ocr_text(original)
        new_len = len(cleaned)
        reduction = (1 - new_len / original_len) * 100 if original_len else 0

        db.conn.execute(
            "UPDATE documents SET content=?, char_count=?, processed=0 WHERE id=?",
            (cleaned, new_len, doc["id"]),
        )
        print(f"   {doc['title']}: {original_len:,} -> {new_len:,} chars (-{reduction:.1f}%)")

    db.conn.commit()
    print("\nReset completat. Tots els documents marcats com a pendents.")
    db.summary()


def run_full_pipeline(files: list[str] = None):
    db = DB()

    if files:
        docs = load_files(files)
    else:
        docs = load_from_data_dir()

    if not docs:
        print("\nNo s'han trobat fitxers per processar.")
        print("   Posa els teus PDFs o TXTs a: TFG/data/")
        db.summary()
        db.close()
        return

    ingest_and_process(db, docs)

    # Nominatim nomes per entitats sense coordenades del LLM
    pending_geo = db.conn.execute(
        "SELECT COUNT(*) c FROM entities WHERE lat IS NULL AND geo_status IS NULL"
    ).fetchone()["c"]
    if pending_geo > 0:
        print(f"\n{pending_geo} entitats sense coordenades LLM -> geocodificant amb Nominatim...")
        geocode_all_db(db)
    else:
        print("\nTotes les entitats ja tenen coordenades (estimades pel LLM).")

    score_all(db)

    # Analisi topografic SRTM
    analyze_all_with_db(db)

    # Re-scoring amb dades de terreny
    rescore_with_terrain(db)

    show_ranking(db)

    # Validacio contra ground truth (Walker et al. 2023)
    results = validate_hypotheses(db)
    if results:
        export_validation_csv(results)

    db.export_geojson()
    db.summary()
    db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="TFG Pipeline — Extraccio arqueologica amb LLM"
    )
    parser.add_argument(
        "--files", nargs="+", metavar="PATH",
        help="Fitxers concrets a processar"
    )
    parser.add_argument("--status",  action="store_true", help="Mostra l'estat de la DB")
    parser.add_argument("--geocode", action="store_true", help="Geocodifica entitats pendents")
    parser.add_argument("--export",  action="store_true", help="Exporta GeoJSON")
    parser.add_argument("--reset",   action="store_true", help="Neteja DB i re-aplica neteja de text")
    parser.add_argument("--score",   action="store_true", help="Regenera scoring sense reprocessar")
    parser.add_argument("--terrain", action="store_true", help="Executa nomes l'analisi topografic SRTM")
    parser.add_argument("--validate", action="store_true", help="Valida hipotesis contra Walker et al. 2023")
    parser.add_argument("--normalize", action="store_true", help="Normalitza coordenades duplicades i regenera scoring")
    args = parser.parse_args()

    if args.normalize:
        db = DB()
        normalize_coordinates(db)
        print("\nRegenerant scoring...")
        score_all(db)
        show_ranking(db)
        db.summary()
        db.close()
    elif args.validate:
        db = DB()
        results = validate_hypotheses(db)
        if results:
            export_validation_csv(results)
        db.close()
    elif args.terrain:
        db = DB()
        analyze_all_with_db(db)
        rescore_with_terrain(db)
        show_ranking(db)
        db.close()
    elif args.reset:
        db = DB()
        reset_database(db)
        db.close()
    elif args.score:
        db = DB()
        score_all(db)
        analyze_all_with_db(db)
        rescore_with_terrain(db)
        show_ranking(db)
        export_ranking_csv(db)
        db.close()
    elif args.status or args.geocode or args.export:
        db = DB()
        if args.status:
            db.summary()
        elif args.geocode:
            geocode_with_gazetteer(db)
            print("\nRegenerant scoring...")
            score_all(db)
            show_ranking(db)
            db.summary()
        elif args.export:
            db.export_geojson()
        db.close()
    else:
        run_full_pipeline(files=args.files)
