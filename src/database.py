"""
TFG: Base de Dades SQLite
===========================
Gestiona documents, entitats i hipòtesis.
El fitxer tfg.db es crea automàticament a TFG/src/
"""

import sqlite3
import json
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "tfg.db"


class DB:
    def __init__(self, path: Path = DB_PATH):
        self.path = path
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()
        print(f"📂 Base de dades: {path}")

    def _create_tables(self):
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS documents (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL UNIQUE,
            author      TEXT,
            year        INTEGER,
            source_type TEXT,
            language    TEXT DEFAULT 'es',
            file_path   TEXT,
            content     TEXT,
            char_count  INTEGER,
            processed   INTEGER DEFAULT 0,
            created_at  TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS entities (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id       INTEGER NOT NULL REFERENCES documents(id),
            name         TEXT NOT NULL,
            entity_type  TEXT,
            description  TEXT,
            context      TEXT,
            confidence   TEXT,
            lat_llm      REAL,
            lon_llm      REAL,
            lat          REAL,
            lon          REAL,
            geo_status   TEXT,
            geo_name     TEXT,
            created_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS hypotheses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id       INTEGER REFERENCES entities(id),
            lat             REAL NOT NULL,
            lon             REAL NOT NULL,
            score           REAL,
            lidar_elevation REAL,
            lidar_slope     REAL,
            lidar_anomaly   INTEGER DEFAULT 0,
            status          TEXT DEFAULT 'candidate',
            notes           TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_entities_doc  ON entities(doc_id);
        CREATE INDEX IF NOT EXISTS idx_entities_geo  ON entities(lat, lon);
        CREATE INDEX IF NOT EXISTS idx_hyp_score     ON hypotheses(score DESC);
        """)
        self.conn.commit()

    # ── Documents ────────────────────────────────────────────────────────────

    def add_document(self, title, content, author=None, year=None,
                     source_type="unknown", language="es", file_path=None) -> Optional[int]:
        existing = self.conn.execute(
            "SELECT id FROM documents WHERE title = ?", (title,)
        ).fetchone()
        if existing:
            print(f"   ⚠️  Ja existeix: '{title}'")
            return None  # None = no cal reprocessar

        cur = self.conn.execute(
            """INSERT INTO documents (title, author, year, source_type, language, file_path, content, char_count)
               VALUES (?,?,?,?,?,?,?,?)""",
            (title, author, year, source_type, language, file_path, content, len(content)),
        )
        self.conn.commit()
        print(f"   ✅ Afegit: '{title}' ({len(content):,} cars.)")
        return cur.lastrowid

    def mark_processed(self, doc_id: int):
        self.conn.execute("UPDATE documents SET processed=1 WHERE id=?", (doc_id,))
        self.conn.commit()

    def get_pending(self) -> list:
        return self.conn.execute(
            "SELECT id, title, char_count FROM documents WHERE processed=0"
        ).fetchall()

    def get_content(self, doc_id: int) -> Optional[str]:
        row = self.conn.execute("SELECT content FROM documents WHERE id=?", (doc_id,)).fetchone()
        return row["content"] if row else None

    # ── Entitats ─────────────────────────────────────────────────────────────

    def add_entities(self, doc_id: int, entities: list[dict]) -> int:
        rows = [(
            doc_id,
            e.get("name", "Unknown"),
            e.get("entity_type", "other"),
            e.get("description", ""),
            e.get("context", ""),
            e.get("confidence", "low"),
            e.get("lat_llm"),
            e.get("lon_llm"),
        ) for e in entities]

        self.conn.executemany(
            """INSERT INTO entities (doc_id, name, entity_type, description, context, confidence, lat_llm, lon_llm)
               VALUES (?,?,?,?,?,?,?,?)""", rows,
        )
        self.conn.commit()
        return len(rows)

    def update_geocoding(self, entity_id: int, lat, lon, geo_status: str, geo_name: str):
        self.conn.execute(
            "UPDATE entities SET lat=?, lon=?, geo_status=?, geo_name=? WHERE id=?",
            (lat, lon, geo_status, geo_name, entity_id),
        )
        self.conn.commit()

    def get_entities_without_coords(self) -> list:
        return self.conn.execute(
            "SELECT id, name, entity_type FROM entities WHERE lat IS NULL AND geo_status IS NULL"
        ).fetchall()

    def get_entities_with_coords(self) -> list:
        return self.conn.execute(
            """SELECT e.*, d.title as doc_title, d.author, d.year
               FROM entities e JOIN documents d ON e.doc_id = d.id
               WHERE e.lat IS NOT NULL AND e.lon IS NOT NULL"""
        ).fetchall()

    # ── Resum i export ────────────────────────────────────────────────────────

    def summary(self):
        d = self.conn.execute("SELECT COUNT(*) t, SUM(processed) p FROM documents").fetchone()
        e = self.conn.execute(
            "SELECT COUNT(*) t, SUM(lat IS NOT NULL) g, SUM(confidence='high') h FROM entities"
        ).fetchone()
        h = self.conn.execute("SELECT COUNT(*) c FROM hypotheses").fetchone()["c"]

        print("\n" + "="*50)
        print("  ESTAT DE LA BASE DE DADES")
        print("="*50)
        print(f"  Documents : {d['t']} total  ({d['p'] or 0} processats)")
        print(f"  Entitats  : {e['t']} total  ({e['g'] or 0} geocodificades, {e['h'] or 0} alta conf.)")
        print(f"  Hipòtesis : {h} candidates")
        print("="*50)

    def export_geojson(self, output_path: str = None) -> str:
        if output_path is None:
            output_path = Path(__file__).parent.parent / "data" / "entities.geojson"
        entities = self.get_entities_with_coords()

        # Obtenir dades de terreny de les hipotesis
        terrain_data = {}
        hyps = self.conn.execute(
            "SELECT entity_id, lidar_elevation, lidar_slope, lidar_anomaly, score FROM hypotheses"
        ).fetchall()
        for h in hyps:
            terrain_data[h["entity_id"]] = {
                "elevation": h["lidar_elevation"],
                "slope": h["lidar_slope"],
                "anomaly": h["lidar_anomaly"],
                "score": h["score"],
            }

        features = []
        for e in entities:
            props = {
                "name": e["name"], "type": e["entity_type"],
                "confidence": e["confidence"], "description": e["description"],
                "source": e["doc_title"], "author": e["author"], "year": e["year"],
            }
            # Afegir propietats de terreny si existeixen
            t = terrain_data.get(e["id"], {})
            if t:
                props["score"] = t.get("score")
                props["elevation"] = t.get("elevation")
                props["slope"] = t.get("slope")
                props["anomaly"] = t.get("anomaly")

            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [e["lon"], e["lat"]]},
                "properties": props,
            })

        Path(output_path).parent.mkdir(exist_ok=True, parents=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False, indent=2)
        print(f"🗺️  GeoJSON exportat: {output_path} ({len(features)} punts)")
        return str(output_path)

    def close(self):
        self.conn.close()