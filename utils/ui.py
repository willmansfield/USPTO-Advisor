"""Shared UI helpers used across multiple pages."""

# ── Design tokens ─────────────────────────────────────────────────────────────

PRIMARY   = "#1a3a5c"   # deep navy
ACCENT    = "#2563eb"   # royal blue
SUCCESS   = "#059669"   # emerald
WARNING   = "#d97706"   # amber
DANGER    = "#dc2626"   # red
MUTED     = "#64748b"   # slate
BORDER    = "#e2e8f0"
SURFACE   = "#ffffff"
BG        = "#f0f4f8"

# Difficulty colours (kept compatible with scoring.py)
DIFF_COLORS = {
    "Easy":     "#059669",
    "Moderate": "#d97706",
    "Difficult":"#dc2626",
}

# ── Plotly shared theme ───────────────────────────────────────────────────────

PLOTLY_THEME = dict(
    font=dict(family="Inter, system-ui, sans-serif", size=12, color="#1e293b"),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    margin=dict(t=10, b=10, l=10, r=10),
    xaxis=dict(showgrid=False, zeroline=False, tickfont=dict(size=11)),
    yaxis=dict(showgrid=True, gridcolor="#f1f5f9", zeroline=False, tickfont=dict(size=11)),
    legend=dict(bgcolor="rgba(0,0,0,0)", borderwidth=0),
)

OUTCOME_COLORS = {
    "Patented":  SUCCESS,
    "Abandoned": DANGER,
    "Pending":   MUTED,
}

# ── Global CSS ────────────────────────────────────────────────────────────────

_GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
}

/* Page background */
.stApp {
    background-color: #f0f4f8;
}

/* Main content area */
section[data-testid="stMain"] > div {
    padding-top: 1.5rem;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #1a3a5c !important;
    border-right: none !important;
}
[data-testid="stSidebar"] * {
    color: #cbd5e1 !important;
}
[data-testid="stSidebar"] .stMarkdown strong {
    color: #f8fafc !important;
}
[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.12) !important;
}
[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.08) !important;
    color: #e2e8f0 !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: 6px !important;
    width: 100%;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.16) !important;
}

/* Sidebar page nav links */
[data-testid="stSidebarNav"] a {
    color: #94a3b8 !important;
    border-radius: 6px;
    padding: 0.35rem 0.75rem;
    font-size: 0.875rem;
}
[data-testid="stSidebarNav"] a:hover,
[data-testid="stSidebarNav"] [aria-current="page"] {
    background: rgba(255,255,255,0.1) !important;
    color: #f1f5f9 !important;
}

/* ── Buttons ── */
.stButton > button[kind="primary"],
.stButton > button[data-testid*="primary"],
.stFormSubmitButton > button {
    background: #2563eb !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.875rem !important;
    padding: 0.5rem 1.25rem !important;
    transition: background 0.15s ease, box-shadow 0.15s ease;
}
.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button:hover {
    background: #1d4ed8 !important;
    box-shadow: 0 4px 12px rgba(37,99,235,0.3) !important;
}
.stButton > button:not([kind="primary"]) {
    background: white !important;
    color: #1e293b !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    transition: all 0.15s ease;
}
.stButton > button:not([kind="primary"]):hover {
    border-color: #2563eb !important;
    color: #2563eb !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important;
}

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] {
    background: white;
    border-radius: 10px 10px 0 0;
    border-bottom: 2px solid #e2e8f0;
    gap: 0;
    padding: 0 0.5rem;
}
.stTabs [data-baseweb="tab"] {
    background: transparent !important;
    border: none !important;
    color: #64748b !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
    padding: 0.75rem 1.25rem !important;
    border-bottom: 2px solid transparent !important;
    margin-bottom: -2px !important;
    transition: color 0.15s ease;
}
.stTabs [aria-selected="true"] {
    color: #2563eb !important;
    border-bottom-color: #2563eb !important;
}
.stTabs [data-baseweb="tab-panel"] {
    background: white;
    border-radius: 0 0 10px 10px;
    padding: 1.5rem;
    border: 1px solid #e2e8f0;
    border-top: none;
}

/* ── Metrics ── */
[data-testid="metric-container"] {
    background: white;
    border-radius: 10px;
    padding: 1rem 1.25rem;
    border: 1px solid #e2e8f0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
[data-testid="metric-container"] label {
    color: #64748b !important;
    font-size: 0.75rem !important;
    font-weight: 500 !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #1a3a5c !important;
    font-size: 1.5rem !important;
    font-weight: 700 !important;
}

/* ── Forms / inputs ── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stNumberInput > div > div > input {
    background: white !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
    font-size: 0.9rem !important;
    color: #1e293b !important;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.12) !important;
    outline: none !important;
}

/* ── Alerts ── */
.stInfo {
    background: #eff6ff !important;
    border-left: 4px solid #2563eb !important;
    border-radius: 0 8px 8px 0 !important;
    color: #1e3a5f !important;
}
.stSuccess {
    background: #f0fdf4 !important;
    border-left: 4px solid #059669 !important;
    border-radius: 0 8px 8px 0 !important;
}
.stWarning {
    background: #fffbeb !important;
    border-left: 4px solid #d97706 !important;
    border-radius: 0 8px 8px 0 !important;
}
.stError {
    background: #fef2f2 !important;
    border-left: 4px solid #dc2626 !important;
    border-radius: 0 8px 8px 0 !important;
}

/* ── Dataframes ── */
.stDataFrame {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #e2e8f0 !important;
}

/* ── Expanders ── */
.streamlit-expanderHeader {
    background: white !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    color: #1e293b !important;
}

/* ── Download buttons ── */
.stDownloadButton > button {
    background: white !important;
    color: #2563eb !important;
    border: 1px solid #2563eb !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}
.stDownloadButton > button:hover {
    background: #eff6ff !important;
}

/* ── Page headings ── */
h1 {
    color: #1a3a5c !important;
    font-weight: 700 !important;
    font-size: 1.75rem !important;
    letter-spacing: -0.02em;
}
h2 {
    color: #1a3a5c !important;
    font-weight: 700 !important;
    font-size: 1.35rem !important;
}
h3 {
    color: #1e293b !important;
    font-weight: 600 !important;
    font-size: 1.1rem !important;
}
h4 {
    color: #334155 !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

/* Caption / muted text */
.stCaption, small {
    color: #64748b !important;
    font-size: 0.8rem !important;
}

/* Dividers */
hr {
    border: none !important;
    border-top: 1px solid #e2e8f0 !important;
    margin: 1.5rem 0 !important;
}

/* ── Nav cards (home page) ── */
.nav-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-top: 3px solid #2563eb;
    border-radius: 10px;
    padding: 1.5rem;
    height: 100%;
    cursor: pointer;
    transition: box-shadow 0.2s ease, transform 0.2s ease;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}
.nav-card:hover {
    box-shadow: 0 8px 24px rgba(0,0,0,0.10);
    transform: translateY(-2px);
}
.nav-card .nav-icon {
    font-size: 1.75rem;
    line-height: 1;
}
.nav-card .nav-title {
    font-size: 1rem;
    font-weight: 700;
    color: #1a3a5c;
    margin: 0;
}
.nav-card .nav-desc {
    font-size: 0.82rem;
    color: #64748b;
    margin: 0;
    line-height: 1.5;
    flex: 1;
}
.nav-card .nav-cta {
    font-size: 0.8rem;
    font-weight: 600;
    color: #2563eb;
    margin-top: 0.25rem;
}

/* ── Score card ── */
.score-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.25rem 1.5rem;
    display: inline-flex;
    align-items: center;
    gap: 1.5rem;
}
.score-number {
    font-size: 2.5rem;
    font-weight: 800;
    line-height: 1;
}
.score-band {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 0.35rem;
}
.score-bar-bg {
    width: 180px;
    height: 8px;
    background: #f1f5f9;
    border-radius: 99px;
    overflow: hidden;
}
.score-bar-fill {
    height: 100%;
    border-radius: 99px;
    transition: width 0.6s ease;
}
.score-sub {
    font-size: 0.75rem;
    color: #64748b;
    margin-top: 0.35rem;
}

/* ── Score badge (legacy inline use) ── */
.score-badge {
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-weight: 700;
    font-size: 1.1rem;
    color: white;
}

/* ── Prosecution timeline ── */
.timeline-wrap {
    position: relative;
    padding-left: 2rem;
    margin-top: 0.5rem;
}
.timeline-wrap::before {
    content: '';
    position: absolute;
    left: 7px;
    top: 8px;
    bottom: 8px;
    width: 2px;
    background: #e2e8f0;
    border-radius: 2px;
}
.tl-item {
    position: relative;
    margin-bottom: 1rem;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 0.65rem 1rem;
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
}
.tl-dot {
    position: absolute;
    left: -1.65rem;
    top: 0.75rem;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    border: 2px solid white;
    box-shadow: 0 0 0 2px currentColor;
    flex-shrink: 0;
}
.tl-date {
    font-size: 0.75rem;
    color: #64748b;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    flex-shrink: 0;
    padding-top: 1px;
}
.tl-code {
    font-size: 0.72rem;
    font-weight: 700;
    padding: 1px 7px;
    border-radius: 4px;
    white-space: nowrap;
    flex-shrink: 0;
    color: white;
}
.tl-desc {
    font-size: 0.82rem;
    color: #334155;
    line-height: 1.4;
}

/* ── Chat suggestion pills ── */
.suggestions-wrap {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-bottom: 1rem;
}
.pill-btn {
    display: inline-block;
    background: #eff6ff;
    color: #1d4ed8;
    border: 1px solid #bfdbfe;
    border-radius: 99px;
    padding: 0.4rem 0.9rem;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s ease;
}
.pill-btn:hover {
    background: #dbeafe;
}

/* ── Link buttons ── */
.stLinkButton > a {
    background: white !important;
    color: #2563eb !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    font-size: 0.875rem !important;
}
</style>
"""

# ── Public helpers ────────────────────────────────────────────────────────────

def inject_global_css():
    """Call once per page at the top (after set_page_config)."""
    import streamlit as st
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


def score_badge(score, band: str, color: str, size: str = "large") -> str:
    """Legacy inline badge — kept for backward compat."""
    if size == "small":
        padding, font = "3px 12px", "0.9rem"
    else:
        padding, font = "5px 16px", "1rem"
    score_str = f"{score}/100" if score is not None else "—"
    return (
        f'<span style="background:{color};color:white;padding:{padding};'
        f'border-radius:24px;font-weight:700;font-size:{font};">'
        f"{band} &nbsp; {score_str}</span>"
    )


def score_card_html(score, band: str, color: str, total: int = 0) -> str:
    """Rich score card with inline progress bar."""
    score_val = score if score is not None else 0
    score_str = f"{score_val}" if score is not None else "—"
    sub = f"Based on {total:,} applications" if total else ""
    return f"""
<div class="score-card">
  <div class="score-number" style="color:{color};">{score_str}</div>
  <div>
    <div class="score-band" style="color:{color};">{band}</div>
    <div class="score-bar-bg">
      <div class="score-bar-fill" style="width:{score_val}%;background:{color};"></div>
    </div>
    <div class="score-sub">{sub} &nbsp;· &nbsp;out of 100</div>
  </div>
</div>
"""


def timeline_html(events: list) -> str:
    """Render prosecution events as a vertical visual timeline."""
    _COLORS = {
        "CTNF":  "#dc2626", "CTFR":  "#dc2626",
        "MCTNF": "#dc2626", "MCTFR": "#dc2626",
        "RCE":   "#ea580c", "RCE2":  "#ea580c",
        "M327":  "#059669", "MNDC":  "#059669", "MNAL":  "#059669",
        "FWDX":  "#059669", "ISSUE": "#059669",
        "RESP":  "#2563eb", "A___":  "#2563eb",
    }
    if not events:
        return "<p style='color:#64748b;font-size:0.85rem;'>No prosecution events found.</p>"

    items = []
    for e in reversed(events):
        code  = e.get("eventCode", "")
        date  = (e.get("eventDate") or "")[:10]
        desc  = e.get("eventDescriptionText", "")
        color = _COLORS.get(code, "#94a3b8")
        items.append(
            f'<div class="tl-item">'
            f'<div class="tl-dot" style="color:{color};background:{color};"></div>'
            f'<span class="tl-date">{date}</span>'
            f'<span class="tl-code" style="background:{color};">{code}</span>'
            f'<span class="tl-desc">{desc}</span>'
            f'</div>'
        )
    body = "\n".join(items)
    return f'<div class="timeline-wrap">{body}</div>'


def page_header(title: str, subtitle: str = "") -> None:
    """Consistent page header — title + optional subtitle."""
    import streamlit as st
    st.markdown(f"# {title}")
    if subtitle:
        st.caption(subtitle)


def section_header(label: str) -> None:
    """Small uppercase section label."""
    import streamlit as st
    st.markdown(f"#### {label}")
