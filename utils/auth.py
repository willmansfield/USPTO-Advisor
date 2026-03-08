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
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"**Logged in as:** {st.session_state.get('name', '')}")
        if st.sidebar.button("Logout"):
            logout()
