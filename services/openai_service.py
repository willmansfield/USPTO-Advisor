"""
OpenAI service – all GPT interactions for the AI-mode pages.

Requires OPENAI_API_KEY to be set (via .env or environment).
Every public function returns a string; callers should handle empty config gracefully.
"""

from __future__ import annotations

import streamlit as st
from config import OPENAI_API_KEY, OPENAI_MODEL


def _client():
    """Lazily create the OpenAI client so missing key doesn't crash at import."""
    if not OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=OPENAI_API_KEY)
    except ImportError:
        return None


def _check() -> bool:
    """Return True if the API is configured; otherwise show a Streamlit warning."""
    if not OPENAI_API_KEY:
        st.warning(
            "OpenAI API key is not configured.  "
            "Set `OPENAI_API_KEY` in your `.env` file and restart."
        )
        return False
    return True


def _chat(system: str, user: str, temperature: float = 0.3) -> str:
    client = _client()
    if not client:
        return ""
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()


# ── Public AI functions ───────────────────────────────────────────────────────

def examiner_summary(examiner_name: str, stats: dict) -> str:
    """
    Generate a prose narrative about an examiner given their computed stats.
    """
    if not _check():
        return ""

    sys_prompt = (
        "You are a senior patent attorney helping colleagues understand USPTO patent examiners. "
        "Write a concise, professional 2–3 paragraph briefing note about the examiner. "
        "Highlight prosecution difficulty, likely rejection strategies, and practical tips. "
        "Be specific and data-driven. Avoid repeating raw numbers the user can already see."
    )
    user_prompt = f"""
Examiner: {examiner_name}
Difficulty band: {stats.get('band', 'N/A')}
Composite score: {stats.get('score', 'N/A')} / 100
Allowance rate: {stats.get('allowance_rate', 'N/A')} %
Average office actions per disposed application: {stats.get('avg_oa', 'N/A')}
Average pendency (months): {stats.get('avg_pendency', 'N/A')}
RCE rate: {stats.get('rce_rate', 'N/A')} %
Applications analysed: {stats.get('sample_size', 'N/A')}
"""
    return _chat(sys_prompt, user_prompt)


def analyze_office_action(oa_text: str) -> str:
    """Plain-English explanation + key issues from raw OA text."""
    if not _check():
        return ""

    sys_prompt = (
        "You are an expert patent attorney. Analyse the following USPTO Office Action. "
        "Provide: (1) a plain-English summary of each rejection, (2) the legal basis "
        "(35 USC §102, §103, §112, etc.) for each rejection, (3) the key prior art cited, "
        "and (4) the main weaknesses in the examiner's position. "
        "Use clear headings and bullet points."
    )
    return _chat(sys_prompt, oa_text[:8000], temperature=0.2)


def response_strategy(oa_text: str, claims: str) -> str:
    """Draft response arguments given OA text and current claim language."""
    if not _check():
        return ""

    sys_prompt = (
        "You are an expert patent attorney drafting a response to a USPTO Office Action. "
        "Based on the OA and current claims, propose: "
        "(1) claim amendment strategies, (2) argument strategies for each rejection, "
        "(3) likelihood assessment for each strategy, "
        "(4) any interview strategies with the examiner. "
        "Be specific and cite claim elements and cited references by name."
    )
    user_prompt = f"OFFICE ACTION:\n{oa_text[:5000]}\n\nCURRENT CLAIMS:\n{claims[:3000]}"
    return _chat(sys_prompt, user_prompt, temperature=0.3)


def analyze_claims(claims: str, tech_area: str = "") -> str:
    """Pre-filing claim weakness analysis."""
    if not _check():
        return ""

    sys_prompt = (
        "You are a senior patent attorney conducting a pre-filing claim review. "
        "Identify potential: §102 novelty risks, §103 obviousness risks, §112 indefiniteness issues, "
        "claim scope problems, and suggest specific improvements. "
        "Prioritise the most serious issues first."
    )
    user_prompt = f"TECHNOLOGY AREA: {tech_area or 'Not specified'}\n\nCLAIMS:\n{claims[:6000]}"
    return _chat(sys_prompt, user_prompt, temperature=0.2)


def tag_ptab_decision(decision_text: str) -> str:
    """Identify legal issues and key holdings in a PTAB decision."""
    if not _check():
        return ""

    sys_prompt = (
        "You are a PTAB specialist. Analyse this PTAB decision and provide: "
        "(1) outcome (affirmed / reversed / remanded), "
        "(2) legal issues addressed (§102, §103, §112, claim construction, etc.), "
        "(3) key legal holdings (2–4 sentences each), "
        "(4) practical takeaway for patent prosecutors. "
        "Use clear headings."
    )
    return _chat(sys_prompt, decision_text[:8000], temperature=0.2)


def portfolio_summary(entity: str, stats: dict, app_sample: list[dict]) -> str:
    """AI narrative for a company/firm portfolio."""
    if not _check():
        return ""

    sys_prompt = (
        "You are a patent strategy consultant. Write a 3–4 paragraph executive briefing "
        "on the patent prosecution health of the given entity. "
        "Cover: overall prosecution success, examiner difficulty patterns, "
        "technology centre distribution, and 3 specific strategic recommendations."
    )
    top_examiners = {}
    for a in app_sample:
        ex = a.get("appExamNameText", "Unknown")
        top_examiners[ex] = top_examiners.get(ex, 0) + 1
    top5 = sorted(top_examiners.items(), key=lambda x: x[1], reverse=True)[:5]

    user_prompt = f"""
Entity: {entity}
Total applications (sample): {stats.get('total', 'N/A')}
Patented: {stats.get('patented', 'N/A')}
Abandoned: {stats.get('abandoned', 'N/A')}
Pending: {stats.get('pending', 'N/A')}
Overall allowance rate: {stats.get('allowance_rate', 'N/A')} %
Average OAs per app: {stats.get('avg_oa', 'N/A')}
Average pendency: {stats.get('avg_pendency', 'N/A')} months
Top 5 assigned examiners (name: app count): {top5}
"""
    return _chat(sys_prompt, user_prompt, temperature=0.4)


def general_chat(messages: list[dict], live_context: str = "") -> str:
    """
    General patent AI assistant.
    messages: list of {"role": "user"/"assistant", "content": "..."}
    live_context: optional string of live USPTO data to include as context.
    """
    if not _check():
        return ""

    client = _client()
    if not client:
        return ""

    system = (
        "You are PatentAdvisor AI, an expert patent prosecution assistant. "
        "You help patent attorneys, agents, and inventors understand USPTO examination, "
        "prior art, claim strategy, and prosecution statistics. "
        "You have access to live USPTO data when provided in the context. "
        "Be concise, precise, and professional."
    )
    if live_context:
        system += f"\n\nLIVE USPTO CONTEXT:\n{live_context}"

    full_messages = [{"role": "system", "content": system}] + messages

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=full_messages,
        temperature=0.4,
    )
    return resp.choices[0].message.content.strip()
