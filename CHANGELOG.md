# CHANGELOG - Historial de Canvis i Optimitzacions

Registre de tots els canvis, millores i optimitzacions aplicades al projecte TFG.

---

## Fase 1: Estructura Base del Pipeline

### Moduls inicials creats
- **`pipeline.py`** — Orquestrador CLI amb argparse. Flux: ingestio → neteja → LLM → geocodificacio → scoring → exportacio.
- **`corpus_loader.py`** — Lector de fitxers TXT i PDF (via PyMuPDF). Detecta automaticament el format i extreu text cru.
- **`text_cleaner.py`** — Netejador de text OCR per a documents historics dels segles XVI-XIX.
- **`entity_extractor.py`** — Extraccio d'entitats geografiques amb LLM. Chunking + filtratge + parsing JSON.
- **`geocoder.py`** — Geocodificacio amb Nominatim (OpenStreetMap) amb viewbox amazonic.
- **`hypothesis_scorer.py`** — Sistema de scoring amb 6 senyals ponderades.
- **`database.py`** — SQLite amb 3 taules (documents, entities, hypotheses) i mode WAL per concurrencia.
- **`app.py`** — Interficie Streamlit amb mapa Folium interactiu.

### Base de dades (schema inicial)
- Taula `documents`: id, title, author, year, source_type, language, file_path, content, char_count, processed
- Taula `entities`: id, doc_id, name, entity_type, description, context, confidence, lat_llm, lon_llm, lat, lon, geo_status, geo_name
- Taula `hypotheses`: id, entity_id, lat, lon, score, status, notes, created_at
- Indexos sobre doc_id, coordenades i score

---

## Fase 2: Neteja de Text i OCR

### Neteja web agressiva (`text_cleaner.py`)
- **Problema**: Els PDFs d'Internet Archive contenien grans blocs de HTML, SVG, CSS, JavaScript i metadata incrustats que inflaven el text i confondien el LLM.
- **Solucio**: Funcio `strip_web_artifacts()` que elimina:
  - Blocs HTML complets (`<html>...</html>`, `<div>`, `<span>`, etc.)
  - CSS inline i blocs `<style>`
  - JavaScript i blocs `<script>`
  - SVG complets
  - Metadata d'Internet Archive
  - URLs i enllacos
- **Resultat**: Reduccio dramatica del tamany dels documents (alguns PDFs van passar de 500k+ chars a menys de 200k).

### Correccions OCR especifiques
- `ſ` (s llarga) → `s` normal
- Guions de final de linia reunificats
- Lligadures Unicode normalitzades (fi, fl, ff, etc.)
- Numeros de pagina i capcaleres repetides eliminats
- Espais en blanc multiples normalitzats

---

## Fase 3: Extraccio LLM amb Fallback

### Canvi de provider unic a dual (Claude + Ollama)
- **Abans**: Nomes Ollama local amb `llama3.1:8b-instruct-q4_0`.
- **Despres**: Sistema dual configurable via `.env`:
  - Provider principal: **Claude** (Anthropic API, cloud)
  - Fallback automatic: **Ollama** (local)
  - Si Claude falla (error API, timeout), es reintenta amb Ollama sense intervencio manual.

### Model actual
- **Claude**: `claude-haiku-4-5-20251001` — Rapid, econiomic, bona qualitat d'extraccio.
- **Ollama**: `qwen2.5:14b` — Model local com a fallback.

### Optimitzacio del chunking
- **Abans**: Chunks de ~6.000 caracters.
- **Despres**: Chunks de ~20.000 caracters. Claude te un context molt mes gran, permetent chunks mes grans amb menys perdua de context entre fragments.

### Coordenades estimades pel LLM
- **Millora clau**: El prompt del LLM ara demana que estimi coordenades (lat/lon) per a cada entitat basant-se en el context historic.
- Les coordenades LLM es copien directament a `lat/lon` i es marquen com `llm_estimated`.
- Nomes les entitats sense coordenades LLM van a Nominatim, estalviant centenars de peticions.

### Filtre geographic automatic
- Despres de l'extraccio, s'eliminen automaticament totes les entitats fora del bounding box amazonic:
  - Latitud: -20 a 5
  - Longitud: -80 a -45
- Evita falsos positius de llocs europeus o d'altres continents.

---

## Fase 4: Analisi Topografic SRTM

### Nou modul: `terrain_analyzer.py`
- **Objectiu**: Detectar anomalies topografiques que podrien indicar estructures precolombines (plataformes elevades, rases, geoglifs).
- **Metode**:
  1. Per a cada hipotesi, es genera un anell de 12 punts a 1.5 km del centre.
  2. Es descarrega l'elevacio SRTM (30m) del punt central i de l'anell.
  3. Es calcula la diferencia entre l'elevacio central i la mitjana de l'anell.
  4. Si la diferencia supera 2 metres, es marca com **anomalia topografica**.
  5. Es calcula la pendent maxima entre punts oposats de l'anell.

### Providers d'elevacio
- **Principal**: Llibreria `srtm` (tiles locals, SRTM 30m) — rapid, sense limits.
- **Fallback**: API Open-Elevation (REST) — mes lent, amb delay entre peticions.

### Camps afegits a la taula `hypotheses`
- `lidar_elevation` — Elevacio del punt central (metres)
- `lidar_slope` — Pendent maxima del terreny (graus)
- `lidar_anomaly` — 1 si es anomalia topografica, 0 si no

---

## Fase 5: Sistema de Scoring Evolucionat

### De 6 a 8 senyals
- **Scoring original (6 senyals)**:
  - Confianca LLM (20%), Tipus entitat (15%), Qualitat geo (20%), Descripcio (10%), Cross-ref (20%), Rius (15%)
- **Scoring actual (8 senyals)** amb pesos redistribuits:
  - Confianca LLM (14%), Tipus entitat (11%), Qualitat geo (14%), Descripcio (7%), Cross-ref (14%), Rius (10%)
  - **Anomalia elevacio (15%)** — Nova senyal basada en SRTM
  - **Idoneitat terreny (15%)** — Nova senyal combinada (pendent + elevacio)

### Deduplicacio per nom
- Les entitats duplicades (mateix nom en multiples documents) es fusionen, quedant la de millor score.
- Les cross-references es comptabilitzen correctament.

### Re-scoring amb terreny
- Despres de l'analisi SRTM, es recalculen tots els scores incorporant les dues noves senyals.
- Les hipotesis amb anomalies topografiques pugen significativament al ranking.

### Idoneitat terreny: criteris
- **Pendent**: <2 graus = 1.0, <5 = 0.8, <10 = 0.4, >10 = 0.1
- **Elevacio**: 50-500m = 1.0, 20-50m o 500-1000m = 0.6, <20m = 0.3 (zona inundable), >1000m = 0.2
- Score combinat: 60% pendent + 40% elevacio

---

## Fase 6: Validacio contra Ground Truth

### Nou modul: `ground_truth_validator.py`
- **Dataset**: Walker et al. 2023 — ~16.000 sitis arqueologics a l'Amazonia (earthworks, ADE, geoglyphs).
- **Metode**: Per a cada hipotesi, calcula la distancia haversine al siti conegut mes proper.
- **Llindar**: 50 km — una hipotesi es un "hit" si esta a menys de 50 km d'un siti real.

### Metriques calculades
- **Hit rate global**: % d'hipotesis a menys de 50 km d'un siti real
- **Hit rate candidates**: Idem pero nomes per hipotesis amb score >= 0.5
- **Cobertura**: % de sitis reals que tenen almenys una hipotesi a prop
- **Distancia mitjana/mediana dels hits**
- **Top 10 hits**: Les hipotesis mes properes a sitis reals

### Exportacio
- `data/validation_results.csv` — Totes les hipotesis amb la seva distancia al siti real mes proper i si son hit o no.

---

## Fase 7: Visualitzacio Streamlit

### `app.py` — Interficie web interactiva
- Mapa Folium centrat a l'Amazonia amb markers per cada entitat.
- Filtres per:
  - Tipus d'entitat (river, settlement, region, route, mountain, other)
  - Score minim
  - Status (candidate / low_priority)
- Taula de ranking amb totes les propietats.
- Integracio amb els sitis de Walker 2023 com a capa de referencia.

---

## Resum d'Optimitzacions Clau

| Optimitzacio | Impacte |
|---|---|
| Neteja web agressiva | Reduccio 50-70% del tamany dels documents |
| Dual provider (Claude + Ollama) | Fiabilitat i qualitat d'extraccio |
| Chunks de 20k chars | Menys fragmentacio, millor context per al LLM |
| Coordenades LLM estimades | Menys peticions Nominatim, mes rapidesa |
| Filtre bbox amazonic | Elimina falsos positius fora de la regio |
| Analisi SRTM | Deteccio d'anomalies topografiques |
| 8 senyals de scoring | Scoring mes complet i arqueologicament rellevant |
| Validacio Walker 2023 | Metriques objectives de qualitat |
| SQLite WAL mode | Concurrencia sense bloquejos |
| Deduplicacio per nom | Evita hipotesis repetides |
