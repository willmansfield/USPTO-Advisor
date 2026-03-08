"""
Page 6 – AI Chat
Conversational patent assistant.  Can pull live USPTO data to ground answers.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import streamlit as st

from utils.auth import require_auth, sidebar_user
from config import OPENAI_API_KEY

require_auth()
sidebar_user()

st.title("💬 AI Patent Chat")
st.caption(
    "Ask anything about USPTO patent prosecution, examiners, art units, or strategy.  "
    "Toggle 'Fetch live USPTO data' to ground answers in real-time PEDS data."
)

if not OPENAI_API_KEY:
    st.error(
        "OpenAI API key not configured.  "
        "Set `OPENAI_API_KEY` in your `.env` file and restart the app."
    )
    st.stop()

# ── Session state for conversation ───────────────────────────────────────────
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

# ── Sidebar options ───────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("---")
    st.markdown("### Chat Settings")
    use_live_data = st.toggle("Fetch live USPTO data", value=True)
    if st.button("Clear conversation"):
        st.session_state.chat_messages = []
        st.rerun()

# ── Display conversation ──────────────────────────────────────────────────────
for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ── Input ─────────────────────────────────────────────────────────────────────
user_input = st.chat_input("Ask a patent question…")

if not user_input:
    st.stop()

# Add user message
st.session_state.chat_messages.append({"role": "user", "content": user_input})
with st.chat_message("user"):
    st.markdown(user_input)

# ── Optional: fetch live context ──────────────────────────────────────────────
live_context = ""
if use_live_data:
    from services import uspto_api

    # Simple heuristic: extract examiner or art unit from query
    import re
    au_match   = re.search(r"\b(\d{4})\b", user_input)
    name_match = re.search(r"examiner\s+([\w,]+(?:\s+[\w]+)?)", user_input, re.I)

    if name_match:
        ex_name = name_match.group(1).strip()
        with st.spinner(f"Fetching live data for examiner '{ex_name}'…"):
            apps = uspto_api.search_by_examiner(ex_name)
        if apps:
            from services.scoring import compute_examiner_score
            stats = compute_examiner_score(apps)
            live_context = (
                f"Live USPTO data for examiner '{ex_name}':\n"
                f"  Applications sampled: {stats['total']}\n"
                f"  Allowance rate: {stats['allowance_rate']} %\n"
                f"  Average office actions: {stats['avg_oa']}\n"
                f"  Average pendency: {stats['avg_pendency']} months\n"
                f"  Difficulty band: {stats['band']}"
            )

    elif au_match:
        au = au_match.group(1)
        with st.spinner(f"Fetching live data for art unit {au}…"):
            apps = uspto_api.search_by_art_unit(au)
        if apps:
            from services.scoring import compute_examiner_score
            stats = compute_examiner_score(apps)
            live_context = (
                f"Live USPTO data for art unit {au}:\n"
                f"  Applications sampled: {stats['total']}\n"
                f"  Allowance rate: {stats['allowance_rate']} %\n"
                f"  Average office actions: {stats['avg_oa']}\n"
                f"  Difficulty band: {stats['band']}"
            )

# ── Generate AI response ──────────────────────────────────────────────────────
with st.chat_message("assistant"):
    with st.spinner("Thinking…"):
        from services.openai_service import general_chat
        response = general_chat(
            messages=st.session_state.chat_messages,
            live_context=live_context,
        )

    if live_context:
        with st.expander("📡 Live USPTO data used", expanded=False):
            st.code(live_context)

    st.markdown(response)

st.session_state.chat_messages.append({"role": "assistant", "content": response})
