"""
Page 1 – Examiner Search
Produces an examiner profile card with Green/Yellow/Red difficulty scoring,
prosecution stats, rejection-type breakdown, and recent applications table.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from utils.auth import require_auth, sidebar_user
from services import uspto_api, patentsview_api
from services.scoring import compute_examiner_score

require_auth()
sidebar_user()

st.title("🔍 Examiner Search")
st.caption("Search by examiner name to view their difficulty profile and prosecution statistics.")

# ── Search form ───────────────────────────────────────────────────────────────
with st.form("examiner_form"):
    col1, col2 = st.columns([3, 1])
    with col1:
        name_input = st.text_input(
            "Examiner name (last name, or 'Last, First')",
            placeholder="e.g. Smith  or  Smith, John",
        )
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        submitted = st.form_submit_button("Search", use_container_width=True)

if not submitted or not name_input.strip():
    st.stop()

examiner_name = name_input.strip()

# ── Fetch data ────────────────────────────────────────────────────────────────
with st.spinner(f"Fetching applications for examiner '{examiner_name}'…"):
    apps = uspto_api.search_by_examiner(examiner_name)

if not apps:
    st.warning(
        f"No applications found for examiner '{examiner_name}'.  "
        "Try a last-name-only search, or check the spelling."
    )
    st.stop()

# ── Compute score ─────────────────────────────────────────────────────────────
stats = compute_examiner_score(apps)

# Infer examiner's art unit from most common value in results
art_units = [a.get("appGroupArtUnitNumber", "") for a in apps if a.get("appGroupArtUnitNumber")]
art_unit = max(set(art_units), key=art_units.count) if art_units else "N/A"

# ── Score badge ───────────────────────────────────────────────────────────────
badge_html = (
    f'<span class="score-badge" style="background:{stats["color_hex"]}">'
    f'{stats["band"]} &nbsp; {stats["score"] or "N/A"}/100'
    f"</span>"
)

st.markdown("---")
col_name, col_badge = st.columns([3, 2])
with col_name:
    st.markdown(f"### Examiner: {examiner_name}")
    st.markdown(f"**Art Unit:** {art_unit}")
with col_badge:
    st.markdown(badge_html, unsafe_allow_html=True)

# ── Key metrics ───────────────────────────────────────────────────────────────
st.markdown("---")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Applications (sample)", stats["total"])
m2.metric("Allowance Rate", f"{stats['allowance_rate']} %" if stats['allowance_rate'] is not None else "N/A")
m3.metric("Avg Office Actions", stats["avg_oa"] if stats["avg_oa"] is not None else "N/A")
m4.metric("Avg Pendency (mo.)", stats["avg_pendency"] if stats["avg_pendency"] is not None else "N/A")
m5.metric("RCE Rate", f"{stats['rce_rate']} %" if stats['rce_rate'] is not None else "N/A")

# ── Outcome donut chart ───────────────────────────────────────────────────────
st.markdown("---")
col_donut, col_trend = st.columns(2)

with col_donut:
    st.subheader("Application Outcomes")
    fig_donut = go.Figure(go.Pie(
        labels=["Patented", "Abandoned", "Pending"],
        values=[stats["patented"], stats["abandoned"], stats["pending"]],
        hole=0.45,
        marker_colors=["#2ecc71", "#e74c3c", "#95a5a6"],
    ))
    fig_donut.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=280)
    st.plotly_chart(fig_donut, use_container_width=True)

with col_trend:
    st.subheader("Filing Trend (by year)")
    df_apps = pd.DataFrame(apps)
    if "appFilingDate" in df_apps.columns:
        df_apps["year"] = pd.to_datetime(
            df_apps["appFilingDate"], errors="coerce"
        ).dt.year
        trend = df_apps.groupby("year").size().reset_index(name="count")
        fig_trend = px.bar(trend, x="year", y="count",
                           labels={"year": "Filing Year", "count": "Applications"},
                           color_discrete_sequence=["#3498db"])
        fig_trend.update_layout(margin=dict(t=10, b=10), height=280)
        st.plotly_chart(fig_trend, use_container_width=True)
    else:
        st.info("Filing date data not available.")

# ── AI summary (if key configured) ───────────────────────────────────────────
from config import OPENAI_API_KEY
if OPENAI_API_KEY:
    with st.expander("🤖 AI Examiner Brief (click to generate)"):
        if st.button("Generate AI Summary"):
            with st.spinner("Generating AI summary…"):
                from services.openai_service import examiner_summary
                summary = examiner_summary(examiner_name, stats)
            st.markdown(summary)

# ── Applications table ────────────────────────────────────────────────────────
st.markdown("---")
st.subheader(f"Recent Applications (showing {len(apps)} of sample)")

display_cols = {
    "patentApplicationNumber": "Application #",
    "inventionTitle": "Title",
    "appFilingDate": "Filing Date",
    "appGroupArtUnitNumber": "Art Unit",
    "applicationStatusCode": "Status Code",
    "patentNumber": "Patent #",
}

df_display = pd.DataFrame(apps)
available = {k: v for k, v in display_cols.items() if k in df_display.columns}
if available:
    df_show = df_display[list(available.keys())].rename(columns=available)
    df_show = df_show.sort_values("Filing Date", ascending=False) if "Filing Date" in df_show else df_show
    st.dataframe(df_show, use_container_width=True, height=400)
else:
    st.json(apps[:5])

st.caption(
    "Data source: USPTO Patent Examination Data System (PEDS). "
    "Sample limited to 200 most-recent applications. "
    "Score is computed from this sample and may differ from PatentAdvisor ETA™."
)
