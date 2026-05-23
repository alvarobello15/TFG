"""
TFG: Dashboard Principal
==========================
Mapa, filtres, agent IA i ranking d'hipotesis.
"""

import sqlite3
import json
import os
import re
from pathlib import Path

import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from ground_truth_validator import load_walker_sites, load_coomes_sites

DB_PATH = Path(__file__).resolve().parent.parent / "tfg.db"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

BLUE, GREEN, AMBER, RED, GRAY, CYAN, PURPLE = (
    "#2196F3", "#4CAF50", "#FF9800", "#F44336", "#9E9E9E", "#00BCD4", "#9C27B0")

TYPE_COLORS = {"settlement": GREEN, "route": AMBER, "region": BLUE,
               "mountain": PURPLE, "river": CYAN, "other": GRAY}

# ── Page CSS ──────────────────────────────────────────────────────────────────

st.markdown("""<style>
.kpi-row { display:flex; gap:.6rem; margin-bottom:.5rem; }
.kpi-card { flex:1; background:#1E2329; border:1px solid #2A2F35;
            border-radius:10px; padding:.7rem .8rem; text-align:center; }
.kpi-card .kpi-label { font-size:.62rem; color:#6B7280; text-transform:uppercase;
                        letter-spacing:.06em; margin-bottom:.15rem; }
.kpi-card .kpi-value { font-size:1.35rem; font-weight:700; color:#FAFAFA; }
.kpi-card .kpi-icon  { font-size:.9rem; margin-bottom:.1rem; }
.kpi-green .kpi-value { color:#4CAF50; }
.kpi-blue  .kpi-value { color:#2196F3; }
.legend-bar { display:flex; flex-wrap:wrap; gap:1rem; padding:.5rem .8rem;
              background:#1E2329; border:1px solid #2A2F35; border-radius:8px;
              font-size:.72rem; color:#B0BEC5; margin-top:.4rem; }
.legend-bar .legend-item { display:flex; align-items:center; gap:.3rem; }
.legend-dot { width:9px; height:9px; border-radius:50%; display:inline-block; }
.agent-filter-tags { margin-top:.3rem; }
.agent-tag { display:inline-block; background:#4CAF5018; color:#4CAF50;
             border:1px solid #4CAF5040; padding:2px 10px; border-radius:12px;
             font-size:.7rem; margin:2px; }
.agent-tag-none { display:inline-block; background:#2A2F35; color:#6B7280;
                  padding:2px 10px; border-radius:12px; font-size:.7rem; }
.sidebar-section { font-size:.72rem; font-weight:600; color:#9E9E9E;
                   text-transform:uppercase; letter-spacing:.05em;
                   margin-top:.7rem; margin-bottom:.25rem; }
</style>""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────────────

def kpi_card(icon, label, value, css=""):
    return (f'<div class="kpi-card {css}"><div class="kpi-icon">{icon}</div>'
            f'<div class="kpi-label">{label}</div><div class="kpi-value">{value}</div></div>')

def score_to_color(s):
    if s is None: return "gray"
    return "green" if s >= 0.6 else ("orange" if s >= 0.4 else "red")

def score_badge(s):
    if s is None: return '<span style="color:#9E9E9E;">N/A</span>'
    c = GREEN if s >= 0.6 else (AMBER if s >= 0.4 else RED)
    return f'<span style="color:{c};font-weight:700;">{s:.3f}</span>'

def type_badge(t):
    c = TYPE_COLORS.get(t, GRAY)
    return f'<span style="background:{c}22;color:{c};padding:2px 8px;border-radius:4px;font-size:.8em;">{t}</span>'

@st.cache_resource
def get_conn():
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def load_all(conn):
    rows = conn.execute(
        """SELECT e.id,e.name,e.entity_type,e.description,e.confidence,
                  e.lat,e.lon,e.geo_status,e.geo_name,d.title as doc_title,
                  h.score,h.status as hyp_status,
                  h.lidar_elevation,h.lidar_slope,h.lidar_anomaly
           FROM entities e JOIN documents d ON e.doc_id=d.id
           LEFT JOIN hypotheses h ON h.entity_id=e.id
           WHERE e.lat IS NOT NULL AND e.lon IS NOT NULL""").fetchall()
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

# ── Agent ─────────────────────────────────────────────────────────────────────

def get_client():
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH)
    k = os.environ.get("ANTHROPIC_API_KEY")
    if not k: return None
    from anthropic import Anthropic
    return Anthropic(api_key=k)

def build_ctx(conn):
    docs = [r["title"] for r in conn.execute("SELECT title FROM documents").fetchall()]
    tc = conn.execute("SELECT entity_type,COUNT(*)c FROM entities GROUP BY entity_type ORDER BY c DESC").fetchall()
    ne = conn.execute("SELECT COUNT(*)c FROM entities").fetchone()["c"]
    nh = conn.execute("SELECT COUNT(*)c FROM hypotheses").fetchone()["c"]
    nc = conn.execute("SELECT COUNT(*)c FROM hypotheses WHERE status='candidate'").fetchone()["c"]
    na = conn.execute("SELECT COUNT(*)c FROM hypotheses WHERE lidar_anomaly=1").fetchone()["c"]
    t5 = conn.execute("SELECT e.name,h.score,e.entity_type FROM hypotheses h JOIN entities e ON h.entity_id=e.id ORDER BY h.score DESC LIMIT 5").fetchall()
    return (f"DB: {len(docs)} docs ({', '.join(docs)}), {ne} entitats ({', '.join(f'{r[1]} {r[0]}' for r in tc)}), "
            f"{nh} hipotesis ({nc} candidates, {nh-nc} low_priority), {na} anomalies. "
            f"Top 5: {', '.join(f'{r[0]}({r[2]},{r[1]:.3f})' for r in t5)}. "
            f"Tipus: settlement,river,region,route,mountain,other. Confianca: high,medium,low.")

SYS = """Ets un assistent arqueologic expert en hipotesis de jaciments precolombins a l'Amazonia.
DADES: {ctx}
Respon en el mateix idioma que l'usuari. Retorna SEMPRE un JSON i un text:
```json
{{"action":"filter"|"query"|"explain"|"compare","filters":{{"entity_types":[],"min_score":null,"max_score":null,"documents":[],"confidence":[],"only_anomalies":false,"only_candidates":false,"name_search":null}},"response_text":"..."}}
```
Si demana "mostra tot", filters buit. Inclou dades concretes. NO inventis."""

def parse_resp(text):
    for pat in [r'```json\s*(\{.*?\})\s*```',
                r'(\{[^{}]*"action"[^{}]*"filters"[^{}]*\{[^{}]*\}[^{}]*"response_text"[^{}]*\})',
                r'(\{[\s\S]*?"action"[\s\S]*?"response_text"[\s\S]*?\})\s*(?:```|$)']:
        m = re.search(pat, text, re.DOTALL)
        if m:
            try: return json.loads(m.group(1))
            except json.JSONDecodeError: pass
    return {"action":"query","filters":{},"response_text":text.strip()}

def fmt_agent_filters(f):
    if not f: return '<span class="agent-tag-none">Sense filtres d\'agent</span>'
    tags = []
    for k in ["entity_types","documents","confidence"]:
        for v in (f.get(k) or []): tags.append(v)
    if f.get("min_score") is not None: tags.append(f"score>={f['min_score']}")
    if f.get("max_score") is not None: tags.append(f"score<={f['max_score']}")
    if f.get("only_anomalies"): tags.append("anomalies")
    if f.get("only_candidates"): tags.append("candidates")
    if f.get("name_search"): tags.append(f'"{f["name_search"]}"')
    return " ".join(f'<span class="agent-tag">{t}</span>' for t in tags) if tags else '<span class="agent-tag-none">Sense filtres</span>'

def apply_agent(df, f):
    if not f: return df
    m = pd.Series(True, index=df.index)
    if f.get("entity_types"): m &= df["entity_type"].isin(f["entity_types"])
    if f.get("min_score") is not None: m &= (df["score"]>=f["min_score"])|df["score"].isna()
    if f.get("max_score") is not None: m &= (df["score"]<=f["max_score"])|df["score"].isna()
    if f.get("documents"): m &= df["doc_title"].isin(f["documents"])
    if f.get("confidence"): m &= df["confidence"].isin(f["confidence"])
    if f.get("only_anomalies"): m &= df["lidar_anomaly"]==1
    if f.get("only_candidates"): m &= df["hyp_status"]=="candidate"
    if f.get("name_search"): m &= df["name"].str.contains(f["name_search"],case=False,na=False)
    return df[m]

# ── Map ───────────────────────────────────────────────────────────────────────

def build_map(df, sw, sa):
    center = [df["lat"].mean(), df["lon"].mean()] if not df.empty else [-5,-62]
    m = folium.Map(location=center, zoom_start=5, tiles="OpenStreetMap")
    if sw:
        for s in load_walker_sites():
            folium.CircleMarker([s["lat"],s["lon"]],radius=6,color="blue",fill=True,
                fill_color="blue",fill_opacity=.5,tooltip=f"Walker: {s['type']} ({s['lat']:.2f}, {s['lon']:.2f})").add_to(m)
    if sa:
        for s in load_coomes_sites():
            folium.CircleMarker([s["lat"],s["lon"]],radius=6,color="cyan",fill=True,
                fill_color="cyan",fill_opacity=.6,tooltip=f"Coomes: {s['name']}").add_to(m)
    for _,r in df.iterrows():
        c = score_to_color(r.get("score"))
        desc = (r.get("description") or "")[:200]
        gs = r.get("geo_status","")
        geo_html = ('<span style="color:#4CAF50;">&#128205; Gazetteer HGIS</span>' if gs == "gazetteer"
                    else '<span style="color:#FF9800;">&#128205; Estimacio LLM</span>' if gs == "llm_estimated"
                    else '<span style="color:#2196F3;">&#128205; Nominatim</span>' if gs == "found"
                    else '<span style="color:#9E9E9E;">&#128205; ?</span>')
        popup = (f'<div style="font-family:sans-serif;font-size:13px;max-width:280px;">'
                 f'<b style="font-size:1.05em;">{r["name"]}</b><br>{type_badge(r["entity_type"])}<br>'
                 f'<b>Score:</b> {score_badge(r.get("score"))}<br>'
                 f'{geo_html}<br>'
                 f'<b>Confianca:</b> {r["confidence"]}<br><b>Font:</b> {r["doc_title"]}<br>'
                 f'<i style="color:#9E9E9E;font-size:.85em;">{desc}</i></div>')
        folium.CircleMarker([r["lat"],r["lon"]],radius=8,color=c,fill=True,
            fill_color=c,fill_opacity=.7,popup=folium.Popup(popup,max_width=300),
            tooltip=r["name"]).add_to(m)
    return m

# ══════════════════════════════════════════════════════════════════════════════

conn = get_conn()
df_all = load_all(conn)

if df_all.empty:
    st.warning("No hi ha entitats geocodificades."); st.stop()

if "messages" not in st.session_state: st.session_state.messages = []
if "agent_filters" not in st.session_state: st.session_state.agent_filters = {}
client = get_client()

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""<div class="main-header">
<h1>Generacio i Validacio d'Hipotesis Arqueologiques</h1>
<div class="subtitle">Pipeline LLM + LiDAR per a la prospeccio a l'Amazonia — TFG Enginyeria de Dades, UAB 2026</div>
<div class="authors">Alvaro Bello Marabe &nbsp;|&nbsp; Tutora: Ana Oropesa</div>
</div>""", unsafe_allow_html=True)

st.markdown('<div class="page-title"><div class="pt-accent"></div><h2>Dashboard</h2></div>',
            unsafe_allow_html=True)

# ── Sidebar filters ──────────────────────────────────────────────────────────

with st.sidebar:
    all_types = sorted(df_all["entity_type"].dropna().unique())
    sel_types = st.pills("Tipus d'entitat", all_types, default=all_types,
                         selection_mode="multi", key="p_types")

    all_conf = sorted(df_all["confidence"].dropna().unique())
    sel_conf = st.pills("Confianca", all_conf, default=all_conf,
                        selection_mode="multi", key="p_conf")

    sel_status = st.pills("Status", ["Candidates","Low priority"],
                          default=["Candidates"], selection_mode="multi", key="p_status")

    all_docs = sorted(df_all["doc_title"].dropna().unique())
    sel_docs = st.pills("Documents", all_docs, default=all_docs,
                        selection_mode="multi", key="p_docs")

    smin = float(df_all["score"].min()) if df_all["score"].notna().any() else 0.0
    smax = float(df_all["score"].max()) if df_all["score"].notna().any() else 1.0
    sel_score = st.slider("Rang de score", smin, smax, (smin, smax), key="sl_score")

    st.markdown("---")
    st.markdown('<div class="sidebar-section">Ground Truth</div>', unsafe_allow_html=True)
    show_w = st.toggle("Walker et al. 2023", value=True, key="tgl_w")
    show_a = st.toggle("Coomes et al. 2021", value=True, key="tgl_a")

# ── Apply filters ─────────────────────────────────────────────────────────────

mask = pd.Series(True, index=df_all.index)
mask &= df_all["entity_type"].isin(sel_types) if sel_types else False
mask &= df_all["confidence"].isin(sel_conf) if sel_conf else False
mask &= df_all["doc_title"].isin(sel_docs) if sel_docs else False
smap = {"Candidates":"candidate","Low priority":"low_priority"}
if sel_status:
    mask &= df_all["hyp_status"].isin([smap[s] for s in sel_status])
else:
    mask &= False
if df_all["score"].notna().any():
    mask &= ((df_all["score"]>=sel_score[0])&(df_all["score"]<=sel_score[1]))|df_all["score"].isna()

filtered = df_all[mask]
if st.session_state.agent_filters:
    filtered = apply_agent(filtered, st.session_state.agent_filters)

with st.sidebar:
    st.markdown("---")
    nd = filtered["doc_title"].nunique() if not filtered.empty else 0
    st.markdown(f"**Mostrant {len(filtered)} / {len(df_all)} entitats**  \nde {nd} documents")

    # Geocoding source stats
    if "geo_status" in df_all.columns:
        n_gz = int((df_all["geo_status"] == "gazetteer").sum())
        n_llm = int((df_all["geo_status"] == "llm_estimated").sum())
        n_nom = int((df_all["geo_status"] == "found").sum())
        st.caption(f"Geo: {n_gz} gazetteer, {n_llm} LLM, {n_nom} Nominatim")

# ── KPIs ──────────────────────────────────────────────────────────────────────

dn = conn.execute("SELECT COUNT(*)c FROM documents").fetchone()["c"]
en = conn.execute("SELECT COUNT(*)c FROM entities").fetchone()["c"]
gn = conn.execute("SELECT COUNT(*)c FROM entities WHERE lat IS NOT NULL").fetchone()["c"]
cn = conn.execute("SELECT COUNT(*)c FROM hypotheses WHERE status='candidate'").fetchone()["c"]

st.markdown('<div class="kpi-row">'
    + kpi_card("&#128196;","Documents",dn)
    + kpi_card("&#127981;","Entitats",en)
    + kpi_card("&#127759;","Geocodificades",gn,"kpi-blue")
    + kpi_card("&#11088;","Candidates",cn,"kpi-green")
    + '</div>', unsafe_allow_html=True)

# ── Map ───────────────────────────────────────────────────────────────────────

st.markdown('<div class="section-title">Mapa d\'hipotesis</div>', unsafe_allow_html=True)
mp = build_map(filtered, show_w, show_a)
st_folium(mp, width=None, height=620)

st.markdown("""<div class="legend-bar">
<div class="legend-item"><span class="legend-dot" style="background:#2196F3;"></span> Walker 2023</div>
<div class="legend-item"><span class="legend-dot" style="background:#00BCD4;"></span> Coomes 2021</div>
<div class="legend-item"><span class="legend-dot" style="background:#4CAF50;"></span> Score &ge; 0.6</div>
<div class="legend-item"><span class="legend-dot" style="background:#FF9800;"></span> 0.4 &ndash; 0.6</div>
<div class="legend-item"><span class="legend-dot" style="background:#F44336;"></span> &lt; 0.4</div>
<div class="legend-item"><span class="legend-dot" style="background:#9E9E9E;"></span> Sense score</div>
</div>""", unsafe_allow_html=True)

# ── Agent ─────────────────────────────────────────────────────────────────────

st.markdown("", unsafe_allow_html=True)
st.markdown('<div class="section-title">Agent arqueologic</div>', unsafe_allow_html=True)

if client is None:
    st.info("Configura ANTHROPIC_API_KEY a .env per activar l'agent IA.")
else:
    sugs = ["Top 10 candidats","Nomes anomalies","Hipotesis de Carvajal",
            "Validacio ground truth","Mostra tot"]
    cols = st.columns(len(sugs))
    sug_click = None
    for i,s in enumerate(sugs):
        if cols[i].button(s, key=f"sug_{i}", use_container_width=True): sug_click = s

    st.markdown(f'<div class="agent-filter-tags">{fmt_agent_filters(st.session_state.agent_filters)}</div>',
                unsafe_allow_html=True)

    if st.button("Netejar filtres d'agent", key="clr"):
        st.session_state.agent_filters = {}
        st.session_state.messages = []
        st.rerun()

    for msg in st.session_state.messages:
        with st.chat_message("human" if msg["role"]=="user" else "assistant"):
            st.markdown(msg["content"])

    user_in = st.chat_input("Pregunta a l'agent sobre les hipotesis...")
    if sug_click: user_in = sug_click

    if user_in:
        st.session_state.messages.append({"role":"user","content":user_in})
        with st.chat_message("human"): st.markdown(user_in)

        ctx = build_ctx(conn)
        sys = SYS.format(ctx=ctx)
        hist = st.session_state.messages[-10:]
        api_msgs = [{"role":m["role"],"content":m["content"]} for m in hist]

        with st.chat_message("assistant"):
            with st.spinner("Pensant..."):
                try:
                    resp = client.messages.create(model="claude-haiku-4-5-20251001",
                        max_tokens=1024, system=sys, messages=api_msgs)
                    raw = resp.content[0].text
                except Exception as e:
                    raw = f"Error: {e}"
            parsed = parse_resp(raw)
            rtxt = parsed.get("response_text", raw)
            if parsed.get("action")=="filter" and "filters" in parsed:
                st.session_state.agent_filters = parsed["filters"]
            st.markdown(rtxt)

        st.session_state.messages.append({"role":"assistant","content":rtxt})
        st.rerun()

# ── Ranking ───────────────────────────────────────────────────────────────────

st.markdown("", unsafe_allow_html=True)
st.markdown('<div class="section-title">Ranking d\'hipotesis</div>', unsafe_allow_html=True)

dcols = ["name","entity_type","score","hyp_status","confidence","lat","lon","doc_title","description"]
avail = [c for c in dcols if c in filtered.columns]
if not filtered.empty:
    st.dataframe(filtered[avail].sort_values("score",ascending=False,na_position="last"),
                 use_container_width=True, height=400)
else:
    st.info("Cap resultat amb els filtres actuals.")

st.markdown('<div class="footer">TFG Enginyeria de Dades — UAB 2026 — Alvaro Bello Marabe</div>',
            unsafe_allow_html=True)
