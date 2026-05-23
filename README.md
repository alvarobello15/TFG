# TFG - Hipotesis Arqueologiques a l'Amazonia amb LLMs

Treball de Fi de Grau (Enginyeria de Dades, UAB). Combina LLMs (Claude / Ollama) amb analisi geoespacial i topografic per generar hipotesis sobre possibles ubicacions d'assentaments arqueologics precolombins a l'Amazonia, inspirat en l'OpenAI to Z Challenge.

## Estructura del projecte

```
TFG/
├── data/                           # Textos historics i sortides
│   ├── carvajal_1542_clean.txt     # Cronica de Gaspar de Carvajal (netejat)
│   ├── acuna_1641.pdf              # Relacio de Cristobal de Acuna
│   ├── orbigny_tomo1.pdf           # Alcide d'Orbigny, volum 1
│   ├── orbigny_tomo2.pdf           # Alcide d'Orbigny, volum 2
│   ├── orbigny_tomo3.pdf           # Alcide d'Orbigny, volum 3
│   ├── entities.geojson            # Sortida: entitats geocodificades (GeoJSON)
│   ├── hypotheses_ranking.csv      # Sortida: ranking d'hipotesis
│   └── validation_results.csv      # Sortida: metriques de validacio
├── src/
│   ├── pipeline.py                 # Orquestrador principal (CLI)
│   ├── corpus_loader.py            # Lectura de fitxers TXT/PDF
│   ├── text_cleaner.py             # Neteja OCR + eliminacio basura web
│   ├── entity_extractor.py         # Extraccio d'entitats amb LLM (Claude/Ollama)
│   ├── geocoder.py                 # Geocodificacio amb Nominatim
│   ├── hypothesis_scorer.py        # Puntuacio i ranking d'hipotesis (8 senyals)
│   ├── terrain_analyzer.py         # Analisi topografic SRTM (elevacio, pendent, anomalies)
│   ├── ground_truth_validator.py   # Validacio contra Walker et al. 2023
│   ├── database.py                 # Base de dades SQLite (WAL mode)
│   ├── app.py                      # Visualitzacio Streamlit amb mapa interactiu
│   ├── .env                        # Configuracio del proveidor LLM
│   ├── tfg.db                      # Base de dades (generada automaticament)
│   └── data/
│       └── walker_2023/
│           ├── submit.csv          # Ground truth: ~16k sitis arqueologics
│           └── variables.xlsx      # Metadata del dataset
└── README.md
```

## Requisits previs

- **Python** 3.10+
- **Ollama** instal.lat i executant-se localment (nomes si uses el provider local)
- **Clau API Anthropic** (nomes si uses Claude com a provider)

## Instal.lacio

```bash
# 1. Clonar o descarregar el projecte
cd TFG/

# 2. Instal.lar dependencies
pip install pymupdf ollama geopy streamlit folium streamlit-folium python-dotenv srtm anthropic pandas

# 3. Configurar el proveidor LLM (editar src/.env)
#    - Per usar Claude: posar ANTHROPIC_API_KEY i LLM_PROVIDER=claude
#    - Per usar Ollama: posar LLM_PROVIDER=ollama i descarregar el model:
ollama pull qwen2.5:14b
```

## Configuracio (.env)

El fitxer `src/.env` controla quin LLM s'usa i amb quins paramet
```

## Com executar el projecte

Totes les comandes s'executen des de `TFG/src/`:

```bash
cd src/

# ── Pipeline complet ──────────────────────────────────────────────
# Executa tot: ingestio → neteja → LLM → geocodificacio → scoring
#              → analisi SRTM → re-scoring → validacio → exportacio
python pipeline.py

# Processar fitxers concrets
python pipeline.py --files ../data/carvajal_1542_clean.txt

# ── Comandes individuals ──────────────────────────────────────────
python pipeline.py --status      # Estat de la base de dades
python pipeline.py --geocode     # Geocodificar entitats pendents
python pipeline.py --score       # Regenerar scoring (inclou terreny)
python pipeline.py --terrain     # Nomes analisi topografic SRTM
python pipeline.py --validate    # Validar contra Walker et al. 2023
python pipeline.py --export      # Exportar GeoJSON
python pipeline.py --reset       # Netejar DB, re-aplicar neteja, marcar tot pendent

# ── Visualitzacio interactiva ─────────────────────────────────────
streamlit run app.py
```

## Que fa cada modul

| Modul | Funcio |
|---|---|
| `pipeline.py` | Orquestra tot el flux: ingestio, neteja, extraccio LLM, geocodificacio, scoring, terreny, validacio |
| `corpus_loader.py` | Llegeix fitxers .txt i .pdf de `data/` i retorna el text cru |
| `text_cleaner.py` | Neteja artefactes OCR (s llarga, guions, lligadures) i elimina basura web (HTML, SVG, CSS, JS) dels PDFs d'Internet Archive |
| `entity_extractor.py` | Divideix el text en chunks (~20.000 chars), filtra els inutils, i envia els bons al LLM (Claude o Ollama) per extreure entitats geografiques en JSON |
| `geocoder.py` | Converteix noms de lloc en coordenades reals via Nominatim (OpenStreetMap), amb viewbox amazonic |
| `hypothesis_scorer.py` | Avalua cada entitat amb **8 senyals ponderades** i genera un ranking d'hipotesis amb deduplicacio per nom |
| `terrain_analyzer.py` | Descarrega elevacio SRTM (30m) per a cada hipotesi, calcula anomalies topografiques i pendent del terreny |
| `ground_truth_validator.py` | Compara les hipotesis amb ~16.000 sitis arqueologics reals del dataset Walker et al. 2023 |
| `database.py` | Gestiona la DB SQLite (WAL mode) amb 3 taules: `documents`, `entities`, `hypotheses` |
| `app.py` | Interficie Streamlit amb mapa Folium interactiu, filtres per tipus/score, i taula de ranking |

## Com funciona el pipeline

1. **Ingestio**: `corpus_loader.py` llegeix els fitxers de `data/` (TXT o PDF via PyMuPDF)
2. **Neteja**: `text_cleaner.py` elimina basura web (HTML, SVG, CSS, JS, Internet Archive) i aplica correccions OCR (s llarga, guions, lligadures)
3. **Emmagatzematge**: El text net es guarda a la taula `documents` de `tfg.db`
4. **Chunking**: El text es divideix en fragments de ~20.000 caracters per no excedir el context del LLM
5. **Filtratge de chunks**: Es comprova que cada chunk contingui text real (minim 30 paraules, 50%+ caracters alfabetics)
6. **Extraccio LLM**: Cada chunk util s'envia a Claude (cloud) o Ollama (local) que extreu entitats geografiques (rius, assentaments, regions, rutes, muntanyes) en format JSON amb coordenades estimades
7. **Geocodificacio**: Les entitats sense coordenades LLM es geocodifiquen amb Nominatim. Les que ja tenen coords LLM es marquen com `llm_estimated`
8. **Filtre geographic**: S'eliminen entitats fora del bounding box amazonic (lat -20 a 5, lon -80 a -45)
9. **Scoring**: 8 senyals ponderades generen un score de 0 a 1 per cada entitat (veure taula sota)
10. **Analisi topografic SRTM**: Per a cada hipotesi, es descarrega elevacio SRTM i es calculen anomalies (possibles plataformes artificials) i pendent
11. **Re-scoring**: Es recalculen els scores incorporant les dades de terreny
12. **Validacio**: Es comparen les hipotesis amb sitis reals de Walker et al. 2023 (llindar: 50 km)
13. **Exportacio**: GeoJSON per mapes i CSV amb el ranking

## Sistema de scoring (8 senyals)

Les hipotesis es puntuen de 0 a 1 amb 8 senyals ponderades:

| Senyal | Pes | Descripcio |
|---|---|---|
| Confianca LLM | 14% | high=1.0, medium=0.6, low=0.2 |
| Tipus d'entitat | 11% | settlement=1.0, route=0.7, region=0.5, mountain=0.4, river=0.3 |
| Qualitat geocodificacio | 14% | Nominatim found + concordancia amb LLM coords (<50km=1.0, <200km=0.8) |
| Riquesa descripcio | 7% | Descripcions mes llargues = mes informacio (>200chars=1.0) |
| Cross-reference | 14% | Apareix en 3+ docs=1.0, 2 docs=0.7, 1 doc=0.0 |
| Proximitat a rius | 10% | Distancia haversine a 14 rius principals amazonics (<20km=1.0) |
| **Anomalia elevacio** | **15%** | Punt mes elevat que l'entorn (>2m sobre mitjana ring) = possible plataforma artificial |
| **Idoneitat terreny** | **15%** | Pendent baixa (<2deg=1.0) + elevacio moderada (50-500m=1.0) |

Status: `candidate` (score >= 0.5) o `low_priority` (score < 0.5)

## Sortides del projecte

| Fitxer | Descripcio |
|---|---|
| `data/entities.geojson` | Feature collection amb totes les entitats geocodificades i propietats |
| `data/hypotheses_ranking.csv` | Ranking complet ordenat per score |
| `data/validation_results.csv` | Metriques de validacio contra Walker 2023 (hit rate, cobertura, distancies) |
| `src/tfg.db` | Base de dades SQLite amb tot l'estat del pipeline |

## Tecnologies

- **Python 3.10+** — Llenguatge principal
- **Claude API (Anthropic)** — Extraccio d'entitats (cloud, model principal)
- **Ollama** — Extraccio d'entitats (local, fallback)
- **SQLite 3 (WAL mode)** — Persistencia i estat del pipeline
- **SRTM 30m** — Model digital d'elevacio per analisi topografic
- **Nominatim / OpenStreetMap** — Geocodificacio
- **Streamlit + Folium** — Visualitzacio interactiva amb mapa
- **PyMuPDF** — Extraccio de text de PDFs
- **Walker et al. 2023** — Dataset de ground truth (~16k sitis arqueologics)
