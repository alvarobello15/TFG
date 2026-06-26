"""
TFG: Flowchart — Diagrama i demo interactiva del pipeline.
"""

import sqlite3, math, re
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium

DB_PATH = Path(__file__).resolve().parent.parent / "tfg.db"

BLUE,GREEN,AMBER,RED,GRAY,CYAN,PURPLE = "#2196F3","#4CAF50","#FF9800","#F44336","#9E9E9E","#00BCD4","#9C27B0"

WEIGHTS = {"confidence":.14,"entity_type":.11,"geo_quality":.14,"description":.07,
           "cross_ref":.14,"river_prox":.10,"elevation_anomaly":.15,"terrain_suitability":.15}
SIG_LABELS = ["Confianca LLM","Tipus entitat","Qualitat geo","Descripcio",
              "Cross-reference","Proximitat rius","Anomalia terreny","Aptitud terreny"]
SIG2W = dict(zip(SIG_LABELS, WEIGHTS.values()))
RIVERS = [("Amazonas",-3.13,-60.02),("Napo",-1.07,-75.56),("Maranon",-4.45,-77.50),
          ("Ucayali",-8.38,-74.53),("Madeira",-3.32,-58.95),("Tapajos",-2.40,-54.72),
          ("Beni",-14.82,-67.53),("Madre de Dios",-12.59,-69.18),("Guapore",-12.68,-63.42),
          ("Mamor",-10.15,-65.37),("Itenez",-12.50,-64.07),("Negro",-3.07,-60.35),
          ("Putumayo",-1.50,-73.00),("Xingu",-3.20,-52.20)]
TYPE_COLORS = {"settlement":GREEN,"route":AMBER,"region":BLUE,"mountain":PURPLE,"river":CYAN,"other":GRAY}

st.markdown("""<style>
.pipeline-diagram{display:flex;flex-direction:column;align-items:center;gap:0;padding:.8rem 0}
.pipeline-step{background:#1E2329;border:1px solid #2A2F35;border-radius:12px;
  padding:.75rem 1.3rem;width:520px;display:flex;align-items:center;gap:.8rem;cursor:pointer;transition:border-color .2s}
.pipeline-step:hover,.pipeline-step.active{border-color:#4CAF50;background:#1E2329E0}
.pipeline-step .step-icon{font-size:1.4rem;flex-shrink:0}
.pipeline-step .step-content{flex:1}
.pipeline-step .step-name{font-weight:700;color:#FAFAFA;font-size:.88rem}
.pipeline-step .step-file{font-size:.65rem;color:#6B7280;font-family:monospace}
.pipeline-step .step-desc{font-size:.75rem;color:#9E9E9E;margin-top:.1rem}
.pipeline-arrow{color:#2A2F35;font-size:1.1rem;line-height:1;margin:1px 0}
.manuscript{background:#2C2416;border:1px solid #5C4A2A;border-radius:8px;
  padding:1rem 1.3rem;font-family:'Georgia','Times New Roman',serif;
  color:#D4C5A0;font-size:.85rem;line-height:1.7;max-height:240px;overflow-y:auto;
  box-shadow:inset 0 0 30px rgba(0,0,0,.3)}
.json-box{background:#0D1117;border:1px solid #21262D;border-radius:8px;
  padding:.8rem;font-family:'Consolas','Monaco',monospace;font-size:.75rem;
  line-height:1.5;color:#C9D1D9;overflow-x:auto;max-height:280px;overflow-y:auto}
.json-box .jk{color:#79C0FF} .json-box .js{color:#A5D6FF}
.json-box .jn{color:#FFA657} .json-box .jh{background:#388E3C33;display:inline}
.info-card{background:#1E2329;border:1px solid #2A2F35;border-radius:10px;padding:.7rem .8rem;text-align:center}
.info-card .ic-label{font-size:.65rem;color:#9E9E9E;text-transform:uppercase;letter-spacing:.05em;margin-bottom:.15rem}
.info-card .ic-value{font-size:1.2rem;font-weight:700;color:#FAFAFA}
.ic-green .ic-value{color:#4CAF50} .ic-blue .ic-value{color:#2196F3}
.ic-amber .ic-value{color:#FF9800} .ic-red .ic-value{color:#F44336}
.step-result{background:#1E2329;border:1px solid #2A2F35;border-radius:8px;
  padding:.7rem .9rem;font-size:.8rem;color:#B0BEC5;margin:.4rem 0}
.step-result strong{color:#FAFAFA}
.tech-grid{display:flex;flex-wrap:wrap;gap:.7rem;justify-content:center;margin:.8rem 0}
.tech-card{background:#1E2329;border:1px solid #2A2F35;border-radius:10px;
  padding:.6rem .8rem;width:180px;text-align:center}
.tech-card .tech-icon{font-size:1.3rem;margin-bottom:.2rem}
.tech-card .tech-name{font-weight:700;color:#FAFAFA;font-size:.82rem}
.tech-card .tech-role{font-size:.68rem;color:#6B7280;margin-top:.15rem}
</style>""", unsafe_allow_html=True)

@st.cache_resource
def get_conn():
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False); c.row_factory = sqlite3.Row; return c

def hav(a1,o1,a2,o2):
    R=6371;r=math.radians
    ra1,ro1,ra2,ro2=r(a1),r(o1),r(a2),r(o2)
    da,do=ra2-ra1,ro2-ro1
    a=math.sin(da/2)**2+math.cos(ra1)*math.cos(ra2)*math.sin(do/2)**2
    return R*2*math.asin(math.sqrt(a))

def min_river(lat,lon): return min(hav(lat,lon,rl,rn) for _,rl,rn in RIVERS)

def _sc(c): return {"high":1,"medium":.6,"low":.2}.get(c,.1)
def _st(t): return {"settlement":1,"route":.7,"region":.5,"mountain":.4,"river":.3,"other":.2}.get(t,.2)
def _sg(r):
    gs=r.get("geo_status")
    if gs=="found":
        s=.6
        if r.get("lat_llm") and r.get("lon_llm") and r.get("lat") and r.get("lon"):
            d=hav(r["lat_llm"],r["lon_llm"],r["lat"],r["lon"])
            s=1 if d<50 else(.8 if d<200 else .5)
        return s
    return .5 if gs=="llm_estimated" else 0
def _sd(d):
    l=len(d or "")
    return 1 if l>200 else(.7 if l>100 else(.4 if l>30 else(.2 if l>0 else 0)))
def _sx(name,nd):
    n=len(set(did for nm,did in nd if nm==name.lower().strip()))
    return 1 if n>=3 else(.7 if n==2 else 0)
def _sr(lat,lon):
    d=min_river(lat,lon)
    return 1 if d<20 else(.8 if d<50 else(.5 if d<150 else(.2 if d<500 else 0)))
def _sa(a): return 1 if a==1 else 0 if a is not None else 0
def _ss(sl,el):
    if sl is None or el is None: return 0
    ss=1 if sl<2 else(.8 if sl<5 else(.4 if sl<10 else .1))
    es=1 if 50<=el<=500 else(.6 if 20<=el<50 or 500<el<=1000 else(.3 if el<20 else .2))
    return ss*.6+es*.4

def signals(r,nd):
    return {"Confianca LLM":_sc(r.get("confidence")),"Tipus entitat":_st(r.get("entity_type")),
            "Qualitat geo":_sg(r),"Descripcio":_sd(r.get("description")),
            "Cross-reference":_sx(r["name"],nd),"Proximitat rius":_sr(r["lat"],r["lon"]),
            "Anomalia terreny":_sa(r.get("lidar_anomaly")),"Aptitud terreny":_ss(r.get("lidar_slope"),r.get("lidar_elevation"))}

def gt_sites():
    import sys; sys.path.insert(0,str(DB_PATH.parent))
    try:
        from ground_truth_validator import load_walker_sites; return load_walker_sites()
    except: return []

def ic(label,val,css=""): return f'<div class="info-card {css}"><div class="ic-label">{label}</div><div class="ic-value">{val}</div></div>'

def jhl(obj,hl=None):
    hl=hl or set(); lines=["{"]
    for i,(k,v) in enumerate(obj.items()):
        cm="," if i<len(obj)-1 else ""
        vh=f'<span class="js">"{v}"</span>' if isinstance(v,str) else(f'<span class="jn">{v}</span>' if isinstance(v,(int,float)) else '<span class="jn">null</span>')
        kh=f'<span class="jk">"{k}"</span>'
        ln=f'  {kh}: {vh}{cm}'
        lines.append(f'<span class="jh">{ln}</span>' if k in hl else ln)
    lines.append("}"); return "\n".join(lines)

def tbadge(t):
    c=TYPE_COLORS.get(t,GRAY)
    return f'<span style="background:{c}22;color:{c};padding:2px 8px;border-radius:4px;font-size:.78rem;">{t}</span>'

conn = get_conn()

st.markdown("""<div class="main-header">
<h1>Generacio i Validacio d'Hipotesis Arqueologiques</h1>
<div class="subtitle">Pipeline LLM + LiDAR per a la prospeccio a l'Amazonia — TFG Enginyeria de Dades, UAB 2026</div>
<div class="authors">Alvaro Bello Marabe &nbsp;|&nbsp; Tutora: Ana Oropesa</div>
</div>""", unsafe_allow_html=True)

st.markdown('<div class="page-title"><div class="pt-accent"></div><h2>Flowchart</h2></div>',
            unsafe_allow_html=True)

if not DB_PATH.exists():
    st.error("Base de dades no trobada."); st.stop()

st.markdown('<div class="section-title">Arquitectura del pipeline</div>', unsafe_allow_html=True)
st.caption("Cada etapa transforma les dades. Selecciona un pas a sota per veure el detall.")

STEPS = [
    ("&#128196;","Textos Historics","corpus_loader.py","Carrega documents historics (PDF/TXT) del corpus amazonic"),
    ("&#129529;","Neteja OCR + Web","text_cleaner.py","Elimina artefactes OCR, capcaleres i soroll"),
    ("&#129302;","Extraccio LLM","entity_extractor.py","Claude Haiku extreu entitats amb coordenades estimades"),
    ("&#128506;","Geocodificacio","geocoder.py","Coordenades LLM + fallback Nominatim"),
    ("&#128202;","Scoring d'Hipotesis","hypothesis_scorer.py","8 senyals ponderades generen un score 0-1"),
    ("&#127956;","Analisi Topografic","terrain_analyzer.py","Elevacio, pendent i anomalies SRTM NASA"),
    ("&#9989;","Validacio Ground Truth","ground_truth_validator.py","Comparacio amb Walker et al. 2023"),
    ("&#128506;","Visualitzacio","app.py + Streamlit","Dashboard interactiu amb mapa i agent IA"),
]

dhtml = '<div class="pipeline-diagram">'
for i,(ico,nm,fp,desc) in enumerate(STEPS):
    dhtml += (f'<div class="pipeline-step"><div class="step-icon">{ico}</div>'
              f'<div class="step-content"><div class="step-name">{nm}</div>'
              f'<div class="step-file">{fp}</div>'
              f'<div class="step-desc">{desc}</div></div></div>')
    if i < len(STEPS)-1: dhtml += '<div class="pipeline-arrow">&#9660;</div>'
dhtml += '</div>'
st.markdown(dhtml, unsafe_allow_html=True)

st.markdown("", unsafe_allow_html=True)
st.markdown('<div class="section-title">Exemple real pas a pas</div>', unsafe_allow_html=True)
st.caption("Selecciona una entitat i navega pels passos per veure com el pipeline la transforma.")

# Pick good examples: entities with context, high score, terrain data
ex_rows = conn.execute(
    """SELECT h.score,h.status,h.lidar_elevation,h.lidar_slope,h.lidar_anomaly,
              e.id as eid,e.name,e.entity_type,e.confidence,e.description,e.context,
              e.lat,e.lon,e.lat_llm,e.lon_llm,e.geo_status,e.doc_id,
              d.title as doc_title, d.content as doc_content
       FROM hypotheses h JOIN entities e ON h.entity_id=e.id JOIN documents d ON e.doc_id=d.id
       WHERE h.score IS NOT NULL AND e.context IS NOT NULL AND LENGTH(e.context)>20
         AND h.lidar_elevation IS NOT NULL
       ORDER BY h.score DESC LIMIT 30""").fetchall()

if not ex_rows:
    st.info("No hi ha entitats amb dades completes per mostrar exemples."); st.stop()

exdata = [dict(r) for r in ex_rows]

# Select diverse examples
wanted = {"settlement","river","region"}
picks = []
for e in exdata:
    if e["entity_type"] in wanted and e["entity_type"] not in {p["entity_type"] for p in picks}:
        picks.append(e)
    if len(picks) >= 3: break
for e in exdata:
    if len(picks) >= 5: break
    if e not in picks: picks.append(e)

labels = [f"{e['name']}  ({e['entity_type']}, score {e['score']:.3f})" for e in picks]
sel = st.selectbox("Entitat d'exemple", range(len(picks)), format_func=lambda i: labels[i])
ent = picks[sel]

# Cross-ref data
all_nd = [(r["name"].lower().strip(),r["doc_id"]) for r in conn.execute("SELECT name,doc_id FROM entities").fetchall()]

t1,t2,t3,t4,t5,t6,t7 = st.tabs([
    "Text original", "Neteja", "Extraccio LLM",
    "Geocodificacio", "Scoring", "Terreny SRTM", "Validacio + Mapa"
])

with t1:
    doc = ent["doc_content"] or ""
    idx = doc.lower().find(ent["name"].lower())
    if idx >= 0:
        s, e2 = max(0,idx-300), min(len(doc),idx+400)
        frag = doc[s:e2].strip()
        hl = re.sub(re.escape(ent["name"]),
                    f'<b style="color:#4CAF50;text-decoration:underline;">{ent["name"]}</b>',
                    frag, count=1, flags=re.IGNORECASE)
    else:
        hl = ent["context"] or ""

    st.markdown(f'<div class="manuscript"><div style="font-size:.65rem;color:#8B7355;margin-bottom:.4rem;">'
                f'Font: {ent["doc_title"]}</div>{hl}</div>', unsafe_allow_html=True)

with t2:
    st.markdown('<div class="step-result">'
                '<strong>text_cleaner.py</strong> aplica: eliminacio de capcaleres/peus repetits, '
                'correccio d\'artefactes OCR (caracters trencats, espais extranys), '
                'normalitzacio Unicode i eliminacio de metadata web. '
                'El text mostrat al pas anterior ja es el resultat net.</div>', unsafe_allow_html=True)

    # Show stats
    raw_len = conn.execute("SELECT char_count FROM documents WHERE title=?", (ent["doc_title"],)).fetchone()
    if raw_len:
        clean_len = len(ent["doc_content"] or "")
        st.markdown(f'<div class="step-result">Document <strong>{ent["doc_title"]}</strong>: '
                    f'{raw_len["char_count"]:,} caracters finals despres de neteja.</div>', unsafe_allow_html=True)

with t3:
    st.caption("Claude Haiku analitza cada chunk de text i retorna un JSON estructurat per entitat.")

    jobj = {"name":ent["name"],"entity_type":ent["entity_type"],
            "description":(ent["description"] or "")[:200],
            "context":(ent["context"] or "")[:150],
            "confidence":ent["confidence"],"lat":ent["lat_llm"],"lon":ent["lon_llm"]}
    jh = jhl(jobj, {"name","entity_type","lat","lon","confidence"})
    st.markdown(f'<div class="json-box"><pre>{jh}</pre></div>', unsafe_allow_html=True)

    # Entity table
    geo_lbl = "LLM estimat" if ent["geo_status"]=="llm_estimated" else("Nominatim" if ent["geo_status"]=="found" else(ent["geo_status"] or "?"))
    st.markdown(f'<div class="step-result"><table style="width:100%;border-collapse:collapse;">'
                f'<tr><td style="padding:3px 8px;color:#9E9E9E;">Nom</td><td style="padding:3px 8px;"><strong>{ent["name"]}</strong></td></tr>'
                f'<tr><td style="padding:3px 8px;color:#9E9E9E;">Tipus</td><td style="padding:3px 8px;">{tbadge(ent["entity_type"])}</td></tr>'
                f'<tr><td style="padding:3px 8px;color:#9E9E9E;">Coordenades</td><td style="padding:3px 8px;">{ent["lat"]:.4f}, {ent["lon"]:.4f}</td></tr>'
                f'<tr><td style="padding:3px 8px;color:#9E9E9E;">Geocodificacio</td><td style="padding:3px 8px;">{geo_lbl}</td></tr>'
                f'<tr><td style="padding:3px 8px;color:#9E9E9E;">Confianca</td><td style="padding:3px 8px;">{ent["confidence"]}</td></tr>'
                f'</table></div>', unsafe_allow_html=True)

with t4:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown(ic("Coordenades LLM", f'{ent["lat_llm"]:.4f}, {ent["lon_llm"]:.4f}' if ent["lat_llm"] else "N/A", "ic-amber"), unsafe_allow_html=True)
    with c2:
        st.markdown(ic("Coordenades finals", f'{ent["lat"]:.4f}, {ent["lon"]:.4f}', "ic-green"), unsafe_allow_html=True)

    if ent["lat_llm"] and ent["lat"]:
        d = hav(ent["lat_llm"],ent["lon_llm"],ent["lat"],ent["lon"])
        st.markdown(f'<div class="step-result">Distancia LLM vs final: <strong>{d:.1f} km</strong>. '
                    f'Metode: <strong>{geo_lbl}</strong>.</div>', unsafe_allow_html=True)
    st.markdown('<div class="step-result">El pipeline usa les coordenades del LLM directament. '
                'Si el LLM no en proporciona, es fa fallback a Nominatim/OpenStreetMap.</div>', unsafe_allow_html=True)

with t5:
    st.caption("8 senyals ponderades determinen el score final de cada hipotesi.")

    sigs = signals(ent, all_nd)
    wted = {k: v * SIG2W[k] for k,v in sigs.items()}
    total = sum(wted.values())

    c1,c2 = st.columns([3,2])
    with c1:
        sn = list(sigs.keys())
        fig = go.Figure(go.Bar(
            y=sn, x=[wted[k] for k in sn], orientation="h",
            marker_color=[BLUE,GREEN,AMBER,GRAY,PURPLE,CYAN,RED,"#78909C"],
            customdata=[sigs[k] for k in sn],
            hovertemplate="%{y}<br>Raw: %{customdata:.2f}<br>Ponderat: %{x:.3f}<extra></extra>"))
        fig.update_layout(plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#B0BEC5",size=11),margin=dict(l=130,r=20,t=10,b=30),
            height=300,xaxis=dict(gridcolor="#1E2329",title="Contribucio"),
            yaxis=dict(gridcolor="#1E2329",autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        vs = list(sigs.values())+[list(sigs.values())[0]]
        cs = sn+[sn[0]]
        fig_r = go.Figure(go.Scatterpolar(r=vs,theta=cs,fill="toself",
            fillcolor="rgba(33,150,243,0.15)",line=dict(color=BLUE,width=2)))
        fig_r.update_layout(polar=dict(radialaxis=dict(visible=True,range=[0,1],gridcolor="#2A2F35"),
            angularaxis=dict(gridcolor="#2A2F35"),bgcolor="rgba(0,0,0,0)"),
            plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#B0BEC5",size=10),margin=dict(l=40,r=40,t=20,b=20),height=300,showlegend=False)
        st.plotly_chart(fig_r, use_container_width=True)

    sc = GREEN if total>=.6 else(AMBER if total>=.4 else RED)
    st.markdown(f'<div class="step-result" style="text-align:center;">'
                f'Score final: <span style="color:{sc};font-size:1.3rem;font-weight:700;">{total:.3f}</span> '
                f'(DB: <span style="color:{sc};font-weight:700;">{ent["score"]:.3f}</span>) '
                f'&mdash; Status: <strong>{ent["status"]}</strong></div>', unsafe_allow_html=True)

    # Signal detail table
    st.markdown('<div class="step-result"><table style="width:100%;border-collapse:collapse;">'
                '<tr><th style="text-align:left;padding:3px 8px;color:#6B7280;font-size:.7rem;">Senyal</th>'
                '<th style="text-align:right;padding:3px 8px;color:#6B7280;font-size:.7rem;">Raw</th>'
                '<th style="text-align:right;padding:3px 8px;color:#6B7280;font-size:.7rem;">Pes</th>'
                '<th style="text-align:right;padding:3px 8px;color:#6B7280;font-size:.7rem;">Contribucio</th></tr>'
                + "".join(f'<tr><td style="padding:3px 8px;color:#B0BEC5;font-size:.78rem;">{k}</td>'
                          f'<td style="text-align:right;padding:3px 8px;color:#FAFAFA;">{sigs[k]:.2f}</td>'
                          f'<td style="text-align:right;padding:3px 8px;color:#6B7280;">{SIG2W[k]:.2f}</td>'
                          f'<td style="text-align:right;padding:3px 8px;color:#4CAF50;font-weight:600;">{wted[k]:.3f}</td></tr>'
                          for k in sn)
                + '</table></div>', unsafe_allow_html=True)

with t6:
    el,sl,an = ent.get("lidar_elevation"),ent.get("lidar_slope"),ent.get("lidar_anomaly")
    if el is not None:
        c1,c2,c3 = st.columns(3)
        with c1: st.markdown(ic("Elevacio",f"{el:.0f} m","ic-blue"), unsafe_allow_html=True)
        with c2: st.markdown(ic("Pendent",f"{sl:.2f}&deg;" if sl else "N/A"), unsafe_allow_html=True)
        with c3:
            atxt = "Anomalia detectada" if an==1 else "Sense anomalia"
            st.markdown(ic("Anomalia",atxt,"ic-green" if an==1 else ""), unsafe_allow_html=True)

        st.markdown(f'<div class="step-result">'
                    f'El <strong>terrain_analyzer.py</strong> consulta dades SRTM NASA a 30m de resolucio. '
                    f'Genera un anell de {12} punts a 1.5 km del centre i compara l\'elevacio central amb la mitjana. '
                    f'Si el punt esta &gt;2m per sobre, es marca com a <strong>anomalia topografica</strong> '
                    f'(possible plataforma artificial).</div>', unsafe_allow_html=True)
    else:
        st.info("No hi ha dades SRTM per a aquesta entitat.")

with t7:
    gts = gt_sites()
    if gts and ent["lat"]:
        bd,bs = float("inf"),None
        for s in gts:
            d = hav(ent["lat"],ent["lon"],s["lat"],s["lon"])
            if d<bd: bd,bs=d,s
        hit = bd<=50
        hc = GREEN if hit else RED
        ht = "HIT" if hit else "MISS"
        st.markdown(f'<div class="step-result">Jaciment mes proper: <strong>{bs["type"]}</strong> a '
                    f'<span style="color:{hc};font-weight:700;">{bd:.1f} km</span> &mdash; '
                    f'<span style="color:{hc};font-weight:700;">{ht}</span> (llindar: 50 km)</div>',
                    unsafe_allow_html=True)
    else:
        st.info("Ground truth no disponible.")
        bs = None

    # Mini map
    if ent["lat"]:
        mp = folium.Map(location=[ent["lat"],ent["lon"]], zoom_start=7, tiles="OpenStreetMap")
        sc2 = GREEN if ent["score"]>=.6 else(AMBER if ent["score"]>=.4 else RED)
        folium.CircleMarker([ent["lat"],ent["lon"]],radius=10,color=sc2.replace("#",""),
            fill=True,fill_color=sc2.replace("#",""),fill_opacity=.7,
            tooltip=ent["name"]).add_to(mp)
        if bs:
            folium.CircleMarker([bs["lat"],bs["lon"]],radius=7,color="blue",fill=True,
                fill_color="blue",fill_opacity=.5,tooltip=f"GT: {bs['type']}").add_to(mp)
            folium.PolyLine([[ent["lat"],ent["lon"]],[bs["lat"],bs["lon"]]],
                color="#9E9E9E",weight=1,dash_array="5").add_to(mp)
        st_folium(mp, width=None, height=400)

st.markdown("", unsafe_allow_html=True)
st.markdown('<div class="section-title">Estadistiques del pipeline</div>', unsafe_allow_html=True)

nd = conn.execute("SELECT COUNT(*)c FROM documents").fetchone()["c"]
ne = conn.execute("SELECT COUNT(*)c FROM entities").fetchone()["c"]
ng = conn.execute("SELECT COUNT(*)c FROM entities WHERE lat IS NOT NULL").fetchone()["c"]
nh = conn.execute("SELECT COUNT(*)c FROM hypotheses").fetchone()["c"]
nc = conn.execute("SELECT COUNT(*)c FROM hypotheses WHERE status='candidate'").fetchone()["c"]

fig_f = go.Figure(go.Funnel(
    y=["Documents","Entitats","Geocodificades","Hipotesis","Candidates"],
    x=[nd,ne,ng,nh,nc],
    marker=dict(color=[BLUE,CYAN,AMBER,GREEN,"#4CAF50"]),
    textinfo="value+percent initial",textfont=dict(color="#FAFAFA")))
fig_f.update_layout(plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#B0BEC5"),margin=dict(l=20,r=20,t=20,b=20),height=300)
st.plotly_chart(fig_f, use_container_width=True)

c1,c2,c3 = st.columns(3)
with c1: st.markdown(ic("Model LLM","Claude Haiku 4.5","ic-green"),unsafe_allow_html=True)
with c2: st.markdown(ic("Dades terreny","SRTM NASA 30m","ic-blue"),unsafe_allow_html=True)
with c3: st.markdown(ic("Ground truth","Walker et al. 2023","ic-amber"),unsafe_allow_html=True)

st.markdown("", unsafe_allow_html=True)
st.markdown('<div class="section-title">Tecnologies</div>', unsafe_allow_html=True)

techs = [("&#128013;","Python 3","Llenguatge principal"),("&#128202;","Streamlit","Dashboard interactiu"),
         ("&#128451;","SQLite","Base de dades local"),("&#128506;","Folium","Mapes Leaflet.js"),
         ("&#129302;","Claude Haiku","LLM Anthropic"),("&#127956;","SRTM NASA","Elevacio global 30m"),
         ("&#127760;","Nominatim","Geocodificacio OSM"),("&#128200;","Plotly","Grafics interactius")]

thtml = '<div class="tech-grid">'
for ico,nm,rl in techs:
    thtml += f'<div class="tech-card"><div class="tech-icon">{ico}</div><div class="tech-name">{nm}</div><div class="tech-role">{rl}</div></div>'
thtml += '</div>'
st.markdown(thtml, unsafe_allow_html=True)

st.markdown('<div class="footer">TFG Enginyeria de Dades — UAB 2026 — Alvaro Bello Marabe</div>',
            unsafe_allow_html=True)
