"""
Page 5 – PTAB Decisions
Search Patent Trial and Appeal Board trial decisions.
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
    st.warning("No decisions returned. Check search terms and try again.")
    st.stop()

st.success(f"Found {len(decisions)} decision(s).")

# ── Results table ─────────────────────────────────────────────────────────────
# ODP PTAB response: patentTrialDocumentDataBag[]
def _extract(d: dict) -> dict:
    tm = d.get("trialMetaData", {})
    po = d.get("patentOwnerData", {})
    rp = d.get("regularPetitionerData", {})
    return {
        "Trial #":       d.get("trialNumber", ""),
        "Type":          tm.get("trialTypeCode", ""),
        "Status":        tm.get("trialStatusCategory", ""),
        "Patent Owner":  po.get("realPartyInInterestName", ""),
        "Petitioner":    rp.get("realPartyInInterestName", ""),
        "Patent #":      po.get("patentNumber", ""),
        "Art Unit":      po.get("groupArtUnitNumber", ""),
        "Filed":         tm.get("accordedFilingDate", ""),
        "Institution":   tm.get("institutionDecisionDate", ""),
        "FWD":           tm.get("finalWrittenDecisionDate", ""),
    }

df = pd.DataFrame([_extract(d) for d in decisions])
st.dataframe(df, use_container_width=True, height=450)

# ── AI decision analysis ──────────────────────────────────────────────────────
if OPENAI_API_KEY:
    st.markdown("---")
    st.subheader("AI Decision Analysis")
    st.caption("Paste the full text of a PTAB decision for AI analysis and legal-issue tagging.")

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
    "Data: USPTO PTAB API (api.uspto.gov). "
    "Covers AIA trial proceedings (IPR, PGR, CBM) since September 2012."
)
