"""
Page 7 – Office Action Analyzer
Paste or type an Office Action → AI explanation + response strategy.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from utils.auth import require_auth, sidebar_user
from config import OPENAI_API_KEY

require_auth()
sidebar_user()

st.title("📄 Office Action Analyzer")
st.caption(
    "Paste a USPTO Office Action to get a plain-English explanation of each rejection "
    "and an AI-generated response strategy."
)

if not OPENAI_API_KEY:
    st.error("OpenAI API key not configured. Set `OPENAI_API_KEY` in `.env` and restart.")
    st.stop()

# ── Optional: load OA via application number ──────────────────────────────────
st.subheader("Option A – Load from USPTO (by application number)")
with st.form("oa_load_form"):
    col1, col2 = st.columns([3, 1])
    with col1:
        app_num_input = st.text_input("Application Number", placeholder="16/123456")
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        load_submitted = st.form_submit_button("Load History")

if load_submitted and app_num_input:
    from services import uspto_api
    with st.spinner("Loading prosecution history…"):
        transactions = uspto_api.get_transactions(app_num_input)
    if transactions:
        oa_txns = [t for t in transactions if t.get("eventCode", "") in {"CTNF", "CTFR"}]
        st.info(
            f"Found {len(oa_txns)} Office Action(s) for application {app_num_input}.  "
            "To read the full text, retrieve the PDF from "
            "[USPTO Patent Center](https://patentcenter.uspto.gov) and paste below."
        )
        if oa_txns:
            df_oa = [{"Date": t["recordDate"], "Type": t["eventDescriptionText"]} for t in oa_txns]
            st.table(df_oa)
    else:
        st.warning("No transaction history found.")

st.markdown("---")

# ── Main OA text input ────────────────────────────────────────────────────────
st.subheader("Option B – Paste Office Action Text")

oa_text = st.text_area(
    "Paste the full Office Action text here:",
    height=300,
    placeholder="OFFICE ACTION SUMMARY\n\nClaims 1-20 are rejected under 35 U.S.C. § 103...",
)

claims_text = st.text_area(
    "Paste current claim language (for response strategy):",
    height=200,
    placeholder="1. A method comprising:\n  receiving...\n  processing...",
)

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    run_explain   = st.button("Explain Office Action", use_container_width=True)
with col_btn2:
    run_strategy  = st.button("Generate Response Strategy", use_container_width=True, disabled=not claims_text)

if not oa_text:
    st.stop()

from services.openai_service import analyze_office_action, response_strategy

if run_explain:
    with st.spinner("Analysing Office Action…"):
        explanation = analyze_office_action(oa_text)
    st.markdown("---")
    st.subheader("Office Action Analysis")
    st.markdown(explanation)

if run_strategy and claims_text:
    with st.spinner("Generating response strategy…"):
        strategy = response_strategy(oa_text, claims_text)
    st.markdown("---")
    st.subheader("Recommended Response Strategy")
    st.markdown(strategy)
