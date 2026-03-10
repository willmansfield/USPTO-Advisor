"""
USPTO Advisor — home / login page.
Run with:  streamlit run app.py
API server: uvicorn api.main:app --port 8000
"""

import streamlit as st
from config import USERS, APP_TITLE
from utils.ui import inject_global_css

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_global_css()

# ── Auth gate ─────────────────────────────────────────────────────────────────

def do_login(username: str, password: str) -> bool:
    user = USERS.get(username)
    if user and user["password"] == password:
        st.session_state.authenticated = True
        st.session_state.username = username
        st.session_state.name = user["name"]
        return True
    return False


def show_login():
    st.markdown("""
    <style>
    /* Full-bleed two-panel login layout */
    .stApp { background: #1a3a5c !important; }
    section[data-testid="stMain"] > div { padding: 0 !important; }
    .login-outer {
        display: flex;
        min-height: 100vh;
        align-items: stretch;
    }
    .login-left {
        background: #1a3a5c;
        color: white;
        padding: 3rem 3rem 3rem 4rem;
        display: flex;
        flex-direction: column;
        justify-content: center;
        flex: 0 0 42%;
    }
    .login-left h1 {
        color: white !important;
        font-size: 1.85rem !important;
        font-weight: 800 !important;
        margin-bottom: 0.25rem !important;
    }
    .login-left .tagline {
        color: #93c5fd;
        font-size: 0.9rem;
        margin-bottom: 2.5rem;
    }
    .login-feature {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 0.9rem;
        font-size: 0.875rem;
        color: #cbd5e1;
    }
    .login-feature .dot {
        width: 7px; height: 7px;
        border-radius: 50%;
        background: #60a5fa;
        flex-shrink: 0;
    }
    .login-right {
        background: #f0f4f8;
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 2rem;
    }
    .login-card {
        background: white;
        border-radius: 16px;
        padding: 2.5rem;
        width: 100%;
        max-width: 380px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.10);
    }
    .login-card h2 {
        color: #1a3a5c !important;
        font-size: 1.35rem !important;
        font-weight: 700 !important;
        margin-bottom: 0.25rem !important;
    }
    .login-sub {
        color: #64748b;
        font-size: 0.85rem;
        margin-bottom: 1.75rem;
    }
    </style>
    """, unsafe_allow_html=True)

    # Two-panel layout via columns
    left, right = st.columns([4, 5])

    with left:
        st.markdown("""
        <div style="padding: 3rem 2rem; background:#1a3a5c; min-height:100vh; display:flex; flex-direction:column; justify-content:center;">
          <div style="color:#93c5fd; font-size:2rem; margin-bottom:1rem;">⚖</div>
          <h1 style="color:white; font-size:1.85rem; font-weight:800; margin:0 0 0.3rem;">USPTO Advisor</h1>
          <p style="color:#93c5fd; font-size:0.9rem; margin:0 0 2.5rem;">Patent Prosecution Intelligence</p>
          <div style="display:flex;flex-direction:column;gap:0.85rem;">
            <div style="display:flex;align-items:center;gap:0.75rem;color:#cbd5e1;font-size:0.85rem;">
              <span style="width:7px;height:7px;border-radius:50%;background:#60a5fa;flex-shrink:0;display:inline-block;"></span>
              Examiner difficulty scoring &amp; AI prosecution briefs
            </div>
            <div style="display:flex;align-items:center;gap:0.75rem;color:#cbd5e1;font-size:0.85rem;">
              <span style="width:7px;height:7px;border-radius:50%;background:#60a5fa;flex-shrink:0;display:inline-block;"></span>
              Full prosecution timelines with AI-narrated analysis
            </div>
            <div style="display:flex;align-items:center;gap:0.75rem;color:#cbd5e1;font-size:0.85rem;">
              <span style="width:7px;height:7px;border-radius:50%;background:#60a5fa;flex-shrink:0;display:inline-block;"></span>
              Company portfolio health dashboards
            </div>
            <div style="display:flex;align-items:center;gap:0.75rem;color:#cbd5e1;font-size:0.85rem;">
              <span style="width:7px;height:7px;border-radius:50%;background:#60a5fa;flex-shrink:0;display:inline-block;"></span>
              PTAB research &amp; pre-filing claim risk analysis
            </div>
            <div style="display:flex;align-items:center;gap:0.75rem;color:#cbd5e1;font-size:0.85rem;">
              <span style="width:7px;height:7px;border-radius:50%;background:#60a5fa;flex-shrink:0;display:inline-block;"></span>
              Conversational AI assistant with live USPTO data
            </div>
          </div>
          <p style="color:#475569;font-size:0.75rem;margin-top:3rem;">
            Powered by USPTO Open Data Portal · LexisNexis IP
          </p>
        </div>
        """, unsafe_allow_html=True)

    with right:
        st.markdown("<div style='height:3rem'></div>", unsafe_allow_html=True)
        st.markdown("""
        <div style="max-width:360px;margin:0 auto;">
          <h2 style="color:#1a3a5c;font-size:1.5rem;font-weight:700;margin-bottom:0.25rem;">Welcome back</h2>
          <p style="color:#64748b;font-size:0.875rem;margin-bottom:1.75rem;">Sign in to your account to continue.</p>
        </div>
        """, unsafe_allow_html=True)

        form_col, _ = st.columns([3, 1])
        with form_col:
            with st.form("login_form"):
                username = st.text_input("Username", placeholder="Username")
                password = st.text_input("Password", type="password", placeholder="Password")
                submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")

            if submitted:
                if do_login(username, password):
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

            st.markdown(
                "<p style='color:#94a3b8;font-size:0.78rem;margin-top:1rem;'>"
                "Demo: <strong>admin</strong> / admin123 &nbsp;·&nbsp; <strong>demo</strong> / demo123</p>",
                unsafe_allow_html=True,
            )


# ── Logged-in home dashboard ──────────────────────────────────────────────────

_NAV_CARDS = [
    {
        "icon": "⚖️",
        "title": "Prosecution Hub",
        "desc": "Full prosecution history for any application — examiner profile inline, AI office action analysis, and response strategy.",
        "page": "pages/1_Prosecution_Hub.py",
    },
    {
        "icon": "🔬",
        "title": "Examiner Intel",
        "desc": "Difficulty scoring, allowance rates, AI prosecution briefs, and full art unit examiner rosters.",
        "page": "pages/2_Examiner_Intel.py",
    },
    {
        "icon": "💼",
        "title": "Portfolio",
        "desc": "Company prosecution health dashboard — outcomes, filing trends, top examiners, and AI executive summary.",
        "page": "pages/3_Portfolio.py",
    },
    {
        "icon": "🏛️",
        "title": "PTAB & Pre-filing",
        "desc": "Search IPR/PGR/CBM decisions and run pre-filing claim checks for §102, §103, and §112 risks.",
        "page": "pages/4_PTAB_Claims.py",
    },
    {
        "icon": "💬",
        "title": "AI Patent Assistant",
        "desc": "Conversational patent AI — ask about examiners, art units, strategy, or claim drafting with live USPTO data.",
        "page": "pages/5_AI_Chat.py",
    },
]


def show_home():
    from utils.auth import sidebar_user
    sidebar_user()

    name = st.session_state.get("name", "")
    st.markdown(f"# USPTO Advisor")
    st.caption(f"Welcome, **{name}** — what would you like to explore today?")
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # Card grid — 3 across top, 2 across bottom
    top_cards = _NAV_CARDS[:3]
    bot_cards  = _NAV_CARDS[3:]

    top_cols = st.columns(3, gap="medium")
    for col, card in zip(top_cols, top_cards):
        with col:
            st.markdown(
                f"""<div class="nav-card">
                  <div class="nav-icon">{card['icon']}</div>
                  <p class="nav-title">{card['title']}</p>
                  <p class="nav-desc">{card['desc']}</p>
                  <p class="nav-cta">Open →</p>
                </div>""",
                unsafe_allow_html=True,
            )
            # Invisible button fills the card — CSS layering would be ideal but
            # Streamlit doesn't support it natively; we use a labelled button below the card.
            if st.button(f"Open {card['title']}", key=f"nav_{card['title']}", use_container_width=True):
                st.switch_page(card["page"])

    st.markdown("<div style='height:0.25rem'></div>", unsafe_allow_html=True)

    bot_cols = st.columns([1, 1, 1], gap="medium")
    padding_cols = [bot_cols[0], bot_cols[1]]
    for col, card in zip(padding_cols, bot_cards):
        with col:
            st.markdown(
                f"""<div class="nav-card">
                  <div class="nav-icon">{card['icon']}</div>
                  <p class="nav-title">{card['title']}</p>
                  <p class="nav-desc">{card['desc']}</p>
                  <p class="nav-cta">Open →</p>
                </div>""",
                unsafe_allow_html=True,
            )
            if st.button(f"Open {card['title']}", key=f"nav_{card['title']}", use_container_width=True):
                st.switch_page(card["page"])

    st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
    st.markdown(
        "<p style='color:#94a3b8;font-size:0.78rem;'>"
        "Data: USPTO Open Data Portal — live API calls, no local database. "
        "Samples up to 1,000 most recent applications per query. &nbsp;·&nbsp; "
        "REST API + MCP: <code>uvicorn api.main:app --port 8000</code></p>",
        unsafe_allow_html=True,
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if st.session_state.get("authenticated"):
    show_home()
else:
    show_login()
