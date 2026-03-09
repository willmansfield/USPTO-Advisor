"""
Portfolio — company prosecution health dashboard.

Enter a company name → instant portfolio overview with outcome distribution,
filing trends, examiner concentration, art unit breakdown, and AI executive summary.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
from collections import Counter

from utils.auth import require_auth, sidebar_user
from services import uspto_api, openai_service
from services.scoring import compute_examiner_score
from services.uspto_api import meta, get_outcome, get_patent_number, get_assignee

require_auth()
sidebar_user()

st.title("💼 Portfolio")
st.caption("Prosecution health dashboard for any company or assignee — powered by live USPTO data.")


def _score_badge(score, band, color):
    return (
        f'<span style="background:{color};color:white;padding:4px 14px;'
        f'border-radius:20px;font-weight:700;font-size:1rem;">'
        f'{band} &nbsp; {score}/100</span>'
    )


# ── Search ────────────────────────────────────────────────────────────────────

default_company = st.session_state.pop("portfolio_prefill", "") or ""

with st.form("portfolio_form"):
    col_i, col_b = st.columns([4, 1])
    with col_i:
        company = st.text_input(
            "Company name",
            value=default_company,
            placeholder="e.g. Apple Inc, Google LLC, Microsoft Corporation",
            label_visibility="collapsed",
        )
    with col_b:
        search = st.form_submit_button("Analyse portfolio", use_container_width=True)

if not company:
    st.info("Enter a company or assignee name to analyse their patent portfolio.")
    st.stop()

# ── Fetch ─────────────────────────────────────────────────────────────────────

with st.spinner(f"Fetching portfolio data for {company}…"):
    apps = uspto_api.search_by_assignee(company)

if not apps:
    st.error(f"No applications found for **{company}**. Try a variation of the name.")
    st.stop()

stats = compute_examiner_score(apps)

# ── Header ────────────────────────────────────────────────────────────────────

st.markdown(f"## {company}")
st.caption(f"Analysis based on {len(apps)} most recent applications")
st.markdown(_score_badge(stats["score"], stats["band"], stats["color_hex"]),
            unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

# Headline metrics
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total (sample)", stats["total"])
m2.metric("Patented", stats["patented"])
m3.metric("Abandoned", stats["abandoned"])
m4.metric("Allowance Rate", f"{stats['allowance_rate']}%")
m5.metric("Avg Pendency", f"{stats['avg_pendency']} mo")

st.markdown("---")

# ── AI Executive Summary (always) ─────────────────────────────────────────────

if openai_service._check():
    st.markdown("### 🤖 AI Executive Summary")
    cache_key = f"portfolio_summary_{company}"
    if cache_key not in st.session_state:
        with st.spinner("Generating AI executive summary…"):
            report = openai_service.portfolio_summary(company, stats, apps[:50])
            st.session_state[cache_key] = report
    st.markdown(st.session_state[cache_key])
    st.markdown("---")
else:
    st.info("Add **OPENAI_API_KEY** to `.env` to enable AI executive summaries.")

# ── Charts row 1: trend + outcomes ────────────────────────────────────────────

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### Filing Trend")
    years = Counter(
        str(meta(a).get("filingDate", ""))[:4]
        for a in apps if meta(a).get("filingDate", "")
    )
    yr_df = pd.DataFrame(sorted(years.items()), columns=["Year", "Applications"])
    yr_df = yr_df[yr_df["Year"].str.isdigit()]
    fig_trend = px.area(yr_df, x="Year", y="Applications", color_discrete_sequence=["#3498db"])
    fig_trend.update_layout(margin=dict(t=0, b=0), height=280)
    st.plotly_chart(fig_trend, use_container_width=True)

with col2:
    st.markdown("#### Outcomes")
    fig_donut = px.pie(
        names=["Patented", "Abandoned", "Pending"],
        values=[stats["patented"], stats["abandoned"], stats["pending"]],
        color_discrete_map={"Patented": "#2ecc71", "Abandoned": "#e74c3c", "Pending": "#95a5a6"},
        hole=0.55,
    )
    fig_donut.update_layout(margin=dict(t=0, b=0), showlegend=True, height=280)
    st.plotly_chart(fig_donut, use_container_width=True)

# ── Charts row 2: top examiners + art units ────────────────────────────────────

col3, col4 = st.columns(2)

with col3:
    st.markdown("#### Top Examiners")
    examiners = Counter(meta(a).get("examinerNameText", "") for a in apps)
    top_ex = examiners.most_common(15)
    if top_ex:
        ex_df = pd.DataFrame(top_ex, columns=["Examiner", "Applications"])
        # Shorten to last name only for chart
        ex_df["Examiner"] = ex_df["Examiner"].apply(lambda n: n.split(",")[0] if n else n)
        fig_ex = px.bar(
            ex_df, x="Applications", y="Examiner", orientation="h",
            color_discrete_sequence=["#9b59b6"],
        )
        fig_ex.update_layout(margin=dict(t=0, b=0), height=340,
                             yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_ex, use_container_width=True)
    # Click to go to examiner page
    if st.button("🔍 Explore an examiner's full profile →"):
        st.info("Click any row in the Applications table below to open in Prosecution Hub, "
                "or use the Examiner Intel page.")

with col4:
    st.markdown("#### Art Unit Distribution")
    art_units = Counter(meta(a).get("groupArtUnitNumber", "") for a in apps)
    top_au = art_units.most_common(15)
    if top_au:
        au_df = pd.DataFrame(top_au, columns=["Art Unit", "Applications"])
        au_df = au_df[au_df["Art Unit"].str.len() > 0]
        fig_au = px.bar(
            au_df, x="Applications", y="Art Unit", orientation="h",
            color_discrete_sequence=["#e67e22"],
        )
        fig_au.update_layout(margin=dict(t=0, b=0), height=340,
                             yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig_au, use_container_width=True)

st.markdown("---")

# ── Application table ──────────────────────────────────────────────────────────

st.markdown("#### Applications")
rows = []
for a in apps:
    m_ = meta(a)
    rows.append({
        "App №": a.get("applicationNumberText", ""),
        "Title": str(m_.get("inventionTitle", ""))[:60],
        "Filed": (m_.get("filingDate") or "")[:10],
        "Art Unit": m_.get("groupArtUnitNumber", ""),
        "Examiner": (m_.get("examinerNameText") or "").split(",")[0],
        "Status": m_.get("applicationStatusDescriptionText", ""),
        "Patent №": get_patent_number(a),
    })
df = pd.DataFrame(rows)

event = st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)
if event and event.selection.rows:
    selected_idx = event.selection.rows[0]
    selected_app = df.iloc[selected_idx]["App №"]
    st.session_state["detail_app_num"] = selected_app
    st.switch_page("pages/1_Prosecution_Hub.py")
