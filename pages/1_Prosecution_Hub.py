"""
Prosecution Hub — the central workspace for any active application.

Enter an application number → see full prosecution context, examiner difficulty
inline, AI-narrated prosecution summary, and instant OA analysis.
"""

import streamlit as st
from utils.auth import require_auth, sidebar_user
from services import uspto_api, openai_service
from services.scoring import compute_examiner_score
from services.uspto_api import (
    meta, get_outcome, get_patent_number, get_assignee,
    count_office_actions, count_rces, pendency_months,
)

require_auth()
sidebar_user()

st.title("⚖️ Prosecution Hub")
st.caption("Look up any application — see the full prosecution picture and get AI-powered next steps.")

# ── Event colour coding ───────────────────────────────────────────────────────

_EVENT_COLORS = {
    "CTNF": ("#e74c3c", "🔴"),  "CTFR": ("#e74c3c", "🔴"),
    "MCTNF": ("#e74c3c", "🔴"), "MCTFR": ("#e74c3c", "🔴"),
    "RCE":  ("#e67e22", "🟠"),  "RCE2": ("#e67e22", "🟠"),
    "M327": ("#2ecc71", "🟢"),  "MNDC": ("#2ecc71", "🟢"),  "MNAL": ("#2ecc71", "🟢"),
    "FWDX": ("#2ecc71", "🟢"),  "ISSUE": ("#2ecc71", "🟢"),
    "RESP": ("#3498db", "🔵"),  "A___": ("#3498db", "🔵"),
}

def _event_icon(code: str) -> str:
    return _EVENT_COLORS.get(code, ("#95a5a6", "⚪"))[1]

def _score_badge(score, band, color):
    return (
        f'<span style="background:{color};color:white;padding:4px 14px;'
        f'border-radius:20px;font-weight:700;font-size:1rem;">'
        f'{band} &nbsp; {score}/100</span>'
    )

# ── Search ────────────────────────────────────────────────────────────────────

# Pre-fill from cross-page navigation (e.g. click from Examiner Intel)
default_app = st.session_state.pop("detail_app_num", "") or ""

with st.form("hub_search"):
    col_i, col_b = st.columns([4, 1])
    with col_i:
        app_num = st.text_input(
            "Application number",
            value=default_app,
            placeholder="e.g. 16439518",
            label_visibility="collapsed",
        )
    with col_b:
        search = st.form_submit_button("Load application", use_container_width=True)

if not app_num:
    st.info("Enter a USPTO application number above to get started.")
    st.stop()

# ── Load data ─────────────────────────────────────────────────────────────────

with st.spinner("Fetching application data…"):
    app_data = uspto_api.get_application(app_num)

if not app_data:
    st.error(f"Application **{app_num}** not found. Check the number and try again.")
    st.stop()

m       = meta(app_data)
outcome = get_outcome(app_data)
patent  = get_patent_number(app_data)
events  = app_data.get("eventDataBag") or []
examiner_name = m.get("examinerNameText", "")
art_unit = m.get("groupArtUnitNumber", "")

# ── Application header ────────────────────────────────────────────────────────

status_icon = {"patented": "✅", "abandoned": "❌", "pending": "🔄"}.get(outcome, "❓")
st.markdown(f"## {status_icon} {m.get('inventionTitle', app_num)}")

col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("Status", m.get("applicationStatusDescriptionText", outcome.title()))
col_b.metric("Filed", (m.get("filingDate") or "")[:10])
col_c.metric("Art Unit", art_unit or "—")
col_d.metric("Patent №" if patent else "Office Actions", patent if patent else count_office_actions(app_data))

assignee = get_assignee(app_data)
if assignee:
    st.caption(f"Assignee: **{assignee}**")

st.markdown("---")

# ── Examiner card (inline) ────────────────────────────────────────────────────

examiner_stats = None
if examiner_name:
    with st.spinner(f"Loading examiner profile for {examiner_name}…"):
        ex_apps = uspto_api.search_by_examiner(examiner_name)
    if ex_apps:
        examiner_stats = compute_examiner_score(ex_apps)

    col_ex, col_link = st.columns([3, 1])
    with col_ex:
        st.markdown("#### 👤 Examiner")
        if examiner_stats:
            st.markdown(
                _score_badge(examiner_stats["score"], examiner_stats["band"], examiner_stats["color_hex"]),
                unsafe_allow_html=True,
            )
            st.markdown("")  # spacer
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Allowance Rate", f"{examiner_stats['allowance_rate']}%")
            m2.metric("Avg Office Actions", examiner_stats["avg_oa"])
            m3.metric("Avg Pendency", f"{examiner_stats['avg_pendency']} mo")
            m4.metric("RCE Rate", f"{examiner_stats['rce_rate']}%" if examiner_stats["rce_rate"] is not None else "—")
        else:
            st.write(f"**{examiner_name}** (no stats available)")
    with col_link:
        st.markdown("#### &nbsp;")
        if st.button("🔍 Full examiner profile", use_container_width=True):
            st.session_state["examiner_prefill"] = examiner_name
            st.switch_page("pages/2_Examiner_Intel.py")

st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_ai, tab_timeline, tab_docs = st.tabs(["🤖 AI Analysis", "📋 Prosecution Timeline", "📄 Documents"])


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 1 – AI Analysis  (auto-runs)
# ═══════════════════════════════════════════════════════════════════════════════

with tab_ai:
    if not openai_service._check():
        st.warning("Set **OPENAI_API_KEY** in `.env` to enable AI analysis.")
    else:
        # Track cache keys so the export section can always find them
        cache_key_summary = f"summary_{app_num}"
        cache_key_oa = None
        cache_key_strat = None

        # ── Prosecution narrative ──────────────────────────────────────────────
        st.markdown("### Prosecution Summary")
        if cache_key_summary not in st.session_state:
            with st.spinner("Generating prosecution summary…"):
                # Build a compact context string for the AI
                event_summary = "\n".join(
                    f"{e.get('eventDate','')[:10]}  [{e.get('eventCode','')}]  {e.get('eventDescriptionText','')}"
                    for e in events[:30]
                )
                ctx = (
                    f"Application: {app_num}\n"
                    f"Title: {m.get('inventionTitle','')}\n"
                    f"Outcome: {outcome}\n"
                    f"Examiner: {examiner_name}  Art Unit: {art_unit}\n"
                    f"Assignee: {assignee}\n"
                    f"Filed: {m.get('filingDate','')[:10]}\n"
                    f"Office actions: {count_office_actions(app_data)}  "
                    f"RCEs: {count_rces(app_data)}  "
                    f"Pendency: {pendency_months(app_data)} months\n\n"
                    f"Prosecution events:\n{event_summary}"
                )
                if examiner_stats:
                    ctx += (
                        f"\n\nExaminer profile: {examiner_stats['band']} "
                        f"({examiner_stats['score']}/100), "
                        f"{examiner_stats['allowance_rate']}% allowance rate, "
                        f"{examiner_stats['avg_oa']} avg OAs."
                    )
                sys_p = (
                    "You are a senior patent attorney. Given the prosecution history below, "
                    "write a 2-3 paragraph narrative that: (1) describes what happened in prosecution, "
                    "(2) notes the examiner's difficulty and approach, and (3) gives a practical assessment "
                    "of the current position and recommended next steps. Be specific and professional."
                )
                summary = openai_service._chat(sys_p, ctx)
                st.session_state[cache_key_summary] = summary
        st.markdown(st.session_state[cache_key_summary])

        st.markdown("---")

        # ── Office Action analysis ─────────────────────────────────────────────
        st.markdown("### Most Recent Office Action")
        oa_docs = uspto_api.get_oa_documents(app_num)
        if not oa_docs:
            st.info("No office actions found in the file wrapper for this application.")
        else:
            latest_oa = oa_docs[0]
            oa_label = f"{latest_oa.get('mailDate','')[:10]}  {latest_oa.get('documentCode','')}  {latest_oa.get('documentDescription','')}"
            st.caption(f"Loaded: **{oa_label}**")

            cache_key_oa = f"oa_analysis_{app_num}_{latest_oa.get('documentIdentifier', '')}"
            if cache_key_oa not in st.session_state:
                with st.spinner("Fetching and analysing the office action…"):
                    oa_text = uspto_api.fetch_oa_text(app_num, latest_oa.get("documentIdentifier",""))
                    if oa_text:
                        analysis = openai_service.analyze_office_action(oa_text)
                        st.session_state[cache_key_oa] = (oa_text, analysis)
                    else:
                        st.session_state[cache_key_oa] = ("", "Could not extract OA text from this document.")
            oa_text, oa_analysis = st.session_state[cache_key_oa]
            st.markdown(oa_analysis)

            # ── Response strategy ──────────────────────────────────────────────
            if oa_text:
                st.markdown("---")
                st.markdown("### Response Strategy")
                cache_key_strat = f"strategy_{app_num}_{latest_oa.get('documentIdentifier', '')}"
                if cache_key_strat not in st.session_state:
                    with st.spinner("Fetching claims and generating response strategy…"):
                        claims_text = uspto_api.fetch_claims_text(app_num)
                        if claims_text:
                            strategy = openai_service.response_strategy(oa_text, claims_text)
                        else:
                            strategy = openai_service.response_strategy(oa_text, "(claims not available)")
                        st.session_state[cache_key_strat] = strategy
                st.markdown(st.session_state[cache_key_strat])

                # Allow editing claims for custom strategy
                with st.expander("✏️ Custom response strategy with different claims"):
                    custom_claims = st.text_area("Paste amended claims here", height=200, key="custom_claims")
                    if st.button("Generate strategy for these claims") and custom_claims:
                        with st.spinner("Generating…"):
                            st.markdown(openai_service.response_strategy(oa_text, custom_claims))

        # ── Export ────────────────────────────────────────────────────────────
        st.markdown("---")
        export_parts = [
            f"# Patent Analysis: {app_num}",
            f"**{m.get('inventionTitle', '')}**",
            f"Examiner: {examiner_name} | Art Unit: {art_unit}",
            f"Status: {m.get('applicationStatusDescriptionText', outcome.title())}",
            "",
        ]
        if cache_key_summary in st.session_state:
            export_parts += ["## Prosecution Summary", st.session_state[cache_key_summary], ""]
        if cache_key_oa and cache_key_oa in st.session_state:
            _, _oa_analysis = st.session_state[cache_key_oa]
            export_parts += ["## Office Action Analysis", _oa_analysis, ""]
        if cache_key_strat and cache_key_strat in st.session_state:
            export_parts += ["## Response Strategy", st.session_state[cache_key_strat], ""]
        st.download_button(
            "⬇️ Export Analysis",
            data="\n".join(export_parts),
            file_name=f"analysis_{app_num}.md",
            mime="text/markdown",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 2 – Prosecution Timeline
# ═══════════════════════════════════════════════════════════════════════════════

with tab_timeline:
    if not events:
        st.info("No prosecution events found.")
    else:
        st.markdown(f"**{len(events)} prosecution events** (most recent first)")
        for e in reversed(events):
            code = e.get("eventCode", "")
            icon = _event_icon(code)
            date = (e.get("eventDate") or "")[:10]
            desc = e.get("eventDescriptionText", "")
            st.markdown(
                f"{icon} &nbsp; `{date}` &nbsp; **{code}** &nbsp; — &nbsp; {desc}",
                unsafe_allow_html=False,
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 3 – Documents
# ═══════════════════════════════════════════════════════════════════════════════

with tab_docs:
    with st.spinner("Loading document list…"):
        docs = uspto_api.get_all_documents(app_num)

    if not docs:
        st.info("No documents found in the file wrapper.")
    else:
        st.markdown(f"**{len(docs)} documents** in the file wrapper")
        for doc in docs:
            code = doc.get("documentCode", "")
            desc = doc.get("documentDescription", code)
            date = (doc.get("mailDate") or "")[:10]
            doc_id = doc.get("documentIdentifier", "")
            has_xml = any(
                p.get("mimeTypeCategory") == "XML"
                for p in (doc.get("pageBag") or [])
            )
            has_pdf = any(
                p.get("mimeTypeCategory") == "PDF"
                for p in (doc.get("pageBag") or [])
            )

            col_info, col_btns = st.columns([4, 1])
            with col_info:
                st.markdown(f"**{date}** &nbsp; `{code}` &nbsp; {desc}")
            with col_btns:
                if has_xml and doc_id:
                    with st.expander("View text"):
                        with st.spinner("Extracting…"):
                            text = uspto_api.fetch_document_text(app_num, doc_id)
                        if text:
                            st.text_area("", value=text, height=300, key=f"doc_{doc_id}")
                        else:
                            st.warning("Could not extract text.")
