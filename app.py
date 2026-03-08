"""
PatentAdvisor POC – Home / Login page.

Run with:  streamlit run app.py
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

    st.title(f"⚖️ {APP_TITLE}")
    st.markdown(
        f"Welcome, **{st.session_state.get('name', '')}**.  "
        "Use the sidebar to navigate."
    )

    st.markdown("---")
    st.subheader("What can you do here?")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📊 Patent Analytics (PA Mode)")
        st.markdown("""
| Page | Description |
|------|-------------|
| 🔍 Examiner Search | Profile, difficulty score (Green/Yellow/Red), allowance rate, OA stats |
| 📋 Application Search | Multi-field search – assignee, art unit, status, dates |
| 💼 Portfolio View | Company or law-firm prosecution health dashboard |
| 🏛️ Art Unit Explorer | Art unit stats, examiner roster, score distribution |
| ⚖️ PTAB Decisions | Search PTAB trial outcomes |
        """)

    with col2:
        st.markdown("### 🤖 AI Assistant Mode")
        st.markdown("""
| Page | Description |
|------|-------------|
| 💬 AI Chat | Conversational patent assistant with live USPTO context |
| 📄 OA Analyzer | Paste an Office Action → plain-English analysis + response strategy |
| ✅ Claim Checker | Pre-filing claim weakness analysis (§102/103/112) |
        """)

    st.markdown("---")
    st.info(
        "**Data source:** USPTO Patent Examination Data System (PEDS) & PatentsView – "
        "live API calls, no local database.  "
        "Results reflect a sample of up to 200 recent applications per query."
    )


# ── Entry point ───────────────────────────────────────────────────────────────

if st.session_state.get("authenticated"):
    show_home()
else:
    show_login()
