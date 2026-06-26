"""
TFG: Filtre Geogràfic
Descarta entitats geocodificades que cauen fora de la zona d'estudi
amazònica. Els textos d'exploradors com Orbigny recorren tota
Sud-amèrica (Buenos Aires, Patagònia, Estret de Magallanes...), però
aquest treball només s'interessa per la conca amazònica i regions
adjacents.

Bounding box de la zona d'estudi:
  - Latitud:  [-20°, 5°]
  - Longitud: [-80°, -45°]

Cobreix Amazònia, Bolívia, Perú, Brasil occidental, Equador oriental
i Colòmbia meridional.

Ús des de la terminal (des de TFG/src/):

  python geo_filter.py            # marca les entitats fora de zona
  python geo_filter.py --report   # només informa, no modifica res
"""

import argparse

LAT_MIN, LAT_MAX = -20.0, 5.0
LON_MIN, LON_MAX = -80.0, -45.0


def is_within_study_area(lat: float, lon: float) -> bool:
    """
    Retorna True si les coordenades cauen dins del bounding box
    de la zona d'estudi amazònica.
    """
    if lat is None or lon is None:
        return False
    return (LAT_MIN <= lat <= LAT_MAX) and (LON_MIN <= lon <= LON_MAX)


def filter_entities_db(db, dry_run: bool = False) -> dict:
    """
    Recorre les entitats geocodificades de la base de dades i marca
    com a fora de zona (geo_status = 'out_of_area') les que cauen
    fora del bounding box.

    Si dry_run=True, només compta sense modificar res.
    Retorna un resum amb els comptadors.
    """
    rows = db.conn.execute("""
        SELECT e.id, e.name, e.lat, e.lon, e.geo_status, d.title AS doc_title
        FROM entities e
        JOIN documents d ON e.doc_id = d.id
        WHERE e.lat IS NOT NULL AND e.lon IS NOT NULL
    """).fetchall()

    total = len(rows)
    inside = 0
    outside = 0
    outside_examples = []

    for r in rows:
        if is_within_study_area(r["lat"], r["lon"]):
            inside += 1
        else:
            outside += 1
            if len(outside_examples) < 15:
                outside_examples.append((r["name"], r["lat"], r["lon"], r["doc_title"]))
            if not dry_run:
                db.conn.execute(
                    "UPDATE entities SET geo_status = 'out_of_area' WHERE id = ?",
                    (r["id"],),
                )

    if not dry_run:
        db.conn.commit()

    print("\n" + "=" * 55)
    print("  FILTRE GEOGRÀFIC — ZONA D'ESTUDI AMAZÒNICA")
    print(f"  Bounding box: lat [{LAT_MIN}, {LAT_MAX}], lon [{LON_MIN}, {LON_MAX}]")
    print("=" * 55)
    print(f"  Total entitats geocodificades: {total}")
    print(f"  Dins de la zona:  {inside} ({inside/total*100:.1f}%)" if total else "  (cap entitat)")
    print(f"  Fora de la zona:  {outside} ({outside/total*100:.1f}%)" if total else "")

    if outside_examples:
        print("\n  Exemples d'entitats descartades:")
        for name, lat, lon, doc in outside_examples:
            print(f"     • {name} [{lat:.2f}, {lon:.2f}]  ({doc})")

    if dry_run:
        print("\n  Mode informe: no s'ha modificat res.")
    else:
        print(f"\n  {outside} entitats marcades com a 'out_of_area'.")
    print("=" * 55)

    return {"total": total, "inside": inside, "outside": outside}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Filtre geogràfic per a la zona d'estudi amazònica"
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Només informa de les entitats fora de zona, sense modificar la BD"
    )
    args = parser.parse_args()

    from database import DB

    db = DB()
    filter_entities_db(db, dry_run=args.report)
    db.close()
