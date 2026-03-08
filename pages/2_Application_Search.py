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
        app_num   = st.text_input("Application Number", placeholder="e.g. 16/123456")
        assignee  = st.text_input("Assignee / Applicant", placeholder="e.g. Apple Inc")
        art_unit  = st.text_input("Art Unit", placeholder="e.g. 2143")
    with col2:
        examiner  = st.text_input("Examiner Name (last)", placeholder="e.g. Smith")
        attorney  = st.text_input("Attorney Docket #", placeholder="e.g. 12345.001US1")
        status    = st.selectbox(
            "Application Status",
            ["", "Patented Case", "Abandoned", "Pending", "Published"],
        )
    rows = st.slider("Max results", 10, 100, 50, step=10)
    submitted = st.form_submit_button("Search", use_container_width=True)

if not submitted:
    st.stop()

if not any([app_num, assignee, art_unit, examiner, attorney, status]):
    st.warning("Please enter at least one search criterion.")
    st.stop()

# Build query string for examiner (handled separately via PEDS field)
extra_query = f"appExamNameText:({examiner})" if examiner else ""

with st.spinner("Searching USPTO PEDS…"):
    apps = uspto_api.search_applications(
        query_str=extra_query,
        app_num=app_num,
        assignee=assignee,
        attorney=attorney,
        art_unit=art_unit,
        status=status,
        rows=rows,
    )

if not apps:
    st.warning("No results found. Try broadening your search criteria.")
    st.stop()

st.success(f"Found {len(apps)} result(s).")

# ── Results table ─────────────────────────────────────────────────────────────
display_cols = {
    "patentApplicationNumber": "Application #",
    "inventionTitle":          "Title",
    "appFilingDate":           "Filing Date",
    "appGroupArtUnitNumber":   "Art Unit",
    "appExamNameText":         "Examiner",
    "applicationStatusCode":   "Status Code",
    "applicationStatusDate":   "Status Date",
    "patentNumber":            "Patent #",
    "assigneeEntityName":      "Assignee",
}

df = pd.DataFrame(apps)
available = {k: v for k, v in display_cols.items() if k in df.columns}
df_show = df[list(available.keys())].rename(columns=available)

# Sort by filing date descending if available
if "Filing Date" in df_show.columns:
    df_show["Filing Date"] = pd.to_datetime(df_show["Filing Date"], errors="coerce")
    df_show = df_show.sort_values("Filing Date", ascending=False)

st.dataframe(df_show, use_container_width=True, height=500)

# ── Application detail expander ───────────────────────────────────────────────
st.markdown("---")
st.subheader("View Full Prosecution History")
sel_num = st.text_input(
    "Enter an application number from the results above to view its prosecution history:",
    placeholder="16/123456",
)
if sel_num:
    with st.spinner("Loading prosecution history…"):
        app_detail = uspto_api.get_application(sel_num)
        transactions = uspto_api.get_transactions(sel_num)

    if app_detail:
        c1, c2, c3 = st.columns(3)
        c1.metric("Status", app_detail.get("applicationStatusCode", "N/A"))
        c2.metric("Filing Date", app_detail.get("appFilingDate", "N/A"))
        c3.metric("Patent #", app_detail.get("patentNumber", "—"))

        st.markdown(f"**Title:** {app_detail.get('inventionTitle', 'N/A')}")
        st.markdown(f"**Examiner:** {app_detail.get('appExamNameText', 'N/A')} &nbsp;|&nbsp; "
                    f"**Art Unit:** {app_detail.get('appGroupArtUnitNumber', 'N/A')}")

        if transactions:
            st.subheader("Prosecution Timeline")
            tx_rows = [
                {
                    "Date": t.get("recordDate", ""),
                    "Code": t.get("eventCode", ""),
                    "Event": t.get("eventDescriptionText", ""),
                }
                for t in transactions
            ]
            df_tx = pd.DataFrame(tx_rows).sort_values("Date")
            st.dataframe(df_tx, use_container_width=True)
        else:
            st.info("Transaction history not available for this application.")
    else:
        st.error(f"Application {sel_num} not found.")

st.caption("Data: USPTO PEDS — live query, updated daily.")
