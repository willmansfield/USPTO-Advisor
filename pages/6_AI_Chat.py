"""
Page 6 - AI Chat
Conversational patent assistant with live USPTO tool calling.
The AI model decides which USPTO API functions to call based on the conversation.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from utils.auth import require_auth, sidebar_user
from config import OPENAI_API_KEY

require_auth()
sidebar_user()

st.title("AI Patent Chat")
st.caption(
    "Ask anything about USPTO patent prosecution, examiners, art units, or strategy. "
    "The AI automatically fetches live USPTO data as needed."
)

if not OPENAI_API_KEY:
    st.error(
        "OpenAI API key not configured. "
        "Set OPENAI_API_KEY in your .env file and restart the app."
    )
    st.stop()

# ── Session state ─────────────────────────────────────────────────────────────────────────────
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

# ── Sidebar ───────────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("---")
    st.markdown("### Chat Settings")
    use_tools = st.toggle("Enable live USPTO tools", value=True)
    if st.button("Clear conversation"):
        st.session_state.chat_messages = []
        st.rerun()

# ── Display conversation ───────────────────────────────────────────────────────────────────────
for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── Input ───────────────────────────────────────────────────────────────────────────────────────
user_input = st.chat_input("Ask a patent question...")

if not user_input:
    st.stop()

st.session_state.chat_messages.append({"role": "user", "content": user_input})
with st.chat_message("user"):
    st.markdown(user_input)

# ── Generate AI response (with tool calling) ──────────────────────────────────────────────────────
with st.chat_message("assistant"):
    with st.spinner("Thinking..."):
        from services.openai_service import general_chat
        response, tool_calls = general_chat(
            messages=st.session_state.chat_messages,
            use_tools=use_tools,
        )

    if tool_calls:
        with st.expander("Live USPTO data fetched", expanded=False):
            for call in tool_calls:
                st.code(call)

    st.markdown(response)

st.session_state.chat_messages.append({"role": "assistant", "content": response})
