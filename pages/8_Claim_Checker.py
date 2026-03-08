"""
Page 8 – Claim Checker
Pre-filing claim weakness analysis (§102 / §103 / §112).
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from utils.auth import require_auth, sidebar_user
from config import OPENAI_API_KEY

require_auth()
sidebar_user()

st.title("✅ Claim Checker")
st.caption(
    "Paste patent claims before filing to get an AI-powered risk assessment for "
    "§102 novelty, §103 obviousness, and §112 indefiniteness issues."
)

if not OPENAI_API_KEY:
    st.error("OpenAI API key not configured. Set `OPENAI_API_KEY` in `.env` and restart.")
    st.stop()

with st.form("claim_form"):
    tech_area = st.text_input(
        "Technology Area / CPC Class (optional)",
        placeholder="e.g. Software / G06F  or  Biotech / C12N",
    )
    art_unit = st.text_input(
        "Target Art Unit (optional – adds examiner context)",
        placeholder="e.g. 2143",
    )
    claims = st.text_area(
        "Claims",
        height=350,
        placeholder=(
            "1. A method comprising:\n"
            "   receiving, by a processor, input data;\n"
            "   processing the input data to generate an output;\n"
            "   transmitting the output to a remote server.\n\n"
            "2. The method of claim 1, wherein..."
        ),
    )
    submitted = st.form_submit_button("Analyse Claims", use_container_width=True)

if not submitted or not claims.strip():
    st.stop()

# ── Optional: pull art unit context ──────────────────────────────────────────
au_context = ""
if art_unit.strip():
    from services import uspto_api
    from services.scoring import compute_examiner_score
    with st.spinner(f"Fetching art unit {art_unit} examiner context…"):
        au_apps = uspto_api.search_by_art_unit(art_unit.strip())
    if au_apps:
        au_stats = compute_examiner_score(au_apps)
        au_context = (
            f"\n\nTarget Art Unit {art_unit} context: "
            f"allowance rate {au_stats['allowance_rate']} %, "
            f"avg OAs {au_stats['avg_oa']}, "
            f"difficulty band: {au_stats['band']}."
        )

# ── Run AI analysis ───────────────────────────────────────────────────────────
with st.spinner("Analysing claims…"):
    from services.openai_service import analyze_claims
    full_tech = tech_area + au_context
    result = analyze_claims(claims, tech_area=full_tech)

st.markdown("---")
st.subheader("Claim Analysis Report")
st.markdown(result)

# ── Tips ──────────────────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("Tips for stronger claims"):
    st.markdown("""
- **§102 (Novelty):** Ensure each independent claim has at least one element not found in any single prior art reference.
- **§103 (Obviousness):** Include unexpected results, long-felt need, or specific combinations that the prior art would not suggest.
- **§112(b) (Indefiniteness):** Avoid relative terms (e.g., "substantially", "about") without a clear standard of measure; define all means-plus-function terms in the specification.
- **§112(a) (Written Description):** Make sure every claim element is fully described and enabled in the specification.
- **Software claims:** Add specific technical improvements; avoid purely functional language at the highest level of abstraction.
    """)
