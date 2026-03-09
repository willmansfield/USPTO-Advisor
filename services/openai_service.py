"""
OpenAI service – all GPT interactions for the AI-mode pages.

Requires OPENAI_API_KEY to be set (via .env or environment).
Every public function returns a string; callers should handle empty config gracefully.
"""

from __future__ import annotations

import json
import streamlit as st
from config import OPENAI_API_KEY, OPENAI_MODEL


def _client():
    """Lazily create the OpenAI client so missing key does not crash at import."""
    if not OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=OPENAI_API_KEY)
    except ImportError:
        return None


def _check() -> bool:
    if not OPENAI_API_KEY:
        st.warning(
            "OpenAI API key is not configured. "
            "Set OPENAI_API_KEY in your .env file and restart."
        )
        return False
    return True


def _chat(system: str, user: str) -> str:
    client = _client()
    if not client:
        return ""
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    return resp.choices[0].message.content.strip()


# ── USPTO tool definitions for function calling ─────────────────────────────────────────────

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_application",
            "description": (
                "Look up a specific USPTO patent application by number. "
                "Returns status, examiner, filing date, outcome, and prosecution history summary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "app_num": {
                        "type": "string",
                        "description": "Application number, e.g. 16123456 or 16/123,456",
                    }
                },
                "required": ["app_num"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_examiner",
            "description": (
                "Get prosecution statistics for a USPTO examiner by name. "
                "Returns allowance rate, average office actions, pendency, RCE rate, and difficulty band."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Examiner last name, or LAST, FIRST format",
                    }
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_art_unit",
            "description": (
                "Get prosecution statistics for a USPTO art unit. "
                "Returns allowance rate, average office actions, and difficulty band."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "art_unit": {
                        "type": "string",
                        "description": "4-digit art unit number, e.g. 2143",
                    }
                },
                "required": ["art_unit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_by_assignee",
            "description": "Get patent portfolio statistics for a company or assignee.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignee": {
                        "type": "string",
                        "description": "Company or assignee name",
                    }
                },
                "required": ["assignee"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_applications",
            "description": (
                "Search USPTO applications by one or more criteria. "
                "Returns a list of matching applications with key details."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "app_num":   {"type": "string", "description": "Application number"},
                    "assignee":  {"type": "string", "description": "Assignee or company name"},
                    "examiner":  {"type": "string", "description": "Examiner last name"},
                    "art_unit":  {"type": "string", "description": "Art unit number"},
                    "status":    {"type": "string", "description": "Application status description"},
                    "free_text": {"type": "string", "description": "Free-text Lucene search query"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_ptab",
            "description": "Search PTAB (Patent Trial and Appeal Board) trial decisions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "patent_owner": {"type": "string", "description": "Patent owner / respondent name"},
                    "petitioner":   {"type": "string", "description": "Petitioner name"},
                },
                "required": [],
            },
        },
    },
]


def _dispatch_tool(name: str, args: dict) -> str:
    """Execute a tool call and return a text result for the model."""
    from services import uspto_api
    from services.scoring import compute_examiner_score
    from services.uspto_api import (
        meta, get_outcome, get_patent_number,
        count_office_actions, count_rces, pendency_months,
    )

    if name == "get_application":
        app = uspto_api.get_application(args["app_num"])
        if not app:
            return "No application found for " + args["app_num"] + "."
        m = meta(app)
        return "\n".join([
            "Application: " + args["app_num"],
            "Title: " + str(m.get("inventionTitle", "N/A")),
            "Status: " + str(m.get("applicationStatusDescriptionText", "N/A")),
            "Filing date: " + str(m.get("filingDate", "N/A")),
            "Examiner: " + str(m.get("examinerNameText", "N/A")),
            "Art unit: " + str(m.get("groupArtUnitNumber", "N/A")),
            "Outcome: " + get_outcome(app),
            "Patent number: " + (get_patent_number(app) or "N/A"),
            "Office actions: " + str(count_office_actions(app)),
            "RCEs: " + str(count_rces(app)),
            "Pendency (months): " + str(pendency_months(app) or "pending"),
        ])

    if name == "search_by_examiner":
        apps = uspto_api.search_by_examiner(args["name"])
        if not apps:
            return "No applications found for examiner " + args["name"] + "."
        stats = compute_examiner_score(apps)
        return "\n".join([
            "Examiner: " + args["name"],
            "Applications sampled: " + str(stats["total"]),
            "Allowance rate: " + str(stats["allowance_rate"]) + " %",
            "Average office actions: " + str(stats["avg_oa"]),
            "Average pendency: " + str(stats["avg_pendency"]) + " months",
            "RCE rate: " + str(stats["rce_rate"]) + " %",
            "Difficulty band: " + str(stats["band"]),
            "Score: " + str(stats["score"]) + " / 100",
        ])

    if name == "search_by_art_unit":
        apps = uspto_api.search_by_art_unit(args["art_unit"])
        if not apps:
            return "No applications found for art unit " + args["art_unit"] + "."
        stats = compute_examiner_score(apps)
        return "\n".join([
            "Art unit: " + args["art_unit"],
            "Applications sampled: " + str(stats["total"]),
            "Allowance rate: " + str(stats["allowance_rate"]) + " %",
            "Average office actions: " + str(stats["avg_oa"]),
            "Average pendency: " + str(stats["avg_pendency"]) + " months",
            "Difficulty band: " + str(stats["band"]),
        ])

    if name == "search_by_assignee":
        apps = uspto_api.search_by_assignee(args["assignee"])
        if not apps:
            return "No applications found for assignee " + args["assignee"] + "."
        stats = compute_examiner_score(apps)
        return "\n".join([
            "Assignee: " + args["assignee"],
            "Applications sampled: " + str(stats["total"]),
            "Allowance rate: " + str(stats["allowance_rate"]) + " %",
            "Average office actions: " + str(stats["avg_oa"]),
            "Average pendency: " + str(stats["avg_pendency"]) + " months",
            "Difficulty band: " + str(stats["band"]),
        ])

    if name == "search_applications":
        apps = uspto_api.search_applications(**{k: v for k, v in args.items() if v})
        if not apps:
            return "No applications found matching the criteria."
        lines = ["Found " + str(len(apps)) + " applications:"]
        for a in apps[:10]:
            m = meta(a)
            lines.append(
                "  " + str(a.get("applicationNumberText", "?")) + " | "
                + str(m.get("inventionTitle", "N/A"))[:60] + " | "
                + str(m.get("applicationStatusDescriptionText", "N/A")) + " | "
                + "Examiner: " + str(m.get("examinerNameText", "N/A"))
            )
        return "\n".join(lines)

    if name == "search_ptab":
        decisions = uspto_api.search_ptab(**args)
        if not decisions:
            return "No PTAB decisions found."
        lines = ["Found " + str(len(decisions)) + " PTAB decisions:"]
        for d in decisions[:10]:
            lines.append(
                "  " + str(d.get("trialNumber", "?")) + " | "
                + str(d.get("patentOwnerName", "N/A")) + " vs "
                + str(d.get("petitionerPartyName", "N/A")) + " | "
                + str(d.get("decisionTypeCategory", "N/A"))
            )
        return "\n".join(lines)

    return "Unknown tool: " + name


# ── Public AI functions ─────────────────────────────────────────────────────

def examiner_summary(examiner_name: str, stats: dict) -> str:
    """Generate a prose narrative about an examiner given their computed stats."""
    if not _check():
        return ""
    sys_prompt = (
        "You are a senior patent attorney helping colleagues understand USPTO patent examiners. "
        "Write a concise, professional 2-3 paragraph briefing note about the examiner. "
        "Highlight prosecution difficulty, likely rejection strategies, and practical tips. "
        "Be specific and data-driven. Avoid repeating raw numbers the user can already see."
    )
    user_prompt = (
        "Examiner: " + examiner_name + "\n"
        + "Difficulty band: " + str(stats.get("band", "N/A")) + "\n"
        + "Composite score: " + str(stats.get("score", "N/A")) + " / 100\n"
        + "Allowance rate: " + str(stats.get("allowance_rate", "N/A")) + " %\n"
        + "Average office actions per disposed application: " + str(stats.get("avg_oa", "N/A")) + "\n"
        + "Average pendency (months): " + str(stats.get("avg_pendency", "N/A")) + "\n"
        + "RCE rate: " + str(stats.get("rce_rate", "N/A")) + " %\n"
        + "Applications analysed: " + str(stats.get("sample_size", "N/A")) + "\n"
    )
    return _chat(sys_prompt, user_prompt)


def analyze_office_action(oa_text: str) -> str:
    """Plain-English explanation + key issues from raw OA text."""
    if not _check():
        return ""
    sys_prompt = (
        "You are an expert patent attorney. Analyse the following USPTO Office Action. "
        "Provide: (1) a plain-English summary of each rejection, (2) the legal basis "
        "(35 USC 102, 103, 112, etc.) for each rejection, (3) the key prior art cited, "
        "and (4) the main weaknesses in the examiner's position. "
        "Use clear headings and bullet points."
    )
    return _chat(sys_prompt, oa_text[:8000])


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
    user_prompt = "OFFICE ACTION:\n" + oa_text[:5000] + "\n\nCURRENT CLAIMS:\n" + claims[:3000]
    return _chat(sys_prompt, user_prompt)


def analyze_claims(claims: str, tech_area: str = "") -> str:
    """Pre-filing claim weakness analysis."""
    if not _check():
        return ""
    sys_prompt = (
        "You are a senior patent attorney conducting a pre-filing claim review. "
        "Identify potential: 102 novelty risks, 103 obviousness risks, 112 indefiniteness issues, "
        "claim scope problems, and suggest specific improvements. "
        "Prioritise the most serious issues first."
    )
    user_prompt = "TECHNOLOGY AREA: " + (tech_area or "Not specified") + "\n\nCLAIMS:\n" + claims[:6000]
    return _chat(sys_prompt, user_prompt)


def tag_ptab_decision(decision_text: str) -> str:
    """Identify legal issues and key holdings in a PTAB decision."""
    if not _check():
        return ""
    sys_prompt = (
        "You are a PTAB specialist. Analyse this PTAB decision and provide: "
        "(1) outcome (affirmed / reversed / remanded), "
        "(2) legal issues addressed (102, 103, 112, claim construction, etc.), "
        "(3) key legal holdings (2-4 sentences each), "
        "(4) practical takeaway for patent prosecutors. "
        "Use clear headings."
    )
    return _chat(sys_prompt, decision_text[:8000])


def portfolio_summary(entity: str, stats: dict, app_sample: list[dict]) -> str:
    """AI narrative for a company/firm portfolio."""
    if not _check():
        return ""
    sys_prompt = (
        "You are a patent strategy consultant. Write a 3-4 paragraph executive briefing "
        "on the patent prosecution health of the given entity. "
        "Cover: overall prosecution success, examiner difficulty patterns, "
        "technology centre distribution, and 3 specific strategic recommendations."
    )
    top_examiners: dict = {}
    for a in app_sample:
        ex = a.get("appExamNameText", "Unknown")
        top_examiners[ex] = top_examiners.get(ex, 0) + 1
    top5 = sorted(top_examiners.items(), key=lambda x: x[1], reverse=True)[:5]
    user_prompt = (
        "Entity: " + entity + "\n"
        + "Total applications (sample): " + str(stats.get("total", "N/A")) + "\n"
        + "Patented: " + str(stats.get("patented", "N/A")) + "\n"
        + "Abandoned: " + str(stats.get("abandoned", "N/A")) + "\n"
        + "Pending: " + str(stats.get("pending", "N/A")) + "\n"
        + "Overall allowance rate: " + str(stats.get("allowance_rate", "N/A")) + " %\n"
        + "Average OAs per app: " + str(stats.get("avg_oa", "N/A")) + "\n"
        + "Average pendency: " + str(stats.get("avg_pendency", "N/A")) + " months\n"
        + "Top 5 assigned examiners: " + str(top5) + "\n"
    )
    return _chat(sys_prompt, user_prompt)


def general_chat(messages: list[dict], use_tools: bool = True) -> tuple[str, list[str]]:
    """
    General patent AI assistant with USPTO tool calling.
    The model decides which USPTO API tools to call based on the conversation.
    Returns (response_text, list_of_tool_call_summaries).
    """
    if not _check():
        return "", []
    client = _client()
    if not client:
        return "", []

    system = (
        "You are PatentAdvisor AI, an expert patent prosecution assistant. "
        "You help patent attorneys, agents, and inventors understand USPTO examination, "
        "prior art, claim strategy, and prosecution statistics. "
        "You have access to live USPTO data via the provided tools. "
        "Use the tools whenever the user asks about specific applications, examiners, "
        "art units, or assignees. Be concise, precise, and professional."
    )

    api_messages = [{"role": "system", "content": system}] + list(messages)
    tool_calls_made: list[str] = []

    for _ in range(5):  # max 5 tool-call rounds
        kwargs: dict = {"model": OPENAI_MODEL, "messages": api_messages}
        if use_tools:
            kwargs["tools"] = _TOOLS
        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        if not msg.tool_calls:
            return (msg.content or "").strip(), tool_calls_made

        # Append assistant turn with tool_calls, then dispatch each
        api_messages.append(msg)
        for tc in msg.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments)
            summary = name + "(" + ", ".join(k + "=" + repr(v) for k, v in args.items()) + ")"
            tool_calls_made.append(summary)
            result = _dispatch_tool(name, args)
            api_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

    # Fallback if loop limit reached
    resp = client.chat.completions.create(model=OPENAI_MODEL, messages=api_messages)
    return (resp.choices[0].message.content or "").strip(), tool_calls_made
