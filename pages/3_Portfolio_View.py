"""
Page 3 – Portfolio View
Assignee or law-firm prosecution health dashboard.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter

from utils.auth import require_auth, sidebar_user
from services import uspto_api
from services.scoring import compute_examiner_score
from config import OPENAI_API_KEY

require_auth()
sidebar_user()

st.title("💼 Portfolio View")
st.caption("Enter a company or law-firm name to analyse their USPTO prosecution portfolio.")

with st.form("portfolio_form"):
    entity = st.text_input("Assignee / Company Name", placeholder="e.g. Google LLC")
    submitted = st.form_submit_button("Analyse Portfolio", use_container_width=True)

if not submitted or not entity.strip():
    st.stop()

entity = entity.strip()

with st.spinner(f"Fetching portfolio for '{entity}'…"):
    apps = uspto_api.search_by_assignee(entity)

if not apps:
    st.warning(f"No applications found for '{entity}'. Try a shorter or different name.")
    st.stop()

stats = compute_examiner_score(apps)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(f"## Portfolio: {entity}")
st.caption(f"Based on a sample of {stats['total']} most-recent applications.")

# ── Summary metrics ───────────────────────────────────────────────────────────
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Apps (sample)", stats["total"])
m2.metric("Patented", stats["patented"])
m3.metric("Abandoned", stats["abandoned"])
m4.metric("Pending", stats["pending"])
m5.metric("Allowance Rate", f"{stats['allowance_rate']} %" if stats["allowance_rate"] is not None else "N/A")

st.markdown("---")

# ── Charts ────────────────────────────────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Outcome Distribution")
    fig_pie = go.Figure(go.Pie(
        labels=["Patented", "Abandoned", "Pending"],
        values=[stats["patented"], stats["abandoned"], stats["pending"]],
        hole=0.4,
        marker_colors=["#2ecc71", "#e74c3c", "#95a5a6"],
    ))
    fig_pie.update_layout(margin=dict(t=10, b=10), height=280)
    st.plotly_chart(fig_pie, use_container_width=True)

with col_right:
    st.subheader("Filing Activity by Year")
    df = pd.DataFrame(apps)
    if "appFilingDate" in df.columns:
        df["year"] = pd.to_datetime(df["appFilingDate"], errors="coerce").dt.year
        trend = df.groupby("year").size().reset_index(name="count").dropna()
        fig_bar = px.bar(trend, x="year", y="count",
                         color_discrete_sequence=["#3498db"],
                         labels={"year": "Year", "count": "Filings"})
        fig_bar.update_layout(margin=dict(t=10, b=10), height=280)
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("Filing date data not available.")

# ── Examiner distribution ─────────────────────────────────────────────────────
st.markdown("---")
st.subheader("Top Examiners (by application count)")

examiner_counts = Counter(
    a.get("appExamNameText", "Unknown") for a in apps if a.get("appExamNameText")
)
top_examiners = pd.DataFrame(
    examiner_counts.most_common(20), columns=["Examiner", "Applications"]
)
if not top_examiners.empty:
    fig_ex = px.bar(
        top_examiners, x="Applications", y="Examiner", orientation="h",
        color_discrete_sequence=["#9b59b6"],
    )
    fig_ex.update_layout(margin=dict(t=10, b=10), height=400, yaxis={"autorange": "reversed"})
    st.plotly_chart(fig_ex, use_container_width=True)

# ── Art unit distribution ─────────────────────────────────────────────────────
st.subheader("Art Unit Distribution")
au_counts = Counter(
    a.get("appGroupArtUnitNumber", "Unknown") for a in apps if a.get("appGroupArtUnitNumber")
)
top_au = pd.DataFrame(au_counts.most_common(15), columns=["Art Unit", "Applications"])
if not top_au.empty:
    fig_au = px.bar(top_au, x="Art Unit", y="Applications",
                    color_discrete_sequence=["#e67e22"])
    fig_au.update_layout(margin=dict(t=10, b=10), height=300)
    st.plotly_chart(fig_au, use_container_width=True)

# ── AI portfolio report ───────────────────────────────────────────────────────
if OPENAI_API_KEY:
    st.markdown("---")
    with st.expander("🤖 AI Portfolio Report"):
        if st.button("Generate AI Report"):
            with st.spinner("Generating AI portfolio report…"):
                from services.openai_service import portfolio_summary
                report = portfolio_summary(entity, stats, apps)
            st.markdown(report)

# ── Raw data table ────────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("View Raw Application Data"):
    df = pd.DataFrame(apps)
    cols = {
        "patentApplicationNumber": "App #",
        "inventionTitle": "Title",
        "appFilingDate": "Filing Date",
        "appGroupArtUnitNumber": "Art Unit",
        "appExamNameText": "Examiner",
        "applicationStatusCode": "Status",
        "patentNumber": "Patent #",
    }
    available = {k: v for k, v in cols.items() if k in df.columns}
    st.dataframe(df[list(available.keys())].rename(columns=available), use_container_width=True)

st.caption("Data: USPTO PEDS – sample up to 200 most-recent applications.")
