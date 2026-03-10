import os
from dotenv import load_dotenv

load_dotenv()

# ── USPTO API key (loaded from .env) ─────────────────────────────────────────
USPTO_API_KEY = os.getenv("USPTO_API_KEY", "")

# ── Credentials — loaded from Streamlit secrets manager ──────────────────────
# Configure users in .streamlit/secrets.toml:
#
#   [users.alice]
#   name     = "Alice Smith"
#   password = "her-password"
#
# Falls back to empty dict when running outside Streamlit (e.g. API server).
def _load_users() -> dict:
    try:
        import streamlit as st
        raw = st.secrets.get("users", {})
        return {
            username: {"name": info["name"], "password": info["password"]}
            for username, info in raw.items()
        }
    except Exception:
        return {}

USERS = _load_users()

# ── USPTO APIs ────────────────────────────────────────────────────────────────
# Primary: Patent Examination Data System (PEDS)
PEDS_API_URL = "https://ped.uspto.gov/api/queries"
PEDS_TRANSACTION_URL = "https://ped.uspto.gov/api/queries/{app_num}/transactions"

# PatentsView (granted patents with examiner fields)
PATENTSVIEW_API_URL = "https://api.patentsview.org/patents/query"

# PTAB decisions – try new ODP first, fall back to developer hub
PTAB_ODP_URL     = "https://api.uspto.gov/api/v1/patent/trials/decisions/search"
PTAB_DEVHUB_URL  = "https://developer.uspto.gov/ptab-api/decisions"

# Office Action text retrieval
OA_TEXT_URL = "https://efts.uspto.gov/LATEST/search-index"

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = "gpt-5-mini"

# ── App settings ──────────────────────────────────────────────────────────────
APP_TITLE   = "USPTO Advisor"
PAGE_LIMIT  = 50   # records per ODP page (6 MB payload cap ≈ 50 safe max)
MAX_PAGES   = 20   # max pages to fetch (= 1 000 apps)

# Examiner difficulty thresholds (based on allowance rate %)
SCORE_GREEN  = 60   # >= 60 % → Easy
SCORE_YELLOW = 35   # 35–59 % → Moderate
# < 35 % → Difficult

# ── Outcome classification ────────────────────────────────────────────────────
PATENTED_CODES  = {str(c) for c in range(150, 161)}   # 150-160
ABANDONED_CODES = {str(c) for c in range(161, 200)}   # 161-199

OFFICE_ACTION_CODES = {"CTNF", "CTFR", "MCTNF", "MCTFR"}
ALLOWANCE_CODES     = {"M327", "MNDC", "MNAL"}
RCE_CODES           = {"RCE", "RCE2"}
