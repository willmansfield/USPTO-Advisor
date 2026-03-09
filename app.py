"""
USPTO Advisor — home / login page.
Run with:  streamlit run app.py
API server: uvicorn api.main:app --port 8000
"""

import streamlit as st
from config import USERS, APP_TITLE

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Inject minimal custom CSS ─────────────────────────────────────────────────
st.markdown("""
<style>
    .score-badge {
        display: inline-block;
        padding: 4px 14px;
        border-radius: 20px;
        font-weight: 700;
        font-size: 1.1rem;
        color: white;
    }
    .metric-card {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 1rem;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)


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
    col_l, col_m, col_r = st.columns([1, 1.2, 1])
    with col_m:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.image(
            "https://upload.wikimedia.org/wikipedia/commons/thumb/8/8c/USPTO_seal.svg/240px-USPTO_seal.svg.png",
            width=80,
        )
        st.markdown(f"## {APP_TITLE}")
        st.caption("USPTO Patent Analytics · Powered by open data + AI")
        st.markdown("---")

        with st.form("login_form"):
            username = st.text_input("Username", placeholder="admin")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Login", use_container_width=True)

        if submitted:
            if do_login(username, password):
                st.rerun()
            else:
                st.error("Invalid username or password.")

        st.markdown("---")
        st.caption("Demo credentials:  **admin** / admin123  or  **demo** / demo123")


# ── Logged-in home dashboard ──────────────────────────────────────────────────

def show_home():
    from utils.auth import sidebar_user
    sidebar_user()

    st.title("⚖️ USPTO Advisor")
    st.markdown(f"Welcome, **{st.session_state.get('name', '')}**.")
    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Start here")

        if st.button(
            "⚖️ **Prosecution Hub**\n\nLook up any application — full prosecution history, "
            "inline examiner profile, AI-powered OA analysis and response strategy.",
            use_container_width=True,
        ):
            st.switch_page("pages/1_Prosecution_Hub.py")

        st.markdown("")

        if st.button(
            "🔬 **Examiner Intel**\n\nSearch an examiner or art unit — "
            "difficulty score, allowance rate, AI prosecution brief, examiner roster.",
            use_container_width=True,
        ):
            st.switch_page("pages/2_Examiner_Intel.py")

        st.markdown("")

        if st.button(
            "💼 **Portfolio**\n\nCompany prosecution health dashboard — "
            "outcomes, trends, top examiners, art units, AI executive summary.",
            use_container_width=True,
        ):
            st.switch_page("pages/3_Portfolio.py")

    with col2:
        st.markdown("### Research & analysis")

        if st.button(
            "⚖️ **PTAB & Pre-filing**\n\nSearch IPR/PGR/CBM decisions · "
            "Pre-filing claim checker for §102/103/112 risks.",
            use_container_width=True,
        ):
            st.switch_page("pages/4_PTAB_Claims.py")

        st.markdown("")

        if st.button(
            "💬 **AI Patent Assistant**\n\nConversational patent AI — ask about examiners, "
            "art units, strategy, claim drafting. Fetches live USPTO data automatically.",
            use_container_width=True,
        ):
            st.switch_page("pages/5_AI_Chat.py")

    st.markdown("---")
    st.info(
        "**Data:** USPTO Open Data Portal — live API calls, no local database. "
        "Samples up to 200 most recent applications per query.  \n"
        "**REST API + MCP server:** `uvicorn api.main:app --port 8000` — "
        "docs at `/docs`, MCP at `/mcp`."
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if st.session_state.get("authenticated"):
    show_home()
else:
    show_login()
