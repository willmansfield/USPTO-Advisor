"""
Examiner Intel — examiner difficulty profiles and art unit landscapes.

Two tabs:
  Examiner — full profile with AI brief, stats, trends, and recent applications.
  Art Unit  — overall difficulty score + ranked examiner roster.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter, defaultdict

from utils.auth import require_auth, sidebar_user
from utils.ui import score_badge
from services import uspto_api, openai_service
from services.scoring import compute_examiner_score
from services.uspto_api import meta, get_outcome

require_auth()
sidebar_user()

st.title("🔬 Examiner Intel")
st.caption("Understand who examines your cases — and how to work with them effectively.")


# Pre-fill from cross-page navigation
default_examiner = st.session_state.pop("examiner_prefill", "") or ""

tab_ex, tab_au = st.tabs(["👤 Examiner Profile", "🏛️ Art Unit Explorer"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 – EXAMINER PROFILE
# ══════════════════════════════════════════════════════════════════════════════

with tab_ex:
    with st.form("examiner_form"):
        col_i, col_b = st.columns([4, 1])
        with col_i:
            ex_name = st.text_input(
                "Examiner name",
                value=default_examiner,
                placeholder="Last name — e.g. SMITH — or LAST, FIRST",
                label_visibility="collapsed",
            )
        with col_b:
            ex_search = st.form_submit_button("Search", use_container_width=True)

    if not ex_name:
        st.info("Enter an examiner name to load their profile.")
    else:
        with st.spinner(f"Fetching applications for {ex_name}…"):
            apps = uspto_api.search_by_examiner(ex_name)

        if not apps:
            st.error(f"No applications found for **{ex_name}**.")
        else:
            stats = compute_examiner_score(apps)

            # Canonical name + primary art unit from the data
            names = [meta(a).get("examinerNameText", "") for a in apps]
            name_counts = Counter(n for n in names if n)
            canonical = name_counts.most_common(1)
            canonical_name = canonical[0][0] if canonical else ex_name

            art_units = [meta(a).get("groupArtUnitNumber", "") for a in apps]
            primary_au = Counter(au for au in art_units if au).most_common(1)
            primary_au_code = primary_au[0][0] if primary_au else "—"

            # Disambiguation notice when multiple examiners are mixed in the sample
            unique_names = len(name_counts)
            if unique_names > 1:
                st.info(
                    f"**{len(apps)} applications** across **{unique_names} examiners** matching "
                    f""{ex_name}". Stats reflect the combined sample. "
                    f"For a single examiner use **LAST, FIRST** format (e.g. `{canonical_name}`)."
                )

            # ── Score badge + headline ─────────────────────────────────────────────
            st.markdown(f"## {canonical_name} &nbsp; · &nbsp; Art Unit {primary_au_code}")
            st.markdown(score_badge(stats["score"], stats["band"], stats["color_hex"]),
                        unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            # ── Key metrics ────────────────────────────────────────────────────────
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Applications", stats["total"])
            m2.metric("Allowance Rate", f"{stats['allowance_rate']}%")
            m3.metric("Avg Office Actions", stats["avg_oa"])
            m4.metric("Avg Pendency", f"{stats['avg_pendency']} mo")
            m5.metric("RCE Rate", f"{stats['rce_rate']}%" if stats["rce_rate"] is not None else "—")

            st.markdown("---")

            # ── AI Brief ──────────────────────────────────────────────────────────
            brief_text = ""
            if openai_service._check():
                st.markdown("### 🤖 AI Prosecution Brief")
                cache_key = f"ex_brief_{canonical_name}"
                if cache_key not in st.session_state:
                    with st.spinner("Generating AI brief…"):
                        brief = openai_service.examiner_summary(canonical_name, stats)
                        st.session_state[cache_key] = brief
                brief_text = st.session_state[cache_key]
                st.markdown(brief_text)
                st.markdown("---")
            else:
                st.info("Add **OPENAI_API_KEY** to `.env` to enable AI prosecution briefs.")

            # ── Charts ────────────────────────────────────────────────────────────
            col_charts1, col_charts2 = st.columns(2)

            with col_charts1:
                st.markdown("#### Outcome Distribution")
                fig_donut = px.pie(
                    names=["Patented", "Abandoned", "Pending"],
                    values=[stats["patented"], stats["abandoned"], stats["pending"]],
                    color_discrete_map={"Patented": "#2ecc71", "Abandoned": "#e74c3c", "Pending": "#95a5a6"},
                    hole=0.5,
                )
                fig_donut.update_layout(margin=dict(t=0, b=0), showlegend=True, height=260)
                st.plotly_chart(fig_donut, use_container_width=True)

            with col_charts2:
                st.markdown("#### Filing Trend")
                years = Counter(
                    str(meta(a).get("filingDate", ""))[:4]
                    for a in apps if meta(a).get("filingDate", "")
                )
                yr_df = pd.DataFrame(sorted(years.items()), columns=["Year", "Applications"])
                yr_df = yr_df[yr_df["Year"].str.isdigit()]
                fig_trend = px.line(yr_df, x="Year", y="Applications", markers=True)
                fig_trend.update_layout(margin=dict(t=0, b=0), height=260)
                st.plotly_chart(fig_trend, use_container_width=True)

            st.markdown("---")

            # ── Recent applications table ──────────────────────────────────────────
            st.markdown(f"#### Recent Applications (sample of {len(apps)})")
            rows = []
            for a in apps:
                m_ = meta(a)
                outcome = get_outcome(a)
                rows.append({
                    "App №": a.get("applicationNumberText", ""),
                    "Title": str(m_.get("inventionTitle", ""))[:60],
                    "Filed": (m_.get("filingDate") or "")[:10],
                    "Status": m_.get("applicationStatusDescriptionText", ""),
                    "Outcome": outcome.title(),
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

            # ── Export ────────────────────────────────────────────────────────────
            if brief_text:
                st.markdown("---")
                export_md = "\n".join([
                    f"# Examiner Brief: {canonical_name}",
                    f"Art Unit: {primary_au_code}",
                    f"Difficulty: {stats['band']} ({stats['score']}/100)",
                    f"Allowance Rate: {stats['allowance_rate']}% | "
                    f"Avg OAs: {stats['avg_oa']} | "
                    f"Avg Pendency: {stats['avg_pendency']} mo | "
                    f"RCE Rate: {stats['rce_rate']}%",
                    f"Sample: {stats['total']} applications",
                    "",
                    "## AI Prosecution Brief",
                    brief_text,
                ])
                st.download_button(
                    "⬇️ Export Examiner Brief",
                    data=export_md,
                    file_name=f"examiner_{canonical_name.replace(', ', '_')}.md",
                    mime="text/markdown",
                )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 – ART UNIT EXPLORER
# ══════════════════════════════════════════════════════════════════════════════

with tab_au:
    with st.form("au_form"):
        col_i, col_b = st.columns([4, 1])
        with col_i:
            au_code = st.text_input(
                "Art unit",
                placeholder="4-digit art unit — e.g. 2143",
                label_visibility="collapsed",
            )
        with col_b:
            au_search = st.form_submit_button("Search", use_container_width=True)

    if not au_code:
        st.info("Enter a 4-digit art unit code to explore the examiner landscape.")
    else:
        with st.spinner(f"Loading art unit {au_code}…"):
            au_apps = uspto_api.search_by_art_unit(au_code)

        if not au_apps:
            st.error(f"No applications found for art unit **{au_code}**.")
        else:
            au_stats = compute_examiner_score(au_apps)

            # ── Overall banner ────────────────────────────────────────────────────
            st.markdown(f"## Art Unit {au_code}")
            st.markdown(score_badge(au_stats["score"], au_stats["band"], au_stats["color_hex"]),
                        unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Applications (sample)", au_stats["total"])
            m2.metric("Allowance Rate", f"{au_stats['allowance_rate']}%")
            m3.metric("Avg Office Actions", au_stats["avg_oa"])
            m4.metric("Avg Pendency", f"{au_stats['avg_pendency']} mo")

            st.markdown("---")

            # ── Per-examiner breakdown ────────────────────────────────────────────
            by_examiner: dict = defaultdict(list)
            for a in au_apps:
                ex = meta(a).get("examinerNameText", "Unknown")
                by_examiner[ex].append(a)

            ex_rows = []
            for ex, ex_apps in by_examiner.items():
                s = compute_examiner_score(ex_apps)
                ex_rows.append({
                    "Examiner": ex,
                    "Apps": len(ex_apps),
                    "Score": s["score"] or 0,
                    "Band": s["band"],
                    "Allowance %": s["allowance_rate"],
                    "Avg OAs": s["avg_oa"],
                    "Avg Pendency (mo)": s["avg_pendency"],
                    "_color": s["color_hex"],
                })
            ex_rows.sort(key=lambda r: r["Score"], reverse=True)

            # Score bar chart
            st.markdown("#### Examiner Scores — ranked easiest → hardest")
            bar_df = pd.DataFrame(ex_rows)
            fig_bar = go.Figure()
            for _, row in bar_df.iterrows():
                fig_bar.add_trace(go.Bar(
                    x=[row["Examiner"].split(",")[0]],
                    y=[row["Score"]],
                    marker_color=row["_color"],
                    showlegend=False,
                    hovertemplate=f"{row['Examiner']}<br>Score: {row['Score']}<br>Allowance: {row['Allowance %']}%<extra></extra>",
                ))
            fig_bar.update_layout(
                margin=dict(t=0, b=80), height=320,
                xaxis=dict(tickangle=-40), yaxis=dict(range=[0, 100], title="Score"),
            )
            st.plotly_chart(fig_bar, use_container_width=True)

            # Distribution pie
            band_counts = Counter(r["Band"] for r in ex_rows)
            fig_pie = px.pie(
                names=list(band_counts.keys()),
                values=list(band_counts.values()),
                color=list(band_counts.keys()),
                color_discrete_map={
                    "Easy (Green)": "#2ecc71",
                    "Moderate (Yellow)": "#f39c12",
                    "Difficult (Red)": "#e74c3c",
                },
                title="Difficulty distribution",
            )
            fig_pie.update_layout(margin=dict(t=30, b=0), height=260)
            st.plotly_chart(fig_pie, use_container_width=True)

            # Roster table — click to load examiner profile
            st.markdown("#### Examiner Roster")
            display_cols = ["Examiner", "Apps", "Score", "Band", "Allowance %", "Avg OAs", "Avg Pendency (mo)"]
            roster_event = st.dataframe(
                bar_df[display_cols],
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
            )
            if roster_event and roster_event.selection.rows:
                selected_idx = roster_event.selection.rows[0]
                selected_ex = bar_df.iloc[selected_idx]["Examiner"]
                st.session_state["examiner_prefill"] = selected_ex
                st.rerun()
