"""
Prosecution Hub — the central workspace for any active application.

Enter an application number → see full prosecution context, examiner difficulty
inline, AI-narrated prosecution summary, and instant OA analysis.
"""

import streamlit as st
from utils.auth import require_auth, sidebar_user
from utils.ui import inject_global_css, score_card_html, timeline_html, score_badge
from services import uspto_api, openai_service
from services.scoring import compute_examiner_score
from services.uspto_api import (
    meta, get_outcome, get_patent_number, get_assignee,
    count_office_actions, count_rces, pendency_months,
)

require_auth()
inject_global_css()
sidebar_user()

st.title("⚖️ Prosecution Hub")
st.caption("Look up any application — see the full prosecution picture and get AI-powered next steps.")

# ── Search ────────────────────────────────────────────────────────────────────

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
        search = st.form_submit_button("Load application", use_container_width=True, type="primary")

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

_STATUS_COLOR = {"patented": "#059669", "abandoned": "#dc2626", "pending": "#2563eb"}
_STATUS_ICON  = {"patented": "✅", "abandoned": "❌", "pending": "🔄"}

status_color = _STATUS_COLOR.get(outcome, "#64748b")
status_icon  = _STATUS_ICON.get(outcome, "❓")

st.markdown(f"## {status_icon} {m.get('inventionTitle', app_num)}")

assignee = get_assignee(app_data)
if assignee:
    st.markdown(
        f"<p style='color:#64748b;font-size:0.85rem;margin:-0.5rem 0 0.75rem;'>Assignee: <strong>{assignee}</strong></p>",
        unsafe_allow_html=True,
    )

col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("Status", m.get("applicationStatusDescriptionText", outcome.title()))
col_b.metric("Filed", (m.get("filingDate") or "")[:10])
col_c.metric("Art Unit", art_unit or "—")
col_d.metric("Patent №" if patent else "Office Actions", patent if patent else count_office_actions(app_data))

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
        st.markdown("#### Examiner")
        if examiner_stats:
            st.markdown(
                score_card_html(
                    examiner_stats["score"],
                    examiner_stats["band"],
                    examiner_stats["color_hex"],
                    total=examiner_stats.get("total", 0),
                ),
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Allowance Rate", f"{examiner_stats['allowance_rate']}%")
            m2.metric("Avg Office Actions", examiner_stats["avg_oa"])
            m3.metric("Avg Pendency", f"{examiner_stats['avg_pendency']} mo")
            m4.metric("RCE Rate", f"{examiner_stats['rce_rate']}%" if examiner_stats["rce_rate"] is not None else "—")
        else:
            st.write(f"**{examiner_name}** (no stats available)")
    with col_link:
        st.markdown(f"<p style='font-weight:600;color:#1a3a5c;margin-bottom:0.5rem;'>{examiner_name}</p>", unsafe_allow_html=True)
        if st.button("View full examiner profile →", use_container_width=True):
            st.session_state["examiner_prefill"] = examiner_name
            st.switch_page("pages/2_Examiner_Intel.py")

st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_timeline, tab_ai, tab_docs = st.tabs(["📋 Prosecution Timeline", "🤖 AI Analysis", "📄 Documents"])


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 1 – Prosecution Timeline
# ═══════════════════════════════════════════════════════════════════════════════

with tab_timeline:
    if events:
        st.markdown(
            f"<p style='color:#64748b;font-size:0.85rem;margin-bottom:1rem;'>"
            f"<strong>{len(events)}</strong> prosecution events — most recent first</p>",
            unsafe_allow_html=True,
        )
    st.markdown(timeline_html(events), unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Tab 2 – AI Analysis
# ═══════════════════════════════════════════════════════════════════════════════

with tab_ai:
    if not openai_service._check():
        st.warning("Set **OPENAI_API_KEY** in `.env` to enable AI analysis.")
    else:
        from concurrent.futures import ThreadPoolExecutor as _TPE

        cache_key_summary = f"summary_{app_num}"
        _ai_requested_key = f"ai_requested_{app_num}"

        # Streamlit renders all tab content on every page load, even when a
        # different tab is active.  Gate AI calls behind an explicit button so
        # we only hit the API (and show spinners) when the user actually wants
        # the analysis — not silently on every Timeline-tab visit.
        if cache_key_summary not in st.session_state and not st.session_state.get(_ai_requested_key):
            st.markdown(
                "<p style='color:#64748b;font-size:0.875rem;'>Review the prosecution timeline, "
                "then generate AI analysis when ready.</p>",
                unsafe_allow_html=True,
            )
            if st.button("Generate AI Analysis", type="primary", key="btn_gen_ai"):
                st.session_state[_ai_requested_key] = True
                st.rerun()
        else:

        # ── from here AI has been requested or results are already cached ──

            oa_docs = uspto_api.get_oa_documents(app_num)
            latest_oa = oa_docs[0] if oa_docs else None
            _doc_id = latest_oa.get("documentIdentifier", "") if latest_oa else ""
            cache_key_oa    = f"oa_analysis_{app_num}_{_doc_id}" if latest_oa else None
            cache_key_strat = f"strategy_{app_num}_{_doc_id}"   if latest_oa else None

            need_summary = cache_key_summary not in st.session_state
            need_oa      = bool(cache_key_oa and cache_key_oa not in st.session_state)

            event_summary = "\n".join(
                f"{e.get('eventDate','')[:10]}  [{e.get('eventCode','')}]  {e.get('eventDescriptionText','')}"
                for e in events[:30]
            )
            _ctx = (
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
                _ctx += (
                    f"\n\nExaminer profile: {examiner_stats['band']} "
                    f"({examiner_stats['score']}/100), "
                    f"{examiner_stats['allowance_rate']}% allowance rate, "
                    f"{examiner_stats['avg_oa']} avg OAs."
                )
            _sys_p = (
                "You are a senior patent attorney. Given the prosecution history below, "
                "write a 2-3 paragraph narrative that: (1) describes what happened in prosecution, "
                "(2) notes the examiner's difficulty and approach, and (3) gives a practical assessment "
                "of the current position and recommended next steps. Be specific and professional."
            )

            def _gen_summary():
                try:
                    return openai_service._chat(_sys_p, _ctx)
                except Exception as e:
                    return f"⚠️ AI request failed: {e}"

            def _fetch_and_analyse_oa():
                try:
                    text = uspto_api.fetch_oa_text(app_num, _doc_id)
                    analysis = openai_service.analyze_office_action(text)
                    return text, analysis
                except Exception as e:
                    return "", f"⚠️ Could not analyse office action: {e}"

            tasks = {}
            if need_summary:
                tasks["summary"] = _gen_summary
            if need_oa:
                tasks["oa"] = _fetch_and_analyse_oa

            if tasks:
                _msgs = {
                    frozenset(["summary", "oa"]): "Generating prosecution summary and office action analysis…",
                    frozenset(["summary"]):       "Generating prosecution summary…",
                    frozenset(["oa"]):            "Fetching and analysing the office action…",
                }
                with st.spinner(_msgs[frozenset(tasks)]):
                    with _TPE(max_workers=len(tasks)) as _pool:
                        _futs = {k: _pool.submit(fn) for k, fn in tasks.items()}
                        for k, fut in _futs.items():
                            try:
                                result = fut.result()
                            except Exception as exc:
                                result = f"⚠️ {exc}"
                            if k == "summary":
                                st.session_state[cache_key_summary] = result
                            elif k == "oa":
                                st.session_state[cache_key_oa] = result if isinstance(result, tuple) else ("", result)

            st.markdown("### Prosecution Summary")
            st.markdown(st.session_state.get(cache_key_summary, ""))
            st.markdown("---")

            st.markdown("### Most Recent Office Action")
            if not oa_docs:
                st.info("No office actions found in the file wrapper for this application.")
            else:
                oa_label = (
                    f"{latest_oa.get('mailDate','')[:10]}  "
                    f"{latest_oa.get('documentCode','')}  "
                    f"{latest_oa.get('documentDescription','')}"
                )
                st.caption(f"Loaded: **{oa_label}**")
                oa_text, oa_analysis = st.session_state.get(cache_key_oa, ("", ""))
                st.markdown(oa_analysis)

                if oa_text:
                    st.markdown("---")
                    st.markdown("### Response Strategy")
                    if cache_key_strat not in st.session_state:
                        with st.spinner("Fetching claims and generating response strategy…"):
                            try:
                                claims_text = uspto_api.fetch_claims_text(app_num)
                            except Exception:
                                claims_text = ""
                            strategy = openai_service.response_strategy(
                                oa_text,
                                claims_text if claims_text else "(claims not available)",
                            )
                            st.session_state[cache_key_strat] = strategy
                    st.markdown(st.session_state[cache_key_strat])

                    with st.expander("✏️ Custom response strategy with different claims"):
                        custom_claims = st.text_area("Paste amended claims here", height=200, key="custom_claims")
                        if st.button("Generate strategy for these claims") and custom_claims:
                            with st.spinner("Generating…"):
                                st.markdown(openai_service.response_strategy(oa_text, custom_claims))

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
# Tab 3 – Documents
# ═══════════════════════════════════════════════════════════════════════════════

with tab_docs:
    with st.spinner("Loading document list…"):
        docs = uspto_api.get_all_documents(app_num)

    if not docs:
        st.info("No documents found in the file wrapper.")
    else:
        st.markdown(
            f"<p style='color:#64748b;font-size:0.85rem;margin-bottom:0.75rem;'>"
            f"<strong>{len(docs)}</strong> documents — PDFs fetched directly via USPTO API</p>",
            unsafe_allow_html=True,
        )

        for doc in docs:
            code   = doc.get("documentCode", "")
            desc   = doc.get("documentDescription", code)
            date   = (doc.get("mailDate") or "")[:10]
            doc_id = doc.get("documentIdentifier", "")
            has_xml = any(
                p.get("mimeTypeCategory") == "XML"
                for p in (doc.get("pageBag") or [])
            )
            has_pdf = any(
                p.get("mimeTypeCategory") == "PDF"
                for p in (doc.get("pageBag") or [])
            )

            col_info, col_pdf = st.columns([5, 1])
            with col_info:
                st.markdown(
                    f"<div style='padding:0.5rem 0;border-bottom:1px solid #f1f5f9;'>"
                    f"<div style='font-size:0.8rem;color:#64748b;margin-bottom:0.2rem;'>{date}"
                    f"&nbsp;&nbsp;<code style='background:#f1f5f9;padding:2px 7px;border-radius:4px;"
                    f"font-size:0.75rem;color:#1e293b;'>{code}</code></div>"
                    f"<div style='font-size:1rem;color:#1e293b;font-weight:500;"
                    f"white-space:normal;word-break:break-word;'>{desc}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with col_pdf:
                if has_pdf and doc_id:
                    key_pdf = f"pdf_data_{doc_id}"
                    if key_pdf not in st.session_state:
                        if st.button("Fetch PDF", key=f"btn_pdf_{doc_id}", use_container_width=True):
                            with st.spinner("Downloading…"):
                                try:
                                    st.session_state[key_pdf] = uspto_api.fetch_pdf(app_num, doc_id)
                                    st.rerun()
                                except Exception as e:
                                    st.warning(f"PDF unavailable: {e}")
                    else:
                        st.download_button(
                            "⬇️ Save PDF",
                            data=st.session_state[key_pdf],
                            file_name=f"{code}_{date}_{doc_id}.pdf",
                            mime="application/pdf",
                            key=f"dl_pdf_{doc_id}",
                            use_container_width=True,
                        )

            # XML text preview sits below the row at full width
            if has_xml and doc_id:
                with st.expander(f"Preview text — {code} {date}"):
                    with st.spinner("Extracting…"):
                        try:
                            text = uspto_api.fetch_document_text(app_num, doc_id)
                        except Exception as e:
                            text = ""
                            st.warning(f"Could not fetch document: {e}")
                    if text:
                        st.text_area("", value=text, height=300, key=f"doc_{doc_id}")
