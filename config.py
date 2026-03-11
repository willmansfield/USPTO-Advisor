import os
from dotenv import load_dotenv

load_dotenv()

# ── USPTO API ─────────────────────────────────────────────────────────────────
USPTO_API_KEY = os.getenv("USPTO_API_KEY", "")

# ── OpenAI ────────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = "gpt-5.4"

# ── Auth ─────────────────────────────────────────────────────────────────────
# Loaded from .env as comma-separated user:password pairs
# e.g. USERS="admin:admin123,demo:demo456"
def _load_users() -> dict:
    raw = os.getenv("USERS", "")
    users = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            username, _, password = entry.partition(":")
            users[username.strip()] = password.strip()
    return users

USERS = _load_users()

# ── App settings ──────────────────────────────────────────────────────────────
APP_TITLE  = "USPTO Patent AI"
PAGE_LIMIT = 25
MAX_PAGES  = 40

# ── Scoring thresholds ────────────────────────────────────────────────────────
SCORE_GREEN  = 60
SCORE_YELLOW = 35

# ── USPTO event codes ─────────────────────────────────────────────────────────
OFFICE_ACTION_CODES = {"CTNF", "CTFR", "MCTNF", "MCTFR"}
ALLOWANCE_CODES     = {"M327", "MNDC", "MNAL"}
RCE_CODES           = {"RCE", "RCE2"}
