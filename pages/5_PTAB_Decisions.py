"""
Page 5 – PTAB Decisions
Search Patent Trial and Appeal Board decisions.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from utils.auth import require_auth, sidebar_user
from services import uspto_api
from config import OPENAI_API_KEY

require_auth()
sidebar_user()

st.title("⚖️ PTAB Decisions")
st.caption("Search Patent Trial and Appeal Board trial decisions (IPR, PGR, CBM).")

# ── Search form ───────────────────────────────────────────────────────────────
with st.form("ptab_form"):
    col1, col2 = st.columns(2)
    with col1:
        patent_owner = st.text_input("Patent Owner", placeholder="e.g. Apple Inc")
    with col2:
        petitioner   = st.text_input("Petitioner",   placeholder="e.g. Samsung")
    rows = st.slider("Max results", 10, 100, 25, step=5)
    submitted = st.form_submit_button("Search PTAB", use_container_width=True)

if not submitted:
    st.stop()

if not patent_owner and not petitioner:
    st.warning("Enter at least one search criterion.")
    st.stop()

with st.spinner("Querying USPTO PTAB API…"):
    decisions = uspto_api.search_ptab(
        patent_owner=patent_owner,
        petitioner=petitioner,
        rows=rows,
    )

if not decisions:
    st.warning(
        "No decisions returned.  "
        "The PTAB API may require an API key or the endpoint may have changed — "
        "check the USPTO Open Data Portal at data.uspto.gov."
    )
    st.stop()

st.success(f"Found {len(decisions)} decision(s).")

# ── Results table ─────────────────────────────────────────────────────────────
# PTAB API response structure varies between versions; normalise here.
def _extract(d: dict) -> dict:
    return {
        "Proceeding #":   d.get("proceedingNumber") or d.get("trialNumber") or "",
        "Type":           d.get("proceedingTypeCategory") or d.get("proceedingType") or "",
        "Patent Owner":   d.get("respondentPatentOwnerName") or d.get("patentOwnerName") or "",
        "Petitioner":     d.get("petitionerPartyName") or d.get("petitioner") or "",
        "Patent #":       d.get("respondentPatentNumber") or d.get("patentNumber") or "",
        "Institution":    d.get("institutionDecisionDate") or "",
        "FWD Date":       d.get("finalWrittenDecisionDate") or "",
        "Outcome":        d.get("prosecutionStatus") or d.get("status") or "",
    }

df = pd.DataFrame([_extract(d) for d in decisions])
st.dataframe(df, use_container_width=True, height=450)

# ── Decision detail + AI analysis ────────────────────────────────────────────
if OPENAI_API_KEY and decisions:
    st.markdown("---")
    st.subheader("AI Decision Analysis")
    st.caption("Select a decision and paste its text for AI analysis.")

    proc_nums = [_extract(d)["Proceeding #"] for d in decisions if _extract(d)["Proceeding #"]]
    if proc_nums:
        selected = st.selectbox("Select a proceeding", proc_nums)

    decision_text = st.text_area(
        "Paste full decision text here (copy from USPTO PTAB portal):",
        height=250,
        placeholder="Enter the decision text to analyse…",
    )

    if decision_text and st.button("Analyse Decision with AI"):
        with st.spinner("Analysing decision…"):
            from services.openai_service import tag_ptab_decision
            analysis = tag_ptab_decision(decision_text)
        st.markdown("### AI Analysis")
        st.markdown(analysis)

st.caption(
    "Data: USPTO PTAB API (data.uspto.gov). "
    "Covers AIA trial proceedings (IPR, PGR, CBM) since September 2012."
)
