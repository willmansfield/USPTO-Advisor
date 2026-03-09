"""
Page 2 – Application Search
Multi-field search returning bibliographic data and prosecution status.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from utils.auth import require_auth, sidebar_user
from services import uspto_api

require_auth()
sidebar_user()

st.title("📋 Application Search")
st.caption("Search USPTO patent applications by multiple criteria.")

# ── Search form ───────────────────────────────────────────────────────────────
with st.form("app_search_form"):
    col1, col2 = st.columns(2)
    with col1:
        app_num  = st.text_input("Application Number", placeholder="e.g. 16123456")
        assignee = st.text_input("Assignee / Applicant", placeholder="e.g. Apple Inc")
        art_unit = st.text_input("Art Unit", placeholder="e.g. 2143")
    with col2:
        examiner = st.text_input("Examiner Name (last)", placeholder="e.g. SMITH")
        status   = st.selectbox(
            "Application Status",
            ["", "Patented Case", "Abandoned", "Pending", "Published"],
        )
    rows = st.slider("Max results", 10, 100, 50, step=10)
    submitted = st.form_submit_button("Search", use_container_width=True)

if not submitted:
    st.stop()

if not any([app_num, assignee, art_unit, examiner, status]):
    st.warning("Please enter at least one search criterion.")
    st.stop()

with st.spinner("Searching USPTO…"):
    apps = uspto_api.search_applications(
        app_num=app_num,
        assignee=assignee,
        examiner=examiner,
        art_unit=art_unit,
        status=status,
        rows=rows,
    )

if not apps:
    st.warning("No results found. Try broadening your search criteria.")
    st.stop()

st.success(f"Found {len(apps)} result(s).")

# ── Results table ─────────────────────────────────────────────────────────────
rows_data = []
for a in apps:
    m = uspto_api.meta(a)
    rows_data.append({
        "App #":        a.get("applicationNumberText", ""),
        "Title":        m.get("inventionTitle", "")[:60],
        "Filing Date":  m.get("filingDate", ""),
        "Art Unit":     m.get("groupArtUnitNumber", ""),
        "Examiner":     m.get("examinerNameText", ""),
        "Status":       m.get("applicationStatusDescriptionText", ""),
        "Status Date":  m.get("applicationStatusDate", ""),
        "Patent #":     uspto_api.get_patent_number(a),
        "Assignee":     uspto_api.get_assignee(a)[:40],
    })

df = pd.DataFrame(rows_data)
if "Filing Date" in df.columns:
    df["Filing Date"] = pd.to_datetime(df["Filing Date"], errors="coerce")
    df = df.sort_values("Filing Date", ascending=False)

selection = st.dataframe(
    df,
    use_container_width=True,
    height=500,
    on_select="rerun",
    selection_mode="single-row",
)

# -- Row click -> navigate to Application Detail
selected_rows = selection.selection.rows
if selected_rows:
    sel_app_num = str(df.iloc[selected_rows[0]]["App #"])
    st.session_state.detail_app_num = sel_app_num
    st.switch_page("pages/9_Application_Detail.py")

st.caption("Data: USPTO Open Data Portal (api.uspto.gov) — live query, updated daily.")
