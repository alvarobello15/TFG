"""
TFG: Pagina d'Analytics
=========================
Metriques i analisi del rendiment del sistema.
Segona pagina de l'app Streamlit (multi-page).
"""

import sqlite3
import math
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

DB_PATH = Path(__file__).resolve().parent.parent / "tfg.db"

# ── Paleta ────────────────────────────────────────────────────────────────────

BLUE    = "#2196F3"
GREEN   = "#4CAF50"
AMBER   = "#FF9800"
RED     = "#F44336"
GRAY    = "#9E9E9E"
CYAN    = "#00BCD4"
PURPLE  = "#9C27B0"
COLOR_SEQ = [BLUE, GREEN, AMBER, RED, CYAN, PURPLE, "#78909C", "#FF5722"]

# ── Scoring weights (mirall de hypothesis_scorer.py) ──────────────────────────

WEIGHTS = {
    "confidence":          0.14,
    "entity_type":         0.11,
    "geo_quality":         0.14,
    "description":         0.07,
    "cross_ref":           0.14,
    "river_prox":          0.10,
    "elevation_anomaly":   0.15,
    "terrain_suitability": 0.15,
}

MAJOR_RIVERS = [
    ("Amazonas",     -3.13,  -60.02), ("Napo",        -1.07,  -75.56),
    ("Maranon",      -4.45,  -77.50), ("Ucayali",     -8.38,  -74.53),
    ("Madeira",      -3.32,  -58.95), ("Tapajos",     -2.40,  -54.72),
    ("Beni",        -14.82,  -67.53), ("Madre de Dios",-12.59, -69.18),
    ("Guapore",     -12.68,  -63.42), ("Mamor",       -10.15,  -65.37),
    ("Itenez",      -12.50,  -64.07), ("Negro",        -3.07,  -60.35),
    ("Putumayo",     -1.50,  -73.00), ("Xingu",        -3.20,  -52.20),
]

SIGNAL_NAMES = [
    "Confianca LLM", "Tipus entitat", "Qualitat geo", "Descripcio",
    "Cross-reference", "Proximitat rius", "Anomalia terreny", "Aptitud terreny",
]
SIGNAL_TO_WEIGHT = dict(zip(SIGNAL_NAMES, WEIGHTS.values()))

# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """
<style>
.main-header {
    text-align: center;
    padding: 1.5rem 0 0.5rem 0;
}
.main-header h1 {
    font-size: 1.75rem;
    font-weight: 700;
    color: #FAFAFA;
    margin-bottom: 0.2rem;
    letter-spacing: 0.02em;
}
.main-header .subtitle {
    font-size: 0.85rem;
    color: #9E9E9E;
    margin-bottom: 0.15rem;
}
.main-header .authors {
    font-size: 0.78rem;
    color: #6B7280;
}
.section-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: #B0BEC5;
    margin-top: 1.2rem;
    margin-bottom: 0.3rem;
    padding-bottom: 0.4rem;
    border-bottom: 1px solid #2A2F35;
    letter-spacing: 0.01em;
}
.section-desc {
    font-size: 0.8rem;
    color: #6B7280;
    margin-bottom: 0.8rem;
    font-style: italic;
}
.kpi-card {
    background: #1E2329;
    border: 1px solid #2A2F35;
    border-radius: 10px;
    padding: 1rem 1.2rem;
    text-align: center;
}
.kpi-card .kpi-label {
    font-size: 0.72rem;
    color: #9E9E9E;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 0.25rem;
}
.kpi-card .kpi-value {
    font-size: 1.65rem;
    font-weight: 700;
    color: #FAFAFA;
}
.kpi-card .kpi-icon {
    font-size: 1.1rem;
    margin-bottom: 0.2rem;
}
.kpi-green  .kpi-value { color: #4CAF50; }
.kpi-amber  .kpi-value { color: #FF9800; }
.kpi-red    .kpi-value { color: #F44336; }
.kpi-blue   .kpi-value { color: #2196F3; }
.footer {
    text-align: center;
    padding: 2rem 0 1rem 0;
    font-size: 0.72rem;
    color: #4B5563;
    border-top: 1px solid #1E2329;
    margin-top: 2rem;
}
.tab-intro {
    font-size: 0.82rem;
    color: #6B7280;
    margin-bottom: 1rem;
    font-style: italic;
}
</style>
"""

# ── Plotly theme helper ───────────────────────────────────────────────────────

def apply_plotly_theme(fig, height=400):
    """Apply consistent dark theme to all plotly figures."""
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#B0BEC5", size=12),
        title_font=dict(size=14, color="#FAFAFA"),
        margin=dict(l=40, r=20, t=50, b=40),
        height=height,
        xaxis=dict(gridcolor="#1E2329", gridwidth=1),
        yaxis=dict(gridcolor="#1E2329", gridwidth=1),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig


# ── Helpers ───────────────────────────────────────────────────────────────────

@st.cache_resource
def get_connection():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def kpi_card(icon, label, value, css_class=""):
    return f"""
    <div class="kpi-card {css_class}">
        <div class="kpi-icon">{icon}</div>
        <div class="kpi-label">{label}</div>
        <div class="kpi-value">{value}</div>
    </div>
    """


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    rlat1, rlon1, rlat2, rlon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def min_river_distance(lat, lon):
    return min(haversine_km(lat, lon, rlat, rlon) for _, rlat, rlon in MAJOR_RIVERS)


# ── Signal recomputation ─────────────────────────────────────────────────────

def _s_confidence(c):
    return {"high": 1.0, "medium": 0.6, "low": 0.2}.get(c, 0.1)

def _s_entity_type(t):
    return {"settlement": 1.0, "route": 0.7, "region": 0.5,
            "mountain": 0.4, "river": 0.3, "other": 0.2}.get(t, 0.2)

def _s_geo_quality(row):
    gs = row.get("geo_status")
    if gs == "found":
        s = 0.6
        if row.get("lat_llm") and row.get("lon_llm") and row.get("lat") and row.get("lon"):
            d = haversine_km(row["lat_llm"], row["lon_llm"], row["lat"], row["lon"])
            s = 1.0 if d < 50 else (0.8 if d < 200 else 0.5)
        return s
    if gs == "llm_estimated":
        return 0.5
    return 0.0

def _s_description(desc):
    if not desc:
        return 0.0
    l = len(desc)
    return 1.0 if l > 200 else (0.7 if l > 100 else (0.4 if l > 30 else 0.2))

def _s_cross_ref(name, all_names_docs):
    n = len(set(did for n, did in all_names_docs if n == name.lower().strip()))
    return 1.0 if n >= 3 else (0.7 if n == 2 else 0.0)

def _s_river_prox(lat, lon):
    d = min_river_distance(lat, lon)
    if d < 20: return 1.0
    if d < 50: return 0.8
    if d < 150: return 0.5
    if d < 500: return 0.2
    return 0.0

def _s_elev_anomaly(a):
    if a is None: return 0.0
    return 1.0 if a == 1 else 0.0

def _s_terrain_suit(slope, elev):
    if slope is None or elev is None:
        return 0.0
    ss = 1.0 if slope < 2 else (0.8 if slope < 5 else (0.4 if slope < 10 else 0.1))
    es = (1.0 if 50 <= elev <= 500
          else (0.6 if 20 <= elev < 50 or 500 < elev <= 1000
          else (0.3 if elev < 20 else 0.2)))
    return ss * 0.6 + es * 0.4


def compute_signal_breakdown(rows_df, all_names_docs):
    records = []
    for _, r in rows_df.iterrows():
        signals = {
            "Confianca LLM":    _s_confidence(r.get("confidence")),
            "Tipus entitat":    _s_entity_type(r.get("entity_type")),
            "Qualitat geo":     _s_geo_quality(r),
            "Descripcio":       _s_description(r.get("description") or ""),
            "Cross-reference":  _s_cross_ref(r["name"], all_names_docs),
            "Proximitat rius":  _s_river_prox(r["lat"], r["lon"]),
            "Anomalia terreny": _s_elev_anomaly(r.get("lidar_anomaly")),
            "Aptitud terreny":  _s_terrain_suit(r.get("lidar_slope"), r.get("lidar_elevation")),
        }
        signals["name"] = r["name"]
        records.append(signals)
    return pd.DataFrame(records)


# ── Ground truth ──────────────────────────────────────────────────────────────

def _load_gt_sites():
    import sys
    sys.path.insert(0, str(DB_PATH.parent))
    try:
        from ground_truth_validator import load_walker_sites
        return load_walker_sites()
    except Exception:
        return []


def run_validation(conn, threshold_km=50):
    sites = _load_gt_sites()
    if not sites:
        return None

    hyps = conn.execute(
        """SELECT h.id, h.lat, h.lon, h.score, h.status, e.name, e.entity_type
           FROM hypotheses h JOIN entities e ON h.entity_id = e.id
           ORDER BY h.score DESC"""
    ).fetchall()
    if not hyps:
        return None

    hits, misses = [], []
    for h in hyps:
        best_dist = float("inf")
        best_site = None
        for s in sites:
            d = haversine_km(h["lat"], h["lon"], s["lat"], s["lon"])
            if d < best_dist:
                best_dist = d
                best_site = s
        rec = {
            "name": h["name"], "entity_type": h["entity_type"],
            "lat": h["lat"], "lon": h["lon"], "score": h["score"],
            "status": h["status"], "nearest_dist_km": round(best_dist, 2),
            "nearest_type": best_site["type"] if best_site else None,
        }
        (hits if best_dist <= threshold_km else misses).append(rec)

    n_total = len(hyps)
    n_hits = len(hits)
    cand_total = sum(1 for h in hyps if h["status"] == "candidate")
    cand_hits = sum(1 for h in hits if h["status"] == "candidate")

    matched_sites = set()
    for s in sites:
        for h in hyps:
            if haversine_km(h["lat"], h["lon"], s["lat"], s["lon"]) <= threshold_km:
                matched_sites.add((s["lat"], s["lon"]))
                break

    avg_dist = sum(h["nearest_dist_km"] for h in hits) / n_hits if n_hits else 0
    sorted_dists = sorted(h["nearest_dist_km"] for h in hits)
    median_dist = sorted_dists[n_hits // 2] if n_hits else 0

    return {
        "n_known": len(sites), "n_hyps": n_total,
        "n_hits": n_hits, "hit_rate": n_hits / n_total if n_total else 0,
        "cand_total": cand_total, "cand_hits": cand_hits,
        "cand_hit_rate": cand_hits / cand_total if cand_total else 0,
        "coverage": len(matched_sites) / len(sites) if sites else 0,
        "avg_dist": round(avg_dist, 1), "median_dist": round(median_dist, 1),
        "hits": hits, "misses": misses,
    }


# =============================================================================
#  MAIN
# =============================================================================

def main():
    st.markdown(CSS, unsafe_allow_html=True)

    st.markdown("""<div class="main-header">
    <h1>Generacio i Validacio d'Hipotesis Arqueologiques</h1>
    <div class="subtitle">Pipeline LLM + LiDAR per a la prospeccio a l'Amazonia — TFG Enginyeria de Dades, UAB 2026</div>
    <div class="authors">Alvaro Bello Marabe &nbsp;|&nbsp; Tutora: Ana Oropesa</div>
    </div>""", unsafe_allow_html=True)

    st.markdown('<div class="page-title"><div class="pt-accent"></div><h2>Analytics</h2></div>',
                unsafe_allow_html=True)

    if not DB_PATH.exists():
        st.error(f"Base de dades no trobada: {DB_PATH}")
        return

    conn = get_connection()

    # ── Pre-load data ─────────────────────────────────────────────────────
    n_docs = conn.execute("SELECT COUNT(*) c FROM documents").fetchone()["c"]
    n_ents = conn.execute("SELECT COUNT(*) c FROM entities").fetchone()["c"]
    n_geo = conn.execute(
        "SELECT COUNT(*) c FROM entities WHERE lat IS NOT NULL"
    ).fetchone()["c"]
    n_hyps = conn.execute("SELECT COUNT(*) c FROM hypotheses").fetchone()["c"]
    n_cand = conn.execute(
        "SELECT COUNT(*) c FROM hypotheses WHERE status='candidate'"
    ).fetchone()["c"]
    validation = run_validation(conn)

    # ── KPI row ───────────────────────────────────────────────────────────
    st.markdown('<div class="section-title">Estat del pipeline</div>',
                unsafe_allow_html=True)

    hit_rate_val = validation["cand_hit_rate"] if validation else 0
    hit_rate_str = f"{validation['cand_hit_rate']:.1%}" if validation else "N/A"
    hr_class = ("kpi-green" if hit_rate_val > 0.20
                else ("kpi-amber" if hit_rate_val > 0.10 else "kpi-red"))

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.markdown(kpi_card("&#128196;", "Documents", n_docs), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("&#127981;", "Entitats", n_ents), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("&#127759;", "Geocodificades", n_geo, "kpi-blue"),
                    unsafe_allow_html=True)
    with c4:
        st.markdown(kpi_card("&#128202;", "Hipotesis", n_hyps), unsafe_allow_html=True)
    with c5:
        st.markdown(kpi_card("&#11088;", "Candidates", n_cand, "kpi-green"),
                    unsafe_allow_html=True)
    with c6:
        st.markdown(kpi_card("&#127919;", "Hit rate", hit_rate_str, hr_class),
                    unsafe_allow_html=True)

    st.markdown("", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════
    #  TABS
    # ══════════════════════════════════════════════════════════════════════
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Resum i distribucio",
        "Fonts i scoring",
        "Validacio",
        "Terreny",
        "Cobertura",
    ])

    # ── TAB 1: Resum i distribucio ────────────────────────────────────────
    with tab1:
        st.markdown('<p class="tab-intro">'
                    'Distribucio dels scores i classificacio de les entitats extretes.'
                    '</p>', unsafe_allow_html=True)

        # -- Score histogram --
        st.markdown('<div class="section-title">Com es distribueixen els scores?</div>',
                    unsafe_allow_html=True)

        scores_rows = conn.execute(
            "SELECT score FROM hypotheses WHERE score IS NOT NULL"
        ).fetchall()
        if scores_rows:
            scores = [r["score"] for r in scores_rows]
            scores_df = pd.DataFrame({"score": scores})

            n_above = sum(1 for s in scores if s >= 0.5)
            n_below = sum(1 for s in scores if s < 0.5)

            fig = px.histogram(scores_df, x="score", nbins=25,
                               color_discrete_sequence=[BLUE],
                               labels={"score": "Score", "count": "Nombre"})
            fig.add_vline(x=0.5, line_dash="dash", line_color=RED,
                          annotation_text="Umbral candidat (0.5)",
                          annotation_font_color=RED)
            fig.update_layout(bargap=0.05)
            apply_plotly_theme(fig, 350)
            st.plotly_chart(fig, use_container_width=True)

            mc1, mc2 = st.columns(2)
            with mc1:
                st.markdown(kpi_card("&#9989;", "Candidates (&ge; 0.5)", n_above, "kpi-green"),
                            unsafe_allow_html=True)
            with mc2:
                st.markdown(kpi_card("&#9898;", "Low priority (&lt; 0.5)", n_below),
                            unsafe_allow_html=True)
        else:
            st.info("No hi ha dades de scores disponibles.")

        st.markdown("", unsafe_allow_html=True)

        # -- Entities by type --
        st.markdown('<div class="section-title">Quins tipus d\'entitats ha extret el pipeline?</div>',
                    unsafe_allow_html=True)

        type_rows = conn.execute(
            "SELECT entity_type, COUNT(*) c FROM entities GROUP BY entity_type ORDER BY c DESC"
        ).fetchall()
        if type_rows:
            type_df = pd.DataFrame([dict(r) for r in type_rows])

            col1, col2 = st.columns(2)
            with col1:
                fig = px.bar(type_df, x="entity_type", y="c",
                             color="entity_type",
                             color_discrete_sequence=COLOR_SEQ,
                             labels={"entity_type": "Tipus", "c": "Nombre"})
                fig.update_layout(showlegend=False)
                apply_plotly_theme(fig, 350)
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                fig = px.pie(type_df, names="entity_type", values="c",
                             color_discrete_sequence=COLOR_SEQ,
                             hole=0.4)
                apply_plotly_theme(fig, 350)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hi ha dades d'entitats.")

        # -- Full data table --
        st.markdown("", unsafe_allow_html=True)
        st.markdown('<div class="section-title">Taula completa d\'hipotesis</div>',
                    unsafe_allow_html=True)
        st.markdown('<p class="section-desc">Totes les hipotesis amb les seves columnes. '
                    'Filtrable, ordenable i descarregable.</p>',
                    unsafe_allow_html=True)

        all_rows = conn.execute(
            """SELECT h.id as hyp_id, h.score, h.status, h.lat, h.lon,
                      h.lidar_elevation, h.lidar_slope, h.lidar_anomaly, h.notes,
                      e.name, e.entity_type, e.confidence, e.description,
                      e.geo_status, e.geo_name,
                      d.title as doc_title, d.author, d.year
               FROM hypotheses h
               JOIN entities e ON h.entity_id = e.id
               JOIN documents d ON e.doc_id = d.id
               ORDER BY h.score DESC"""
        ).fetchall()

        if all_rows:
            full_df = pd.DataFrame([dict(r) for r in all_rows])
            st.dataframe(full_df, use_container_width=True, height=450)

            csv_data = full_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Descarregar CSV",
                data=csv_data,
                file_name="hipotesis_completes.csv",
                mime="text/csv",
            )
        else:
            st.info("No hi ha hipotesis a la base de dades.")

    # ── TAB 2: Fonts i scoring ────────────────────────────────────────────
    with tab2:
        st.markdown('<p class="tab-intro">'
                    'Analisi per document font i desglose de les senyals que componen cada score.'
                    '</p>', unsafe_allow_html=True)

        # -- By document --
        st.markdown('<div class="section-title">Quantes entitats aporta cada document?</div>',
                    unsafe_allow_html=True)

        doc_rows = conn.execute(
            """SELECT d.title, COUNT(e.id) as n_ents,
                      AVG(h.score) as avg_score
               FROM documents d
               LEFT JOIN entities e ON e.doc_id = d.id
               LEFT JOIN hypotheses h ON h.entity_id = e.id
               GROUP BY d.id
               ORDER BY n_ents DESC"""
        ).fetchall()
        if doc_rows:
            doc_df = pd.DataFrame([dict(r) for r in doc_rows])

            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=doc_df["title"], y=doc_df["n_ents"],
                name="Entitats", marker_color=BLUE,
                hovertemplate="<b>%{x}</b><br>Entitats: %{y}<extra></extra>",
            ))
            if doc_df["avg_score"].notna().any():
                fig.add_trace(go.Scatter(
                    x=doc_df["title"], y=doc_df["avg_score"],
                    name="Score mitjana", yaxis="y2",
                    mode="markers+lines",
                    marker=dict(color=AMBER, size=10),
                    hovertemplate="<b>%{x}</b><br>Score mitjana: %{y:.3f}<extra></extra>",
                ))
                fig.update_layout(
                    yaxis2=dict(title="Score mitjana", overlaying="y",
                                side="right", range=[0, 1],
                                gridcolor="#1E2329"),
                )
            fig.update_layout(
                xaxis_title="Document", yaxis_title="Nombre d'entitats",
                xaxis_tickangle=-25, bargap=0.3,
            )
            apply_plotly_theme(fig, 400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hi ha documents.")

        st.markdown("", unsafe_allow_html=True)

        # -- Scoring breakdown --
        st.markdown('<div class="section-title">Com es compon el score de les millors hipotesis?</div>',
                    unsafe_allow_html=True)
        st.markdown('<p class="section-desc">'
                    'Contribucio ponderada de cada senyal per a les 10 hipotesis amb score mes alt.'
                    '</p>', unsafe_allow_html=True)

        top_rows = conn.execute(
            """SELECT h.score, h.lidar_elevation, h.lidar_slope, h.lidar_anomaly,
                      e.name, e.entity_type, e.confidence, e.description,
                      e.lat, e.lon, e.lat_llm, e.lon_llm, e.geo_status, e.doc_id
               FROM hypotheses h
               JOIN entities e ON h.entity_id = e.id
               ORDER BY h.score DESC
               LIMIT 10"""
        ).fetchall()

        if top_rows:
            top_df = pd.DataFrame([dict(r) for r in top_rows])

            all_nd = conn.execute("SELECT name, doc_id FROM entities").fetchall()
            all_names_docs = [(r["name"].lower().strip(), r["doc_id"]) for r in all_nd]

            signals_df = compute_signal_breakdown(top_df, all_names_docs)
            signal_cols = [c for c in signals_df.columns if c != "name"]

            melted = signals_df.melt(id_vars="name", value_vars=signal_cols,
                                      var_name="Senyal", value_name="Valor raw")
            melted["Contribucio"] = melted.apply(
                lambda r: r["Valor raw"] * SIGNAL_TO_WEIGHT.get(r["Senyal"], 0),
                axis=1,
            )

            fig = px.bar(melted, x="name", y="Contribucio", color="Senyal",
                         color_discrete_sequence=COLOR_SEQ,
                         labels={"name": "", "Contribucio": "Contribucio al score"},
                         barmode="stack",
                         hover_data={"Valor raw": ":.2f", "Contribucio": ":.3f"})
            fig.update_layout(xaxis_tickangle=-25)
            apply_plotly_theme(fig, 420)
            st.plotly_chart(fig, use_container_width=True)

            # Radar
            st.markdown('<div class="section-title">Perfil de senyals de la millor hipotesi</div>',
                        unsafe_allow_html=True)

            best = signals_df.iloc[0]
            radar_vals = [best[c] for c in signal_cols]
            radar_vals.append(radar_vals[0])
            cats = signal_cols + [signal_cols[0]]

            fig_radar = go.Figure(go.Scatterpolar(
                r=radar_vals, theta=cats, fill="toself",
                fillcolor=f"rgba(33,150,243,0.15)",
                line=dict(color=BLUE, width=2),
                name=best["name"],
                hovertemplate="%{theta}: %{r:.2f}<extra></extra>",
            ))
            fig_radar.update_layout(
                polar=dict(
                    radialaxis=dict(visible=True, range=[0, 1],
                                    gridcolor="#2A2F35", linecolor="#2A2F35"),
                    angularaxis=dict(gridcolor="#2A2F35", linecolor="#2A2F35"),
                    bgcolor="rgba(0,0,0,0)",
                ),
            )
            apply_plotly_theme(fig_radar, 420)
            st.plotly_chart(fig_radar, use_container_width=True)
        else:
            st.info("No hi ha hipotesis per desglosar.")

    # ── TAB 3: Validacio ──────────────────────────────────────────────────
    with tab3:
        st.markdown('<p class="tab-intro">'
                    'Comparacio de les hipotesis generades amb els jaciments arqueologics '
                    'coneguts de Walker et al. 2023.'
                    '</p>', unsafe_allow_html=True)

        if validation:
            st.markdown('<div class="section-title">Metriques de validacio</div>',
                        unsafe_allow_html=True)

            vc1, vc2, vc3 = st.columns(3)
            with vc1:
                hr_cls = ("kpi-green" if validation["hit_rate"] > 0.2
                          else ("kpi-amber" if validation["hit_rate"] > 0.1 else "kpi-red"))
                st.markdown(
                    kpi_card("&#127919;", "Hit rate global",
                             f"{validation['hit_rate']:.1%}", hr_cls),
                    unsafe_allow_html=True)
            with vc2:
                st.markdown(
                    kpi_card("&#11088;", "Hit rate candidates",
                             f"{validation['cand_hits']}/{validation['cand_total']} "
                             f"({validation['cand_hit_rate']:.1%})", "kpi-blue"),
                    unsafe_allow_html=True)
            with vc3:
                st.markdown(
                    kpi_card("&#127760;", "Cobertura sitis coneguts",
                             f"{validation['coverage']:.1%}"),
                    unsafe_allow_html=True)

            st.markdown("", unsafe_allow_html=True)
            vc4, vc5 = st.columns(2)
            with vc4:
                st.markdown(
                    kpi_card("&#128207;", "Distancia mitjana (hits)",
                             f"{validation['avg_dist']:.1f} km"),
                    unsafe_allow_html=True)
            with vc5:
                st.markdown(
                    kpi_card("&#128207;", "Distancia mediana (hits)",
                             f"{validation['median_dist']:.1f} km"),
                    unsafe_allow_html=True)

            st.markdown("", unsafe_allow_html=True)

            # Top hits bar
            if validation["hits"]:
                st.markdown(
                    '<div class="section-title">'
                    'Quines hipotesis estan mes a prop de jaciments reals?'
                    '</div>', unsafe_allow_html=True)

                hits_sorted = sorted(validation["hits"],
                                     key=lambda h: h["nearest_dist_km"])[:10]
                hits_df = pd.DataFrame(hits_sorted)

                fig = px.bar(hits_df, y="name", x="nearest_dist_km",
                             orientation="h",
                             color="nearest_dist_km",
                             color_continuous_scale=[[0, GREEN], [0.5, AMBER], [1, RED]],
                             labels={"nearest_dist_km": "Distancia (km)", "name": ""},
                             hover_data={"nearest_type": True, "score": ":.3f"})
                fig.update_layout(yaxis=dict(autorange="reversed"))
                apply_plotly_theme(fig, 400)
                st.plotly_chart(fig, use_container_width=True)

            # Scatter score vs distance
            all_val = validation["hits"] + validation["misses"]
            if all_val:
                st.markdown(
                    '<div class="section-title">'
                    'Correlaciona el score amb la proximitat a jaciments reals?'
                    '</div>', unsafe_allow_html=True)

                val_df = pd.DataFrame(all_val)
                fig = px.scatter(val_df, x="score", y="nearest_dist_km",
                                 color="status",
                                 color_discrete_map={"candidate": GREEN,
                                                     "low_priority": GRAY},
                                 labels={"score": "Score",
                                         "nearest_dist_km": "Distancia (km)"},
                                 hover_data={"name": True, "nearest_type": True})
                fig.add_hline(y=50, line_dash="dash", line_color=AMBER,
                              annotation_text="Llindar 50 km",
                              annotation_font_color=AMBER)
                apply_plotly_theme(fig, 420)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hi ha dades de ground truth disponibles (Walker et al. 2023).")

    # ── TAB 4: Terreny ────────────────────────────────────────────────────
    with tab4:
        st.markdown('<p class="tab-intro">'
                    'Analisi topografic basat en dades SRTM: elevacions, pendents i '
                    'anomalies que podrien indicar estructures precolombines.'
                    '</p>', unsafe_allow_html=True)

        terrain_rows = conn.execute(
            """SELECT h.lidar_elevation, h.lidar_slope, h.lidar_anomaly,
                      h.score, e.name
               FROM hypotheses h
               JOIN entities e ON h.entity_id = e.id
               WHERE h.lidar_elevation IS NOT NULL"""
        ).fetchall()

        if terrain_rows:
            terrain_df = pd.DataFrame([dict(r) for r in terrain_rows])

            st.markdown(
                '<div class="section-title">'
                'Com es distribueixen les elevacions i pendents?'
                '</div>', unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            with col1:
                fig = px.histogram(terrain_df, x="lidar_elevation", nbins=20,
                                   color_discrete_sequence=[BLUE],
                                   labels={"lidar_elevation": "Elevacio (m)"})
                apply_plotly_theme(fig, 340)
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                fig = px.histogram(terrain_df, x="lidar_slope", nbins=20,
                                   color_discrete_sequence=[CYAN],
                                   labels={"lidar_slope": "Pendent (graus)"})
                apply_plotly_theme(fig, 340)
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("", unsafe_allow_html=True)
            st.markdown(
                '<div class="section-title">'
                'Quantes anomalies topografiques s\'han detectat?'
                '</div>', unsafe_allow_html=True)

            n_anom = int(terrain_df["lidar_anomaly"].sum())
            n_normal = len(terrain_df) - n_anom
            anom_df = pd.DataFrame({
                "Tipus": ["Anomalia", "Normal"],
                "Nombre": [n_anom, n_normal],
            })

            col1, col2 = st.columns(2)
            with col1:
                fig = px.pie(anom_df, names="Tipus", values="Nombre",
                             color="Tipus", hole=0.4,
                             color_discrete_map={"Anomalia": RED, "Normal": BLUE})
                apply_plotly_theme(fig, 340)
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                st.markdown(
                    '<div class="section-title">'
                    'Les anomalies tenen scores mes alts?'
                    '</div>', unsafe_allow_html=True)

                fig = px.scatter(
                    terrain_df, x="lidar_elevation", y="score",
                    color=terrain_df["lidar_anomaly"].map(
                        {1: "Anomalia", 0: "Normal"}),
                    color_discrete_map={"Anomalia": RED, "Normal": BLUE},
                    labels={"lidar_elevation": "Elevacio (m)", "score": "Score",
                            "color": ""},
                    hover_data=["name"])
                apply_plotly_theme(fig, 340)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No hi ha dades SRTM disponibles. "
                    "Executa `terrain_analyzer.py` per obtenir-les.")

    # ── TAB 5: Cobertura ──────────────────────────────────────────────────
    with tab5:
        st.markdown('<p class="tab-intro">'
                    'Mapes de densitat per visualitzar on es concentren les hipotesis '
                    'i comparar amb la distribucio de jaciments coneguts.'
                    '</p>', unsafe_allow_html=True)

        hyp_coords = conn.execute(
            "SELECT lat, lon, score FROM hypotheses WHERE lat IS NOT NULL"
        ).fetchall()

        if hyp_coords:
            heatmap_df = pd.DataFrame([dict(r) for r in hyp_coords])

            st.markdown(
                '<div class="section-title">'
                'On es concentren les hipotesis generades?'
                '</div>', unsafe_allow_html=True)

            fig = px.density_mapbox(
                heatmap_df, lat="lat", lon="lon",
                radius=25, zoom=4,
                mapbox_style="open-street-map",
                color_continuous_scale="YlOrRd",
            )
            fig.update_layout(
                height=520,
                margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig, use_container_width=True)

            gt_sites = _load_gt_sites()
            if gt_sites:
                st.markdown("", unsafe_allow_html=True)
                st.markdown(
                    '<div class="section-title">'
                    'On es concentren els jaciments coneguts (Walker 2023)?'
                    '</div>', unsafe_allow_html=True)

                gt_df = pd.DataFrame(gt_sites)
                fig2 = px.density_mapbox(
                    gt_df, lat="lat", lon="lon",
                    radius=25, zoom=4,
                    mapbox_style="open-street-map",
                    color_continuous_scale="Blues",
                )
                fig2.update_layout(
                    height=520,
                    margin=dict(l=0, r=0, t=10, b=0),
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No hi ha hipotesis amb coordenades.")

    # ── Footer ────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="footer">
        TFG Enginyeria de Dades — UAB 2026 — Alvaro Bello Marabe
    </div>
    """, unsafe_allow_html=True)


main()
