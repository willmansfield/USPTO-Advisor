"""
AI Chat — conversational patent assistant with live USPTO data.

Ask anything about examiners, applications, art units, PTAB, claim strategy,
or prosecution tactics. The AI automatically fetches live USPTO data when needed.
"""

import streamlit as st
from utils.auth import require_auth, sidebar_user
from utils.ui import inject_global_css
from services import openai_service

require_auth()
inject_global_css()
sidebar_user()

st.title("💬 AI Patent Assistant")
st.caption("Ask anything — the assistant automatically pulls live USPTO data when relevant.")

if not openai_service._check():
    st.warning(
        "Add **OPENAI_API_KEY** to `.env` to use the AI assistant.\n\n"
        "The other pages (Prosecution Hub, Examiner Intel, Portfolio, PTAB) work without it."
    )
    st.stop()

# ── Sidebar controls ──────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("---")
    st.markdown("**Assistant settings**")
    use_tools = st.toggle("Fetch live USPTO data", value=True,
                          help="When on, the AI automatically calls USPTO APIs for examiners, applications, art units, etc.")
    if st.button("Clear conversation", use_container_width=True):
        st.session_state.pop("chat_messages", None)
        st.rerun()

# ── Session state ─────────────────────────────────────────────────────────────

if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

# ── Suggested questions (shown when chat is empty) ────────────────────────────

SUGGESTIONS = [
    "Who are the easiest examiners in art unit 2143?",
    "What's the allowance rate for examiner SMITH?",
    "How long does prosecution typically take in art unit 2800?",
    "What are common §103 obviousness arguments that work with difficult examiners?",
    "Tell me about PTAB decisions involving Samsung as petitioner.",
    "What's Apple's overall portfolio allowance rate?",
    "How should I respond to a §103 rejection citing two references?",
    "What makes a claim more likely to be allowed in software art units?",
]

if not st.session_state.chat_messages:
    st.markdown(
        "<p style='font-size:0.85rem;color:#64748b;font-weight:600;text-transform:uppercase;"
        "letter-spacing:0.06em;margin-bottom:0.75rem;'>Try asking</p>",
        unsafe_allow_html=True,
    )

    # Render pill buttons — one per suggestion, flowing wrap via columns
    # We use a 2-col grid for consistent layout with Streamlit buttons
    col1, col2 = st.columns(2)
    for i, q in enumerate(SUGGESTIONS):
        col = col1 if i % 2 == 0 else col2
        with col:
            if st.button(q, use_container_width=True, key=f"sug_{i}"):
                st.session_state.chat_messages.append({"role": "user", "content": q})
                st.rerun()

    # Extra pill CSS to style the suggestion buttons differently
    st.markdown("""
    <style>
    /* Style the suggestion buttons as pill-shaped prompts */
    div[data-testid="stHorizontalBlock"] .stButton > button {
        background: #eff6ff !important;
        color: #1d4ed8 !important;
        border: 1px solid #bfdbfe !important;
        border-radius: 99px !important;
        font-size: 0.8rem !important;
        font-weight: 500 !important;
        padding: 0.4rem 1rem !important;
        text-align: left !important;
        white-space: normal !important;
        height: auto !important;
        line-height: 1.4 !important;
    }
    div[data-testid="stHorizontalBlock"] .stButton > button:hover {
        background: #dbeafe !important;
        border-color: #93c5fd !important;
        color: #1e40af !important;
        box-shadow: none !important;
        transform: none !important;
    }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("---")

# ── Chat history ──────────────────────────────────────────────────────────────

for msg in st.session_state.chat_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("tool_calls"):
            with st.expander(f"Live data fetched ({len(msg['tool_calls'])} call(s))"):
                for tc in msg["tool_calls"]:
                    st.code(tc, language=None)

# ── Input ──────────────────────────────────────────────────────────────────────

prompt = st.chat_input("Ask about an examiner, application, company, PTAB decision, claim strategy…")

if prompt:
    st.session_state.chat_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            response, tool_calls = openai_service.general_chat(
                st.session_state.chat_messages,
                use_tools=use_tools,
            )
        st.markdown(response)
        if tool_calls:
            with st.expander(f"Live data fetched ({len(tool_calls)} call(s))"):
                for tc in tool_calls:
                    st.code(tc, language=None)

    st.session_state.chat_messages.append({
        "role": "assistant",
        "content": response,
        "tool_calls": tool_calls,
    })
