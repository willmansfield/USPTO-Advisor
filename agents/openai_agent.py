"""
OpenAI agent with streaming tool visibility.

Yields SSE-compatible event dicts:
  {"type": "tool_status",    "tool_id": str, "tool_name": str, "arguments": dict}
  {"type": "tool_result",    "tool_id": str, "tool_name": str, "result": str}
  {"type": "final_response", "response": str, "history": list}
  {"type": "error",          "error": str}
"""

from __future__ import annotations

import json
import logging
from typing import Generator

from config import OPENAI_API_KEY, OPENAI_MODEL

logger = logging.getLogger(__name__)

# ── Tool definitions ──────────────────────────────────────────────────────────

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_application",
            "description": (
                "Look up a specific USPTO patent application by number. "
                "Returns status, examiner, filing date, outcome, and prosecution history."
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
                "Returns matching applications with key details."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "app_num":   {"type": "string", "description": "Application number"},
                    "assignee":  {"type": "string", "description": "Assignee or company name"},
                    "examiner":  {"type": "string", "description": "Examiner last name"},
                    "art_unit":  {"type": "string", "description": "Art unit number"},
                    "status":    {"type": "string", "description": "Application status description"},
                    "free_text": {"type": "string", "description": "Free-text Lucene query"},
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
    {
        "type": "function",
        "function": {
            "name": "get_claims",
            "description": "Fetch the current claims text for a patent application.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_num": {
                        "type": "string",
                        "description": "Application number",
                    }
                },
                "required": ["app_num"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_office_action_documents",
            "description": "List office action documents for a patent application.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_num": {
                        "type": "string",
                        "description": "Application number",
                    }
                },
                "required": ["app_num"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_office_action_text",
            "description": (
                "Download and return the full text of an office action (rejection) document. "
                "Use this to read the actual grounds of rejection, cited prior art, and examiner arguments. "
                "If doc_id is omitted, the most recent office action is automatically selected."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "app_num": {
                        "type": "string",
                        "description": "Application number",
                    },
                    "doc_id": {
                        "type": "string",
                        "description": "Document identifier from get_office_action_documents. Omit to auto-select the latest OA.",
                    },
                },
                "required": ["app_num"],
            },
        },
    },
]

_SYSTEM_PROMPT = (
    "You are USPTO Patent AI, an expert patent prosecution assistant with live access to USPTO data. "
    "You help patent attorneys, agents, and inventors understand USPTO examination practices, "
    "prior art, claim strategy, and prosecution statistics. "
    "\n\n"
    "Use the tools whenever the user asks about specific applications, examiners, art units, "
    "assignees, or PTAB decisions. Always fetch real data before drawing conclusions. "
    "Be concise, precise, and professional. When presenting statistics, explain what they mean "
    "strategically for the user. Use markdown formatting for clarity."
)


# ── Tool dispatcher ───────────────────────────────────────────────────────────

def _dispatch_tool(name: str, args: dict) -> str:
    from services import uspto_api
    from services.scoring import compute_examiner_score
    from services.uspto_api import meta, get_outcome, get_patent_number, count_office_actions, count_rces, pendency_months

    if name == "get_application":
        app = uspto_api.get_application(args["app_num"])
        if not app:
            return f"No application found for {args['app_num']}."
        m = meta(app)
        return "\n".join([
            f"Application: {args['app_num']}",
            f"Title: {m.get('inventionTitle', 'N/A')}",
            f"Status: {m.get('applicationStatusDescriptionText', 'N/A')}",
            f"Filing date: {m.get('filingDate', 'N/A')}",
            f"Examiner: {m.get('examinerNameText', 'N/A')}",
            f"Art unit: {m.get('groupArtUnitNumber', 'N/A')}",
            f"Outcome: {get_outcome(app)}",
            f"Patent number: {get_patent_number(app) or 'N/A'}",
            f"Office actions: {count_office_actions(app)}",
            f"RCEs: {count_rces(app)}",
            f"Pendency (months): {pendency_months(app) or 'pending'}",
        ])

    if name == "search_by_examiner":
        apps = uspto_api.search_by_examiner(args["name"])
        if not apps:
            return f"No applications found for examiner {args['name']}."
        stats = compute_examiner_score(apps)
        return "\n".join([
            f"Examiner: {args['name']}",
            f"Applications sampled: {stats['total']}",
            f"Allowance rate: {stats['allowance_rate']}%",
            f"Average office actions: {stats['avg_oa']}",
            f"Average pendency: {stats['avg_pendency']} months",
            f"RCE rate: {stats['rce_rate']}%",
            f"Difficulty band: {stats['band']}",
            f"Score: {stats['score']} / 100",
        ])

    if name == "search_by_art_unit":
        apps = uspto_api.search_by_art_unit(args["art_unit"])
        if not apps:
            return f"No applications found for art unit {args['art_unit']}."
        stats = compute_examiner_score(apps)
        return "\n".join([
            f"Art unit: {args['art_unit']}",
            f"Applications sampled: {stats['total']}",
            f"Allowance rate: {stats['allowance_rate']}%",
            f"Average office actions: {stats['avg_oa']}",
            f"Average pendency: {stats['avg_pendency']} months",
            f"Difficulty band: {stats['band']}",
            f"Score: {stats['score']} / 100",
        ])

    if name == "search_by_assignee":
        apps = uspto_api.search_by_assignee(args["assignee"])
        if not apps:
            return f"No applications found for assignee {args['assignee']}."
        stats = compute_examiner_score(apps)
        patented = stats["patented"]
        abandoned = stats["abandoned"]
        pending = stats["pending"]
        return "\n".join([
            f"Assignee: {args['assignee']}",
            f"Applications sampled: {stats['total']}",
            f"Patented: {patented} | Abandoned: {abandoned} | Pending: {pending}",
            f"Allowance rate: {stats['allowance_rate']}%",
            f"Average office actions: {stats['avg_oa']}",
            f"Average pendency: {stats['avg_pendency']} months",
            f"Difficulty band: {stats['band']}",
        ])

    if name == "search_applications":
        apps = uspto_api.search_applications(**{k: v for k, v in args.items() if v})
        if not apps:
            return "No applications found matching the criteria."
        lines = [f"Found {len(apps)} applications:"]
        for a in apps[:15]:
            m = meta(a)
            lines.append(
                f"  {a.get('applicationNumberText', '?')} | "
                f"{str(m.get('inventionTitle', 'N/A'))[:60]} | "
                f"{m.get('applicationStatusDescriptionText', 'N/A')} | "
                f"Examiner: {m.get('examinerNameText', 'N/A')}"
            )
        return "\n".join(lines)

    if name == "search_ptab":
        decisions = uspto_api.search_ptab(**args)
        if not decisions:
            return "No PTAB decisions found."
        lines = [f"Found {len(decisions)} PTAB decisions:"]
        for d in decisions[:10]:
            lines.append(
                f"  {d.get('trialNumber', '?')} | "
                f"{d.get('patentOwnerName', 'N/A')} vs {d.get('petitionerPartyName', 'N/A')} | "
                f"{d.get('decisionTypeCategory', 'N/A')}"
            )
        return "\n".join(lines)

    if name == "get_claims":
        text = uspto_api.fetch_claims_text(args["app_num"])
        if not text:
            return f"No claims found for application {args['app_num']}."
        return f"Claims for {args['app_num']}:\n\n{text[:8000]}"

    if name == "get_office_action_documents":
        docs = uspto_api.get_oa_documents(args["app_num"])
        if not docs:
            return f"No office action documents found for {args['app_num']}."
        lines = [f"Found {len(docs)} office action documents:"]
        for d in docs:
            lines.append(
                f"  {d.get('documentCode', '?')} | "
                f"{d.get('officialDate', 'N/A')} | "
                f"ID: {d.get('documentIdentifier', 'N/A')}"
            )
        return "\n".join(lines)

    if name == "get_office_action_text":
        app_num = args["app_num"]
        doc_id  = args.get("doc_id", "").strip()

        # Auto-select the most recent OA if no doc_id provided
        if not doc_id:
            docs = uspto_api.get_oa_documents(app_num)
            if not docs:
                return f"No office action documents found for {app_num}."
            # Sort by date descending and take the latest
            docs_sorted = sorted(docs, key=lambda d: d.get("officialDate", ""), reverse=True)
            doc_id = docs_sorted[0]["documentIdentifier"]
            doc_date = docs_sorted[0].get("officialDate", "N/A")
            doc_code = docs_sorted[0].get("documentCode", "OA")
        else:
            doc_date = "N/A"
            doc_code = "OA"

        try:
            text = uspto_api.fetch_oa_text(app_num, doc_id)
        except Exception as e:
            return f"Failed to download office action text: {e}"

        if not text:
            return f"No text could be extracted from the office action document."

        header = f"Office Action ({doc_code}, {doc_date}) for {app_num}:\n\n"
        # Return up to ~15 000 chars — enough for a full rejection
        return header + text[:15000]

    return f"Unknown tool: {name}"


# ── Agent class ───────────────────────────────────────────────────────────────

class OpenAIAgent:
    def __init__(self):
        self.chat_history: list[dict] = []
        self.model = OPENAI_MODEL

    def _client(self):
        if not OPENAI_API_KEY:
            return None
        try:
            from openai import OpenAI
            return OpenAI(api_key=OPENAI_API_KEY)
        except ImportError:
            return None

    def is_configured(self) -> bool:
        return bool(OPENAI_API_KEY)

    def clear_history(self, **kwargs):
        self.chat_history = []

    def process_message_stream(self, message: str, session_id: str = "") -> Generator[dict, None, None]:
        """
        Synchronous generator that yields SSE event dicts.
        Runs the OpenAI tool-calling loop, emitting events for each tool call
        and the final response.
        """
        if not self.is_configured():
            yield {"type": "error", "error": "OpenAI API key not configured."}
            return

        client = self._client()
        if not client:
            yield {"type": "error", "error": "Could not initialise OpenAI client."}
            return

        # Add user message to history
        self.chat_history.append({"role": "user", "content": message})

        # Build the API messages list (system + history, stripping UI-only keys)
        api_messages = [{"role": "system", "content": _SYSTEM_PROMPT}] + [
            {k: v for k, v in m.items() if k in ("role", "content")}
            for m in self.chat_history
        ]

        tool_call_counter = 0

        for _round in range(6):  # max 6 tool-call rounds
            try:
                logger.info("OpenAI request: round=%d model=%s messages=%d", _round, self.model, len(api_messages))
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=api_messages,
                    tools=_TOOLS,
                    tool_choice="auto",
                    timeout=60,
                )
                logger.info("OpenAI response received: round=%d finish_reason=%s", _round, resp.choices[0].finish_reason)
            except Exception as e:
                logger.error("OpenAI API error: %s", e)
                yield {"type": "error", "error": str(e)}
                return

            msg = resp.choices[0].message

            # No tool calls → final response
            if not msg.tool_calls:
                response_text = (msg.content or "").strip()
                self.chat_history.append({"role": "assistant", "content": response_text})
                yield {
                    "type":     "final_response",
                    "response": response_text,
                    "history":  self.chat_history,
                }
                return

            # There are tool calls — append the assistant turn with tool_calls
            api_messages.append(msg)

            # Emit and execute each tool call
            for tc in msg.tool_calls:
                tool_call_counter += 1
                tool_id   = tc.id
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                # Emit tool_status event (the UI shows this immediately)
                yield {
                    "type":      "tool_status",
                    "tool_id":   tool_id,
                    "tool_name": tool_name,
                    "arguments": tool_args,
                }

                # Execute the tool
                try:
                    result = _dispatch_tool(tool_name, tool_args)
                except Exception as e:
                    result = f"Tool {tool_name} failed: {e}"
                    logger.warning("Tool %s failed: %s", tool_name, e)

                # Emit tool_result event
                yield {
                    "type":      "tool_result",
                    "tool_id":   tool_id,
                    "tool_name": tool_name,
                    "result":    result[:2000],  # truncate for display
                }

                # Add tool result to messages
                api_messages.append({
                    "role":         "tool",
                    "tool_call_id": tool_id,
                    "content":      result,
                })

        # Fallback if we exhausted all rounds
        try:
            resp = client.chat.completions.create(
                model=self.model,
                messages=api_messages,
            )
            response_text = (resp.choices[0].message.content or "").strip()
            self.chat_history.append({"role": "assistant", "content": response_text})
            yield {
                "type":     "final_response",
                "response": response_text,
                "history":  self.chat_history,
            }
        except Exception as e:
            yield {"type": "error", "error": str(e)}
