"""
TFG: Entry point amb navegacio
================================
Configura st.navigation per controlar noms de pagines,
ordre i sidebar logo.

Executar: streamlit run app.py
"""

import streamlit as st

st.set_page_config(page_title="TFG - Hipotesis Arqueologiques", layout="wide",
                   page_icon="🏛️")

# ── Shared CSS (titols bonics, sidebar logo) ──────────────────────────────────

SHARED_CSS = """
<style>
/* ── Page title decorator ─────────────────── */
.page-title {
    display: flex; align-items: center; gap: .7rem;
    padding: .6rem 0 .5rem 0; margin-bottom: .3rem;
}
.page-title .pt-accent {
    width: 4px; height: 28px; border-radius: 2px;
    background: linear-gradient(180deg, #4CAF50, #2196F3);
    flex-shrink: 0;
}
.page-title h2 {
    font-size: 1.35rem; font-weight: 700; color: #FAFAFA;
    margin: 0; letter-spacing: .01em;
}
.page-title .pt-sub {
    font-size: .75rem; color: #6B7280; margin-left: auto;
}

/* ── Header ─────────────────────────────────── */
.main-header { text-align: center; padding: 1rem 0 .3rem 0; }
.main-header h1 {
    font-size: 1.55rem; font-weight: 700; color: #FAFAFA;
    margin-bottom: .1rem; letter-spacing: .02em;
}
.main-header .subtitle { font-size: .78rem; color: #9E9E9E; }
.main-header .authors  { font-size: .7rem; color: #6B7280; }

/* ── Section titles ─────────────────────────── */
.section-title {
    font-size: .95rem; font-weight: 600; color: #B0BEC5;
    margin-top: 1rem; margin-bottom: .25rem;
    padding-bottom: .3rem; border-bottom: 1px solid #2A2F35;
}

/* ── Footer ─────────────────────────────────── */
.footer {
    text-align: center; padding: 1.5rem 0 .8rem 0;
    font-size: .65rem; color: #4B5563;
    border-top: 1px solid #1E2329; margin-top: 1.5rem;
}

/* ── Sidebar logo ───────────────────────────── */
.sidebar-brand {
    text-align: center; padding: .3rem 0 .6rem 0;
    border-bottom: 1px solid #2A2F35; margin-bottom: .5rem;
}
.sidebar-brand .sb-icon { font-size: 1.6rem; }
.sidebar-brand .sb-title {
    font-size: .9rem; font-weight: 700; color: #4CAF50;
    letter-spacing: .03em;
}
.sidebar-brand .sb-sub {
    font-size: .6rem; color: #6B7280;
    letter-spacing: .04em; text-transform: uppercase;
}
</style>
"""

st.markdown(SHARED_CSS, unsafe_allow_html=True)

# ── Sidebar logo (above navigation) ──────────────────────────────────────────

st.sidebar.markdown("""
<div class="sidebar-brand">
    <div class="sb-icon">🏛️</div>
    <div class="sb-title">TFG Arqueologia</div>
    <div class="sb-sub">Pipeline LLM + LiDAR</div>
</div>
""", unsafe_allow_html=True)

# ── Navigation ────────────────────────────────────────────────────────────────

dashboard = st.Page("pages/dashboard.py", title="Dashboard", icon="📊", default=True)
analytics = st.Page("pages/analytics.py", title="Analytics", icon="📈")
flowchart = st.Page("pages/flowchart.py", title="Flowchart", icon="🔄")

pg = st.navigation([dashboard, analytics, flowchart])
pg.run()
