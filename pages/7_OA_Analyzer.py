"""
Page 7 - Office Action Analyzer
Load OA text and current claims automatically via USPTO XML API or paste manually.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from utils.auth import require_auth, sidebar_user
from config import OPENAI_API_KEY

require_auth()
sidebar_user()

st.title("Office Action Analyzer")
st.caption(
    "Load an Office Action and current claims directly from the USPTO file wrapper, "
    "then get a plain-English explanation and AI response strategy."
)

if not OPENAI_API_KEY:
    st.error("OpenAI API key not configured. Set OPENAI_API_KEY in .env and restart.")
    st.stop()

# -- Session state
if "oa_docs" not in st.session_state:
    st.session_state.oa_docs = []
if "oa_app_num" not in st.session_state:
    st.session_state.oa_app_num = ""
if "oa_text_loaded" not in st.session_state:
    st.session_state.oa_text_loaded = ""
if "claims_text_loaded" not in st.session_state:
    st.session_state.claims_text_loaded = ""

# -- Option A: load from USPTO
st.subheader("Option A - Load from USPTO (by application number)")
with st.form("oa_load_form"):
    col1, col2 = st.columns([3, 1])
    with col1:
        app_num_input = st.text_input("Application Number", placeholder="16/123456")
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        load_submitted = st.form_submit_button("Load OAs")

if load_submitted and app_num_input:
    from services import uspto_api
    with st.spinner("Loading Office Actions from USPTO..."):
        docs = uspto_api.get_oa_documents(app_num_input)
    st.session_state.oa_docs = docs
    st.session_state.oa_app_num = app_num_input
    st.session_state.oa_text_loaded = ""
    st.session_state.claims_text_loaded = ""

if st.session_state.oa_docs:
    docs = st.session_state.oa_docs
    options = {
        doc["documentCodeDescriptionText"] + " (" + doc["officialDate"][:10] + ")": doc
        for doc in docs
    }
    selected_label = st.selectbox("Select Office Action to load:", list(options.keys()))
    selected_doc = options[selected_label]

    if st.button("Fetch OA Text + Current Claims", type="primary"):
        from services import uspto_api
        with st.spinner("Fetching Office Action and claims from USPTO..."):
            oa_text = uspto_api.fetch_oa_text(
                st.session_state.oa_app_num,
                selected_doc["documentIdentifier"],
            )
            claims_text = uspto_api.fetch_claims_text(st.session_state.oa_app_num)
        st.session_state.oa_text_loaded = oa_text
        st.session_state.claims_text_loaded = claims_text
        st.success("Office Action and claims loaded. Review and edit below if needed.")

elif load_submitted and app_num_input:
    st.warning("No Office Actions found for that application number.")

st.markdown("---")

# -- Option B: paste manually
st.subheader("Option B - Paste Manually")

oa_text = st.text_area(
    "Office Action text:",
    value=st.session_state.oa_text_loaded,
    height=300,
    placeholder="OFFICE ACTION SUMMARY\n\nClaims 1-20 are rejected under 35 U.S.C. 103...",
)

claims_text = st.text_area(
    "Current claim language (for response strategy):",
    value=st.session_state.claims_text_loaded,
    height=200,
    placeholder="1. A method comprising:\n  receiving...\n  processing...",
)

col_btn1, col_btn2 = st.columns(2)
with col_btn1:
    run_explain = st.button("Explain Office Action", use_container_width=True)
with col_btn2:
    run_strategy = st.button(
        "Generate Response Strategy",
        use_container_width=True,
        disabled=not claims_text,
    )

if not oa_text:
    st.stop()

from services.openai_service import analyze_office_action, response_strategy

if run_explain:
    with st.spinner("Analysing Office Action..."):
        explanation = analyze_office_action(oa_text)
    st.markdown("---")
    st.subheader("Office Action Analysis")
    st.markdown(explanation)

if run_strategy and claims_text:
    with st.spinner("Generating response strategy..."):
        strategy = response_strategy(oa_text, claims_text)
    st.markdown("---")
    st.subheader("Recommended Response Strategy")
    st.markdown(strategy)