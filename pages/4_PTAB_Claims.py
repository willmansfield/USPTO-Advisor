"""
PTAB & Pre-filing — two tools for risk assessment.

  PTAB Research   — search IPR/PGR/CBM trial decisions, view detail, get AI analysis.
  Pre-filing Check — paste claims before filing for §102/103/112 risk analysis.
"""

import streamlit as st
import pandas as pd

from utils.auth import require_auth, sidebar_user
from services import uspto_api, openai_service
from services.scoring import compute_examiner_score

require_auth()
sidebar_user()

st.title("⚖️ PTAB & Pre-filing")

tab_ptab, tab_claims = st.tabs(["🏛️ PTAB Research", "✅ Pre-filing Claim Check"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 – PTAB RESEARCH
# ══════════════════════════════════════════════════════════════════════════════

with tab_ptab:
    st.markdown("Search IPR, PGR, and CBM trial decisions from the USPTO Patent Trial and Appeal Board.")
    st.markdown("")

    with st.form("ptab_form"):
        col_a, col_b, col_c = st.columns([3, 3, 1])
        with col_a:
            owner = st.text_input("Patent owner / respondent", placeholder="e.g. Apple Inc")
        with col_b:
            petitioner = st.text_input("Petitioner / challenger", placeholder="e.g. Samsung")
        with col_c:
            rows = st.number_input("Max results", min_value=5, max_value=100, value=25, step=5)
        ptab_search = st.form_submit_button("Search PTAB", use_container_width=True)

    if not owner and not petitioner:
        st.info("Enter a patent owner or petitioner name to search PTAB decisions.")
        st.stop()

    with st.spinner("Searching PTAB decisions…"):
        decisions = uspto_api.search_ptab(
            patent_owner=owner, petitioner=petitioner, rows=int(rows)
        )

    if not decisions:
        st.warning("No PTAB decisions found. Try a different name or spelling.")
        st.stop()

    st.success(f"Found **{len(decisions)}** decisions")

    # ── Results table ─────────────────────────────────────────────────────────
    table_rows = []
    for d in decisions:
        table_rows.append({
            "Trial №": d.get("trialNumber", ""),
            "Type": d.get("trialTypeCategory", ""),
            "Status": d.get("prosecutionStatus", ""),
            "Patent Owner": d.get("patentOwnerName", ""),
            "Petitioner": d.get("petitionerPartyName", ""),
            "Patent №": d.get("patentNumber", ""),
            "Filed": (d.get("filingDate") or "")[:10],
            "Institution": (d.get("institutionDecisionDate") or "")[:10],
            "FWD": (d.get("finalWrittenDecisionDate") or "")[:10],
        })
    df = pd.DataFrame(table_rows)

    event = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    # ── Selected decision detail ───────────────────────────────────────────────
    if event and event.selection.rows:
        idx = event.selection.rows[0]
        d = decisions[idx]
        st.markdown("---")
        st.markdown(f"### Trial {d.get('trialNumber', '')}")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Type", d.get("trialTypeCategory", ""))
        c2.metric("Status", d.get("prosecutionStatus", ""))
        c3.metric("Patent №", d.get("patentNumber", ""))
        c4.metric("Art Unit", d.get("groupArtUnitNumber", "") or "—")

        c5, c6 = st.columns(2)
        c5.metric("Patent Owner", d.get("patentOwnerName", ""))
        c6.metric("Petitioner", d.get("petitionerPartyName", ""))

        d3, d4, d5 = st.columns(3)
        d3.metric("Filed", (d.get("filingDate") or "")[:10])
        d4.metric("Institution Decision", (d.get("institutionDecisionDate") or "")[:10] or "—")
        d5.metric("Final Decision", (d.get("finalWrittenDecisionDate") or "")[:10] or "—")

        trial_num = d.get("trialNumber", "")
        if trial_num:
            st.markdown(
                f"[📄 View on PTAB portal](https://ptab.uspto.gov/#/ptab-trial/{trial_num})",
                unsafe_allow_html=False,
            )

        # AI analysis
        if openai_service._check():
            st.markdown("#### AI Analysis")
            st.markdown(
                "Paste the full decision text below for AI analysis of legal issues and practical takeaways."
            )
            decision_text = st.text_area(
                "Decision text", height=250, placeholder="Paste the full PTAB decision text here…",
                key=f"ptab_text_{idx}"
            )
            if st.button("Analyse decision", key=f"ptab_btn_{idx}") and decision_text:
                with st.spinner("Analysing decision…"):
                    analysis = openai_service.tag_ptab_decision(decision_text)
                st.markdown(analysis)
        else:
            st.info("Add **OPENAI_API_KEY** to `.env` to enable AI PTAB analysis.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 – PRE-FILING CLAIM CHECK
# ══════════════════════════════════════════════════════════════════════════════

with tab_claims:
    st.markdown(
        "Paste your patent claims before filing to identify potential §102 novelty risks, "
        "§103 obviousness risks, §112 indefiniteness issues, and scope problems. "
        "Optionally add a target art unit to tailor the analysis with live examiner statistics."
    )
    st.markdown("")

    if not openai_service._check():
        st.warning("Add **OPENAI_API_KEY** to `.env` to use the claim checker.")
        st.stop()

    col_left, col_right = st.columns([3, 1])
    with col_left:
        claims_text = st.text_area(
            "Claim text",
            height=260,
            placeholder="1. A method comprising:\n   a) ...\n   b) ...\n\n2. The method of claim 1, wherein...",
        )
    with col_right:
        tech_area = st.text_input(
            "Technology area (optional)",
            placeholder="e.g. Software / G06F",
        )
        target_au = st.text_input(
            "Target art unit (optional)",
            placeholder="e.g. 2143",
        )
        st.markdown("<br>", unsafe_allow_html=True)
        analyse = st.button("🔍 Analyse Claims", use_container_width=True, type="primary")

    if not claims_text:
        st.info("Paste your claims above and click 'Analyse Claims'.")
        st.stop()

    if not analyse:
        st.stop()

    # Fetch art unit context if provided
    tech_context = tech_area or ""
    au_context_shown = False
    if target_au:
        with st.spinner(f"Fetching art unit {target_au} statistics…"):
            au_apps = uspto_api.search_by_art_unit(target_au)
        if au_apps:
            au_stats = compute_examiner_score(au_apps)
            st.info(
                f"Art Unit {target_au} context loaded: "
                f"**{au_stats['band']}** — "
                f"{au_stats['allowance_rate']}% allowance rate, "
                f"{au_stats['avg_oa']} avg office actions, "
                f"{au_stats['avg_pendency']} mo avg pendency."
            )
            tech_context += (
                f" | Art Unit {target_au}: {au_stats['allowance_rate']}% allowance, "
                f"{au_stats['avg_oa']} avg OAs, {au_stats['band']}"
            )
            au_context_shown = True

    with st.spinner("Analysing claims…"):
        analysis = openai_service.analyze_claims(claims_text, tech_area=tech_context)

    st.markdown("---")
    st.markdown("### Claim Analysis")
    st.markdown(analysis)

    st.markdown("---")
    with st.expander("💡 Tips for using this analysis"):
        st.markdown("""
- **§102 risks**: These suggest prior art may anticipate your claims. Consider narrowing the claim scope or adding distinguishing limitations.
- **§103 risks**: Obviousness rejections are the most common. Identify the point of novelty and make it explicit in the independent claims.
- **§112 risks**: Indefiniteness issues are often easy to fix before filing — clearer antecedent basis and defined terms prevent prosecution delay.
- **Scope**: Overly broad claims invite rejection; overly narrow claims limit protection. Consider a claim ladder: broad independent → narrowing dependents.
- **Next steps**: Consider a prior art search in the target art unit, and file with a range of dependent claims to preserve fallback positions.
        """)
