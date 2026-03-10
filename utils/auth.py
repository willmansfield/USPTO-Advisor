import streamlit as st


def require_auth():
    """Call at the top of every page to enforce login."""
    if not st.session_state.get("authenticated", False):
        st.warning("Please log in from the Home page first.")
        st.stop()


def logout():
    st.session_state.authenticated = False
    st.session_state.pop("username", None)
    st.session_state.pop("name", None)
    st.rerun()


def sidebar_user():
    """Show current user + logout button in the sidebar."""
    if st.session_state.get("authenticated"):
        name = st.session_state.get("name", "")
        st.sidebar.markdown("---")
        st.sidebar.markdown(
            f"<p style='font-size:0.8rem;color:#94a3b8;margin:0;'>Signed in as</p>"
            f"<p style='font-size:0.875rem;color:#f1f5f9;font-weight:600;margin:0.1rem 0 0.5rem;'>{name}</p>",
            unsafe_allow_html=True,
        )
        if st.sidebar.button("Sign Out", use_container_width=True):
            logout()
