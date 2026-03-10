"""
Portfolio — company prosecution health dashboard.

Enter a company name → instant portfolio overview with outcome distribution,
filing trends, examiner concentration, art unit breakdown, and AI executive summary.
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
from services.uspto_api import meta, get_outcome, get_patent_number, get_assignee

require_auth()
inject_global_css()
sidebar_user()

st.title("💼 Portfolio")
st.caption("Prosecution health dashboard for any company or assignee — powered by live USPTO data.")


# ── Disambiguation helper ─────────────────────────────────────────────────────

def _norm(name: str) -> str:
    return _re.sub(r"[.,\s]+", " ", name.lower()).strip()


def _run_disambiguation(term: str) -> list[dict]:
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

    # Fetch ODP filing counts sequentially — USPTO burst limit is 1 (no parallel requests).
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


# ── Step state ────────────────────────────────────────────────────────────────

prefill    = st.session_state.pop("portfolio_prefill", "") or ""
search_term = st.session_state.get("portfolio_search_term", prefill)
candidates  = st.session_state.get("portfolio_candidates")
confirmed   = st.session_state.get("portfolio_confirmed", "")

# ── Search form ───────────────────────────────────────────────────────────────

with st.form("portfolio_search_form"):
    col_i, col_b = st.columns([4, 1])
    with col_i:
        entered = st.text_input(
            "Company name",
            value=search_term,
            placeholder="e.g. Apple Inc, Google LLC, Microsoft Corporation",
            label_visibility="collapsed",
        )
    with col_b:
        find_btn = st.form_submit_button("Find candidates", use_container_width=True, type="primary")

if find_btn and entered:
    st.session_state.pop("portfolio_candidates", None)
    st.session_state.pop("portfolio_confirmed", None)
    st.session_state["portfolio_search_term"] = entered
    with st.spinner("Searching USPTO and PatentsView for matching companies…"):
        found = _run_disambiguation(entered)
    st.session_state["portfolio_candidates"] = found
    candidates, confirmed, search_term = found, "", entered
    st.rerun()

if prefill and candidates is None:
    st.session_state["portfolio_search_term"] = prefill
    with st.spinner("Searching USPTO and PatentsView for matching companies…"):
        found = _run_disambiguation(prefill)
    st.session_state["portfolio_candidates"] = found
    candidates, search_term = found, prefill

# ── Disambiguation table ──────────────────────────────────────────────────────

if not confirmed:
    if candidates is None:
        st.info("Enter a company or assignee name to get started.")
        st.stop()

    if not candidates:
        st.error(f"No matching companies found for **{search_term}**. Try a different name or spelling.")
        st.stop()

    st.markdown("### Select company to analyse")
    st.caption(
        f"Found **{len(candidates)}** matching name variants in the USPTO database. "
        "Select a row then click **Analyse**."
    )

    cand_df = pd.DataFrame(candidates)
    evt = st.dataframe(
        cand_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    selected_name = ""
    if evt and evt.selection.rows:
        selected_name = candidates[evt.selection.rows[0]]["Name"]
        st.success(f"Selected: **{selected_name}**")

    col_btn, _ = st.columns([2, 3])
    if col_btn.button(
        "Analyse this company →",
        disabled=not selected_name,
        type="primary",
        use_container_width=True,
    ):
        st.session_state["portfolio_confirmed"] = selected_name
        st.rerun()

    st.stop()

# ── Confirmed — show which company + allow change ─────────────────────────────

company = confirmed
col_hdr, col_chg = st.columns([5, 1])
col_hdr.caption(f"Analysing: **{company}**")
if col_chg.button("Change company", use_container_width=True):
    st.session_state.pop("portfolio_confirmed", None)
    st.rerun()

# ── Fetch full portfolio ──────────────────────────────────────────────────────

with st.spinner(f"Fetching portfolio data for {company}…"):
    apps = uspto_api.search_by_assignee(company)

if not apps:
    st.error(f"No applications found for **{company}**. Try a variation of the name.")
    st.stop()

stats = compute_examiner_score(apps)

# ── Header & metrics ──────────────────────────────────────────────────────────

st.markdown(f"## {company}")
st.caption(f"Analysis based on {len(apps):,} most recent applications")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total (sample)", f"{stats['total']:,}")
m2.metric("Patented", f"{stats['patented']:,}")
m3.metric("Abandoned", f"{stats['abandoned']:,}")
m4.metric("Allowance Rate", f"{stats['allowance_rate']}%")
m5.metric("Avg Pendency", f"{stats['avg_pendency']} mo")

st.markdown("---")

# ── AI Executive Summary ──────────────────────────────────────────────────────

portfolio_summary_text = ""
if openai_service._check():
    st.markdown("### AI Executive Summary")
    cache_key = f"portfolio_summary_{company}"
    if cache_key not in st.session_state:
        with st.spinner("Generating AI executive summary…"):
            report = openai_service.portfolio_summary(company, stats, apps[:50])
            st.session_state[cache_key] = report
    portfolio_summary_text = st.session_state[cache_key]
    st.markdown(portfolio_summary_text)

    export_md = "\n".join([
        f"# Portfolio Analysis: {company}",
        f"Sample: {stats['total']} applications | "
        f"Patented: {stats['patented']} | Abandoned: {stats['abandoned']} | Pending: {stats['pending']}",
        f"Allowance Rate: {stats['allowance_rate']}% | "
        f"Avg Pendency: {stats['avg_pendency']} mo | "
        f"Avg OAs: {stats['avg_oa']}",
        "",
        "## AI Executive Summary",
        portfolio_summary_text,
    ])
    st.download_button(
        "⬇️ Export Portfolio Summary",
        data=export_md,
        file_name=f"portfolio_{company.replace(' ', '_')[:40]}.md",
        mime="text/markdown",
    )
    st.markdown("---")
else:
    st.info("Add **OPENAI_API_KEY** to `.env` to enable AI executive summaries.")

# ── Charts row 1: trend + outcomes ────────────────────────────────────────────

col1, col2 = st.columns(2)

with col1:
    st.markdown("#### Filing Trend")
    years = Counter(
        str(meta(a).get("filingDate", ""))[:4]
        for a in apps if meta(a).get("filingDate", "")
    )
    yr_df = pd.DataFrame(sorted(years.items()), columns=["Year", "Applications"])
    yr_df = yr_df[yr_df["Year"].str.isdigit()]
    fig_trend = px.area(
        yr_df, x="Year", y="Applications",
        color_discrete_sequence=["#2563eb"],
    )
    fig_trend.update_traces(line=dict(width=2), fillcolor="rgba(37,99,235,0.12)")
    fig_trend.update_layout(**PLOTLY_THEME, height=290)
    st.plotly_chart(fig_trend, use_container_width=True)

with col2:
    st.markdown("#### Outcomes")
    fig_donut = px.pie(
        names=["Patented", "Abandoned", "Pending"],
        values=[stats["patented"], stats["abandoned"], stats["pending"]],
        color_discrete_map=OUTCOME_COLORS,
        hole=0.55,
    )
    fig_donut.update_layout(**PLOTLY_THEME, showlegend=True, height=290)
    st.plotly_chart(fig_donut, use_container_width=True)

# ── Charts row 2: top examiners + art units ───────────────────────────────────

col3, col4 = st.columns(2)

with col3:
    st.markdown("#### Top Examiners")
    examiners = Counter(meta(a).get("examinerNameText", "") for a in apps)
    top_ex = examiners.most_common(15)
    if top_ex:
        ex_df = pd.DataFrame(top_ex, columns=["Examiner", "Applications"])
        ex_df["Examiner"] = ex_df["Examiner"].apply(lambda n: n.split(",")[0] if n else n)
        fig_ex = px.bar(
            ex_df, x="Applications", y="Examiner", orientation="h",
            color_discrete_sequence=["#2563eb"],
        )
        fig_ex.update_layout(**PLOTLY_THEME, height=360, yaxis=dict(autorange="reversed", showgrid=False))
        st.plotly_chart(fig_ex, use_container_width=True)
    if st.button("Explore an examiner's full profile →"):
        st.switch_page("pages/2_Examiner_Intel.py")

with col4:
    st.markdown("#### Art Unit Distribution")
    art_units = Counter(meta(a).get("groupArtUnitNumber", "") for a in apps)
    top_au = art_units.most_common(15)
    if top_au:
        au_df = pd.DataFrame(top_au, columns=["Art Unit", "Applications"])
        au_df = au_df[au_df["Art Unit"].str.len() > 0]
        fig_au = px.bar(
            au_df, x="Applications", y="Art Unit", orientation="h",
            color_discrete_sequence=["#7c3aed"],
        )
        fig_au.update_layout(**PLOTLY_THEME, height=360, yaxis=dict(autorange="reversed", showgrid=False))
        st.plotly_chart(fig_au, use_container_width=True)

st.markdown("---")

# ── Application table ──────────────────────────────────────────────────────────

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

event = st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
)
if event and event.selection.rows:
    selected_idx = event.selection.rows[0]
    selected_app = df.iloc[selected_idx]["App №"]
    st.session_state["detail_app_num"] = selected_app
    st.switch_page("pages/1_Prosecution_Hub.py")
