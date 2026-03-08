"""
Page 4 – Art Unit Explorer
Art unit statistics and examiner roster with difficulty scores.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from collections import defaultdict

from utils.auth import require_auth, sidebar_user
from services import uspto_api
from services.scoring import compute_examiner_score

require_auth()
sidebar_user()

st.title("🏛️ Art Unit Explorer")
st.caption("Enter a 4-digit art unit to see overall stats and an examiner-by-examiner breakdown.")

with st.form("au_form"):
    col1, col2 = st.columns([2, 1])
    with col1:
        art_unit = st.text_input("Art Unit", placeholder="e.g. 2143")
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        submitted = st.form_submit_button("Explore", use_container_width=True)

if not submitted or not art_unit.strip():
    st.stop()

art_unit = art_unit.strip()

with st.spinner(f"Fetching applications for art unit {art_unit}…"):
    apps = uspto_api.search_by_art_unit(art_unit)

if not apps:
    st.warning(f"No applications found for art unit {art_unit}.")
    st.stop()

# ── Overall art unit stats ────────────────────────────────────────────────────
au_stats = compute_examiner_score(apps)

st.markdown("---")
badge_html = (
    f'<span class="score-badge" style="background:{au_stats["color_hex"]}">'
    f'Art Unit {art_unit} — {au_stats["band"]} &nbsp; {au_stats["score"] or "N/A"}/100'
    f"</span>"
)
st.markdown(badge_html, unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Apps (sample)", au_stats["total"])
m2.metric("Allowance Rate", f"{au_stats['allowance_rate']} %" if au_stats["allowance_rate"] is not None else "N/A")
m3.metric("Avg Office Actions", au_stats["avg_oa"])
m4.metric("Avg Pendency (mo.)", au_stats["avg_pendency"])

# ── Per-examiner breakdown ────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Examiner Roster – Difficulty Breakdown")

examiner_apps: dict[str, list] = defaultdict(list)
for app in apps:
    ex = app.get("appExamNameText", "Unknown")
    examiner_apps[ex].append(app)

rows = []
for ex_name, ex_apps in examiner_apps.items():
    s = compute_examiner_score(ex_apps)
    rows.append({
        "Examiner":       ex_name,
        "Apps":           s["total"],
        "Patented":       s["patented"],
        "Abandoned":      s["abandoned"],
        "Allowance Rate": s["allowance_rate"],
        "Score":          s["score"],
        "Band":           s["band"],
        "_color":         s["color_hex"],
    })

df_ex = pd.DataFrame(rows).sort_values("Score", ascending=False)

# Colour-coded bar chart of examiner scores
if not df_ex.empty and df_ex["Score"].notna().any():
    fig_scores = px.bar(
        df_ex.dropna(subset=["Score"]),
        x="Examiner", y="Score",
        color="Band",
        color_discrete_map={
            "Easy (Green)":     "#2ecc71",
            "Moderate (Yellow)": "#f39c12",
            "Difficult (Red)":  "#e74c3c",
        },
        labels={"Score": "Difficulty Score (0–100)"},
        title="Examiner Scores within Art Unit",
    )
    fig_scores.update_layout(
        xaxis_tickangle=-45, margin=dict(t=40, b=120), height=380,
        legend_title_text="Difficulty Band",
    )
    st.plotly_chart(fig_scores, use_container_width=True)

# ── Score composition pie (art unit level) ───────────────────────────────────
band_counts = df_ex["Band"].value_counts().reset_index()
band_counts.columns = ["Band", "Count"]

col_pie, col_tbl = st.columns(2)
with col_pie:
    st.subheader("Score Distribution")
    color_map = {
        "Easy (Green)":     "#2ecc71",
        "Moderate (Yellow)": "#f39c12",
        "Difficult (Red)":  "#e74c3c",
    }
    fig_band = go.Figure(go.Pie(
        labels=band_counts["Band"],
        values=band_counts["Count"],
        marker_colors=[color_map.get(b, "#95a5a6") for b in band_counts["Band"]],
        hole=0.4,
    ))
    fig_band.update_layout(margin=dict(t=10, b=10), height=260)
    st.plotly_chart(fig_band, use_container_width=True)

with col_tbl:
    st.subheader("Examiner Table")
    display_cols = ["Examiner", "Apps", "Allowance Rate", "Score", "Band"]
    st.dataframe(
        df_ex[display_cols].reset_index(drop=True),
        use_container_width=True,
        height=280,
    )

st.caption(f"Data: USPTO PEDS – sample up to 200 most-recent applications in art unit {art_unit}.")
