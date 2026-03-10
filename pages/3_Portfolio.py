"""
Portfolio — prosecution health dashboards.

Two tabs:
  Company / Assignee — portfolio overview for any patent owner.
  Law Firm           — prosecution practice overview for any correspondent law firm.
"""

import re as _re
from concurrent.futures import ThreadPoolExecutor

import streamlit as st
import pandas as pd
import plotly.express as px
from collections import Counter

from utils.auth import require_auth, sidebar_user
from utils.ui import inject_global_css, PLOTLY_THEME, OUTCOME_COLORS
from services import uspto_api, openai_service, patentsview_api
from services.scoring import compute_examiner_score
from services.uspto_api import meta, get_outcome, get_patent_number

require_auth()
inject_global_css()
sidebar_user()

st.title("💼 Portfolio")
st.caption("Prosecution health dashboards — company assignee or law firm — powered by live USPTO data.")


# ── Shared helpers ────────────────────────────────────────────────────────────

def _norm(name: str) -> str:
    return _re.sub(r"[.,\s]+", " ", name.lower()).strip()


def _charts_trend_outcomes(apps: list, height: int = 290) -> None:
    """Filing trend area chart + outcomes donut, side by side."""
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Filing Trend")
        years = Counter(
            str(meta(a).get("filingDate", ""))[:4]
            for a in apps if meta(a).get("filingDate", "")
        )
        yr_df = pd.DataFrame(sorted(years.items()), columns=["Year", "Applications"])
        yr_df = yr_df[yr_df["Year"].str.isdigit()]
        fig = px.area(yr_df, x="Year", y="Applications", color_discrete_sequence=["#2563eb"])
        fig.update_traces(line=dict(width=2), fillcolor="rgba(37,99,235,0.12)")
        fig.update_layout(**PLOTLY_THEME, height=height)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("#### Outcomes")
        stats = compute_examiner_score(apps)
        fig = px.pie(
            names=["Patented", "Abandoned", "Pending"],
            values=[stats["patented"], stats["abandoned"], stats["pending"]],
            color_discrete_map=OUTCOME_COLORS,
            hole=0.55,
        )
        fig.update_layout(**PLOTLY_THEME, showlegend=True, height=height)
        st.plotly_chart(fig, use_container_width=True)


def _bar_chart(data: list[tuple], x_label: str, y_label: str, color: str, height: int = 360) -> None:
    """Horizontal bar chart from a list of (label, count) tuples."""
    df = pd.DataFrame(data, columns=[y_label, x_label])
    df = df[df[y_label].astype(str).str.len() > 0]
    fig = px.bar(df, x=x_label, y=y_label, orientation="h", color_discrete_sequence=[color])
    fig.update_layout(**{**PLOTLY_THEME, "height": height, "yaxis": dict(autorange="reversed", showgrid=False)})
    st.plotly_chart(fig, use_container_width=True)


# ── Tab layout ────────────────────────────────────────────────────────────────

tab_co, tab_lf = st.tabs(["🏢 Company / Assignee", "⚖️ Law Firm"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 – COMPANY / ASSIGNEE
# ══════════════════════════════════════════════════════════════════════════════

def _render_company_tab() -> None:

    def _disambiguate(term: str) -> list[dict]:
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_odp = pool.submit(uspto_api.get_applicant_name_variants, term)
            fut_pv  = pool.submit(patentsview_api.get_assignee_org_variants, term)
            odp_variants = fut_odp.result()
            pv_variants  = fut_pv.result()

        if not odp_variants:
            return []

        cands: dict[str, dict] = {}
        for name, cnt in odp_variants.items():
            cands[_norm(name)] = {"Name": name, "_sample": cnt, "Granted (PatentsView)": 0}
        for pv_name, cnt in pv_variants.items():
            key = _norm(pv_name)
            if key in cands:
                cands[key]["Granted (PatentsView)"] = cnt

        candidate_list = list(cands.values())[:8]
        for c in candidate_list:
            try:
                c["ODP Filings"] = uspto_api.odp_filing_count(c["Name"])
            except Exception:
                c["ODP Filings"] = c["_sample"]

        rows = [
            {
                "Name": c["Name"],
                "ODP Filings": max(c.get("ODP Filings", 0), c["_sample"]),
                "Granted (PatentsView)": c["Granted (PatentsView)"],
            }
            for c in candidate_list
        ]
        rows.sort(key=lambda r: r["ODP Filings"], reverse=True)
        return rows

    # ── State ────────────────────────────────────────────────────────────────
    prefill     = st.session_state.pop("portfolio_prefill", "") or ""
    search_term = st.session_state.get("co_search_term", prefill)
    candidates  = st.session_state.get("co_candidates")
    confirmed   = st.session_state.get("co_confirmed", "")

    # ── Search form ──────────────────────────────────────────────────────────
    with st.form("co_search_form"):
        col_i, col_b = st.columns([4, 1])
        with col_i:
            entered = st.text_input(
                "Company name", value=search_term,
                placeholder="e.g. Apple Inc, Google LLC, Microsoft Corporation",
                label_visibility="collapsed",
            )
        with col_b:
            find_btn = st.form_submit_button("Find candidates", use_container_width=True, type="primary")

    if find_btn and entered:
        st.session_state.pop("co_candidates", None)
        st.session_state.pop("co_confirmed", None)
        st.session_state["co_search_term"] = entered
        with st.spinner("Searching USPTO and PatentsView for matching companies…"):
            found = _disambiguate(entered)
        st.session_state["co_candidates"] = found
        candidates, confirmed, search_term = found, "", entered
        st.rerun()

    if prefill and candidates is None:
        st.session_state["co_search_term"] = prefill
        with st.spinner("Searching USPTO and PatentsView for matching companies…"):
            found = _disambiguate(prefill)
        st.session_state["co_candidates"] = found
        candidates, search_term = found, prefill

    # ── Disambiguation ───────────────────────────────────────────────────────
    if not confirmed:
        if candidates is None:
            st.info("Enter a company or assignee name to get started.")
            return
        if not candidates:
            st.error(f"No matching companies found for **{search_term}**. Try a different name or spelling.")
            return

        st.markdown("### Select company to analyse")
        st.caption(
            f"Found **{len(candidates)}** matching name variants in the USPTO database. "
            "Select a row then click **Analyse**."
        )
        cand_df = pd.DataFrame(candidates)
        evt = st.dataframe(cand_df, use_container_width=True, hide_index=True,
                           on_select="rerun", selection_mode="single-row")
        selected_name = ""
        if evt and evt.selection.rows:
            selected_name = candidates[evt.selection.rows[0]]["Name"]
            st.success(f"Selected: **{selected_name}**")

        col_btn, _ = st.columns([2, 3])
        if col_btn.button("Analyse this company →", disabled=not selected_name,
                          type="primary", use_container_width=True):
            st.session_state["co_confirmed"] = selected_name
            st.rerun()
        return

    # ── Confirmed — fetch & display ──────────────────────────────────────────
    company = confirmed
    col_hdr, col_chg = st.columns([5, 1])
    col_hdr.caption(f"Analysing: **{company}**")
    if col_chg.button("Change company", use_container_width=True, key="co_change"):
        st.session_state.pop("co_confirmed", None)
        st.rerun()

    with st.spinner(f"Fetching portfolio data for {company}…"):
        apps = uspto_api.search_by_assignee(company)

    if not apps:
        st.error(f"No applications found for **{company}**. Try a variation of the name.")
        return

    stats = compute_examiner_score(apps)

    st.markdown(f"## {company}")
    st.caption(f"Analysis based on {len(apps):,} most recent applications")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total (sample)", f"{stats['total']:,}")
    m2.metric("Patented", f"{stats['patented']:,}")
    m3.metric("Abandoned", f"{stats['abandoned']:,}")
    m4.metric("Allowance Rate", f"{stats['allowance_rate']}%")
    m5.metric("Avg Pendency", f"{stats['avg_pendency']} mo")

    _charts_trend_outcomes(apps)

    col3, col4 = st.columns(2)
    with col3:
        st.markdown("#### Top Examiners")
        top_ex = Counter(meta(a).get("examinerNameText", "") for a in apps).most_common(15)
        if top_ex:
            _bar_chart(
                [(n.split(",")[0] if n else n, c) for n, c in top_ex],
                "Applications", "Examiner", "#2563eb",
            )
        if st.button("Explore an examiner's full profile →", key="co_ex_link"):
            st.switch_page("pages/2_Examiner_Intel.py")

    with col4:
        st.markdown("#### Art Unit Distribution")
        top_au = Counter(meta(a).get("groupArtUnitNumber", "") for a in apps).most_common(15)
        if top_au:
            _bar_chart(top_au, "Applications", "Art Unit", "#7c3aed")

    st.markdown("---")

    st.markdown("#### Applications")
    rows = []
    for a in apps:
        m_ = meta(a)
        rows.append({
            "App №": a.get("applicationNumberText", ""),
            "Title": str(m_.get("inventionTitle", ""))[:60],
            "Filed": (m_.get("filingDate") or "")[:10],
            "Art Unit": m_.get("groupArtUnitNumber", ""),
            "Examiner": (m_.get("examinerNameText") or "").split(",")[0],
            "Status": m_.get("applicationStatusDescriptionText", ""),
            "Patent №": get_patent_number(a),
        })
    df = pd.DataFrame(rows)
    event = st.dataframe(df, use_container_width=True, hide_index=True,
                         on_select="rerun", selection_mode="single-row")
    if event and event.selection.rows:
        st.session_state["detail_app_num"] = df.iloc[event.selection.rows[0]]["App №"]
        st.switch_page("pages/1_Prosecution_Hub.py")

    st.markdown("---")

    # AI last
    portfolio_summary_text = ""
    if openai_service._check():
        st.markdown("### AI Executive Summary")
        cache_key = f"portfolio_summary_{company}"
        if cache_key not in st.session_state:
            with st.spinner("Generating AI executive summary…"):
                st.session_state[cache_key] = openai_service.portfolio_summary(company, stats, apps[:50])
        portfolio_summary_text = st.session_state[cache_key]
        st.markdown(portfolio_summary_text)

        export_md = "\n".join([
            f"# Portfolio Analysis: {company}",
            f"Sample: {stats['total']} applications | Patented: {stats['patented']} | "
            f"Abandoned: {stats['abandoned']} | Pending: {stats['pending']}",
            f"Allowance Rate: {stats['allowance_rate']}% | Avg Pendency: {stats['avg_pendency']} mo | "
            f"Avg OAs: {stats['avg_oa']}",
            "", "## AI Executive Summary", portfolio_summary_text,
        ])
        st.download_button(
            "⬇️ Export Portfolio Summary", data=export_md,
            file_name=f"portfolio_{company.replace(' ', '_')[:40]}.md",
            mime="text/markdown",
        )
    else:
        st.info("Add **OPENAI_API_KEY** to `.env` to enable AI executive summaries.")


with tab_co:
    _render_company_tab()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 – LAW FIRM
# ══════════════════════════════════════════════════════════════════════════════

def _render_law_firm_tab() -> None:

    def _disambiguate_firm(term: str) -> list[dict]:
        """Return candidate law firm name rows with ODP filing counts."""
        variants = uspto_api.get_law_firm_name_variants(term)
        if not variants:
            return []

        candidate_list = [{"Name": name, "_sample": cnt} for name, cnt in variants.items()][:8]
        for c in candidate_list:
            try:
                c["ODP Filings"] = uspto_api.law_firm_filing_count(c["Name"])
            except Exception:
                c["ODP Filings"] = c["_sample"]

        rows = [
            {"Name": c["Name"], "ODP Filings": max(c.get("ODP Filings", 0), c["_sample"])}
            for c in candidate_list
        ]
        rows.sort(key=lambda r: r["ODP Filings"], reverse=True)
        return rows

    # ── State ────────────────────────────────────────────────────────────────
    search_term = st.session_state.get("lf_search_term", "")
    candidates  = st.session_state.get("lf_candidates")
    confirmed   = st.session_state.get("lf_confirmed", "")

    # ── Search form ──────────────────────────────────────────────────────────
    with st.form("lf_search_form"):
        col_i, col_b = st.columns([4, 1])
        with col_i:
            entered = st.text_input(
                "Law firm name", value=search_term,
                placeholder="e.g. Morrison & Foerster, Fish & Richardson, Fenwick & West",
                label_visibility="collapsed",
            )
        with col_b:
            find_btn = st.form_submit_button("Find candidates", use_container_width=True, type="primary")

    if find_btn and entered:
        st.session_state.pop("lf_candidates", None)
        st.session_state.pop("lf_confirmed", None)
        st.session_state["lf_search_term"] = entered
        with st.spinner("Searching USPTO for matching law firms…"):
            found = _disambiguate_firm(entered)
        st.session_state["lf_candidates"] = found
        candidates, confirmed, search_term = found, "", entered
        st.rerun()

    # ── Disambiguation ───────────────────────────────────────────────────────
    if not confirmed:
        if candidates is None:
            st.info("Enter a law firm name to get started.")
            return
        if not candidates:
            st.error(
                f"No law firm found matching **{search_term}** in the USPTO correspondent data. "
                "Try a shorter or alternate spelling of the firm name."
            )
            return

        st.markdown("### Select law firm to analyse")
        st.caption(
            f"Found **{len(candidates)}** matching name variants in the USPTO database. "
            "Select a row then click **Analyse**."
        )
        cand_df = pd.DataFrame(candidates)
        evt = st.dataframe(cand_df, use_container_width=True, hide_index=True,
                           on_select="rerun", selection_mode="single-row")
        selected_name = ""
        if evt and evt.selection.rows:
            selected_name = candidates[evt.selection.rows[0]]["Name"]
            st.success(f"Selected: **{selected_name}**")

        col_btn, _ = st.columns([2, 3])
        if col_btn.button("Analyse this firm →", disabled=not selected_name,
                          type="primary", use_container_width=True):
            st.session_state["lf_confirmed"] = selected_name
            st.rerun()
        return

    # ── Confirmed — fetch & display ──────────────────────────────────────────
    firm = confirmed
    col_hdr, col_chg = st.columns([5, 1])
    col_hdr.caption(f"Analysing: **{firm}**")
    if col_chg.button("Change firm", use_container_width=True, key="lf_change"):
        st.session_state.pop("lf_confirmed", None)
        st.rerun()

    with st.spinner(f"Fetching prosecution data for {firm}…"):
        apps = uspto_api.search_by_law_firm(firm)

    if not apps:
        st.error(f"No applications found for **{firm}**. Try a variation of the name.")
        return

    stats = compute_examiner_score(apps)

    st.markdown(f"## {firm}")
    st.caption(f"Analysis based on {len(apps):,} most recent applications as correspondent")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total (sample)", f"{stats['total']:,}")
    m2.metric("Patented", f"{stats['patented']:,}")
    m3.metric("Abandoned", f"{stats['abandoned']:,}")
    m4.metric("Allowance Rate", f"{stats['allowance_rate']}%")
    m5.metric("Avg Pendency", f"{stats['avg_pendency']} mo")

    _charts_trend_outcomes(apps)

    col3, col4 = st.columns(2)
    with col3:
        st.markdown("#### Top Clients")
        top_clients = Counter(
            meta(a).get("firstApplicantName", "") for a in apps
        ).most_common(15)
        if top_clients:
            _bar_chart(top_clients, "Applications", "Client", "#059669")

    with col4:
        st.markdown("#### Art Unit Distribution")
        top_au = Counter(meta(a).get("groupArtUnitNumber", "") for a in apps).most_common(15)
        if top_au:
            _bar_chart(top_au, "Applications", "Art Unit", "#7c3aed")

    col5, col6 = st.columns(2)
    with col5:
        st.markdown("#### Top Examiners")
        top_ex = Counter(meta(a).get("examinerNameText", "") for a in apps).most_common(15)
        if top_ex:
            _bar_chart(
                [(n.split(",")[0] if n else n, c) for n, c in top_ex],
                "Applications", "Examiner", "#2563eb",
            )
        if st.button("Explore an examiner's full profile →", key="lf_ex_link"):
            st.switch_page("pages/2_Examiner_Intel.py")

    with col6:
        st.markdown("#### Outcomes by Technology Centre")
        tc_outcomes: dict[str, dict] = {}
        for a in apps:
            m_ = meta(a)
            tc = (m_.get("groupArtUnitNumber") or "")[:2] + "xx"
            outcome = get_outcome(a)
            if tc not in tc_outcomes:
                tc_outcomes[tc] = {"Patented": 0, "Abandoned": 0, "Pending": 0}
            tc_outcomes[tc][outcome.title()] = tc_outcomes[tc].get(outcome.title(), 0) + 1

        if tc_outcomes:
            tc_rows = [
                {"Tech Centre": tc, **counts}
                for tc, counts in sorted(tc_outcomes.items())
                if tc != "xx"
            ]
            tc_df = pd.DataFrame(tc_rows).fillna(0)
            fig_tc = px.bar(
                tc_df, x="Tech Centre",
                y=[c for c in ["Patented", "Abandoned", "Pending"] if c in tc_df.columns],
                color_discrete_map=OUTCOME_COLORS,
                barmode="stack",
            )
            fig_tc.update_layout(**PLOTLY_THEME, height=360)
            st.plotly_chart(fig_tc, use_container_width=True)

    st.markdown("---")

    st.markdown("#### Applications")
    rows = []
    for a in apps:
        m_ = meta(a)
        rows.append({
            "App №": a.get("applicationNumberText", ""),
            "Title": str(m_.get("inventionTitle", ""))[:60],
            "Client": (m_.get("firstApplicantName") or "")[:40],
            "Filed": (m_.get("filingDate") or "")[:10],
            "Art Unit": m_.get("groupArtUnitNumber", ""),
            "Examiner": (m_.get("examinerNameText") or "").split(",")[0],
            "Status": m_.get("applicationStatusDescriptionText", ""),
        })
    df = pd.DataFrame(rows)
    event = st.dataframe(df, use_container_width=True, hide_index=True,
                         on_select="rerun", selection_mode="single-row")
    if event and event.selection.rows:
        st.session_state["detail_app_num"] = df.iloc[event.selection.rows[0]]["App №"]
        st.switch_page("pages/1_Prosecution_Hub.py")

    st.markdown("---")

    # AI last
    if openai_service._check():
        st.markdown("### AI Practice Summary")
        cache_key = f"lf_summary_{firm}"
        if cache_key not in st.session_state:
            with st.spinner("Generating AI practice summary…"):
                st.session_state[cache_key] = openai_service.law_firm_summary(firm, stats, apps[:50])
        lf_summary_text = st.session_state[cache_key]
        st.markdown(lf_summary_text)

        export_md = "\n".join([
            f"# Law Firm Analysis: {firm}",
            f"Sample: {stats['total']} applications | Patented: {stats['patented']} | "
            f"Abandoned: {stats['abandoned']} | Pending: {stats['pending']}",
            f"Allowance Rate: {stats['allowance_rate']}% | Avg Pendency: {stats['avg_pendency']} mo | "
            f"Avg OAs: {stats['avg_oa']}",
            "", "## AI Practice Summary", lf_summary_text,
        ])
        st.download_button(
            "⬇️ Export Practice Summary", data=export_md,
            file_name=f"lawfirm_{firm.replace(' ', '_')[:40]}.md",
            mime="text/markdown",
        )
    else:
        st.info("Add **OPENAI_API_KEY** to `.env` to enable AI practice summaries.")


with tab_lf:
    _render_law_firm_tab()
