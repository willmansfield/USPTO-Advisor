"""
PatentAdvisor MCP Server.

Exposes USPTO patent data and AI analysis as MCP tools — give this to
any MCP-compatible AI assistant (Claude Desktop, Cursor, etc.) for live
patent research during conversations.

─── Usage ───────────────────────────────────────────────────────────────────

  Stdio transport (Claude Desktop / local LLM):
    python api/mcp_server.py

  HTTP/SSE transport (mounted on FastAPI at /mcp):
    uvicorn api.main:app --port 8000
    Then add to Claude Desktop config:
      { "url": "http://localhost:8000/mcp/sse" }

  Claude Desktop config (stdio mode):
    {
      "mcpServers": {
        "patent-advisor": {
          "command": "python",
          "args": ["/absolute/path/to/PatentAdvisor/api/mcp_server.py"],
          "env": { "USPTO_API_KEY": "your-key", "OPENAI_API_KEY": "sk-..." }
        }
      }
    }
"""

from __future__ import annotations

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from collections import Counter, defaultdict
from mcp.server.fastmcp import FastMCP

from services import uspto_api, openai_service
from services.scoring import compute_examiner_score
from services.uspto_api import (
    meta, get_outcome, get_patent_number, get_assignee,
    count_office_actions, count_rces, pendency_months,
)

mcp = FastMCP(
    "PatentAdvisor",
    instructions=(
        "You have access to live USPTO patent data and AI patent analysis tools. "
        "Use search_examiner to look up examiner difficulty profiles. "
        "Use search_art_unit to explore a technology area's examiner landscape. "
        "Use get_application for a specific application's prosecution history. "
        "Use search_applications to find applications by assignee, examiner, art unit, or status. "
        "Use get_company_portfolio for a company's overall prosecution health. "
        "Use search_ptab_decisions for IPR/PGR/CBM trial research. "
        "Use analyze_office_action or check_patent_claims for AI-powered analysis "
        "(requires OPENAI_API_KEY)."
    ),
)


# ── Data tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def search_examiner(examiner_name: str) -> str:
    """
    Look up a USPTO patent examiner's prosecution profile.

    Returns difficulty score (0–100), band (Easy / Moderate / Difficult),
    allowance rate, average office actions per application, average
    pendency in months, and RCE rate. Based on up to 200 recent applications.

    Args:
        examiner_name: Last name (e.g. "SMITH") or "LAST, FIRST" format.
    """
    apps = uspto_api.search_by_examiner(examiner_name)
    if not apps:
        return f"No applications found for examiner: {examiner_name}"
    stats = compute_examiner_score(apps)
    names = [meta(a).get("examinerNameText", "") for a in apps]
    art_units = [meta(a).get("groupArtUnitNumber", "") for a in apps]
    canonical = Counter(n for n in names if n).most_common(1)
    primary_au = Counter(au for au in art_units if au).most_common(1)
    return "\n".join([
        f"Examiner:          {canonical[0][0] if canonical else examiner_name}",
        f"Primary art unit:  {primary_au[0][0] if primary_au else 'N/A'}",
        f"Difficulty:        {stats['band']}  (Score: {stats['score']}/100)",
        f"Allowance rate:    {stats['allowance_rate']}%",
        f"Avg office actions:{stats['avg_oa']}",
        f"Avg pendency:      {stats['avg_pendency']} months",
        f"RCE rate:          {stats['rce_rate']}%",
        f"Sample size:       {stats['sample_size']} applications",
    ])


@mcp.tool()
def search_art_unit(art_unit: str) -> str:
    """
    Get prosecution statistics for a 4-digit USPTO art unit.

    Returns overall difficulty, allowance rate, and a ranked list of
    examiners with individual difficulty scores (easiest to hardest).

    Args:
        art_unit: 4-digit art unit number (e.g. "2143").
    """
    apps = uspto_api.search_by_art_unit(art_unit)
    if not apps:
        return f"No applications found for art unit: {art_unit}"
    overall = compute_examiner_score(apps)
    by_examiner: dict = defaultdict(list)
    for a in apps:
        ex = meta(a).get("examinerNameText", "Unknown")
        by_examiner[ex].append(a)
    scored = sorted(
        [(ex, ex_apps, compute_examiner_score(ex_apps)) for ex, ex_apps in by_examiner.items()],
        key=lambda x: x[2].get("score") or 0,
        reverse=True,
    )
    examiner_lines = [
        f"  {ex}: {s['band']} ({s['score']}/100, {s['allowance_rate']}% allow, {len(ea)} apps)"
        for ex, ea, s in scored
    ]
    return "\n".join([
        f"Art Unit:         {art_unit}",
        f"Overall:          {overall['band']} (Score: {overall['score']}/100)",
        f"Allowance rate:   {overall['allowance_rate']}%",
        f"Avg office actions:{overall['avg_oa']}",
        f"Avg pendency:     {overall['avg_pendency']} months",
        f"Sample size:      {overall['sample_size']} applications",
        "",
        f"Examiners ({len(by_examiner)} found, ranked easiest → hardest):",
    ] + examiner_lines)


@mcp.tool()
def get_application(application_number: str) -> str:
    """
    Fetch details for a US patent application.

    Returns title, status, examiner, art unit, assignee, patent number
    (if granted), filing date, office action count, and recent prosecution events.

    Args:
        application_number: Application number (e.g. "16439518" or "16/439,518").
    """
    app_data = uspto_api.get_application(application_number)
    if not app_data:
        return f"Application not found: {application_number}"
    m = meta(app_data)
    events = (app_data.get("eventDataBag") or [])[:15]
    event_lines = [
        f"  {e.get('eventDate', '')}  [{e.get('eventCode', '')}]  {e.get('eventDescriptionText', '')}"
        for e in events
    ]
    return "\n".join([
        f"Application:    {application_number}",
        f"Title:          {m.get('inventionTitle', '')}",
        f"Status:         {m.get('applicationStatusDescriptionText', '')}",
        f"Filing date:    {m.get('filingDate', '')}",
        f"Examiner:       {m.get('examinerNameText', '')}",
        f"Art unit:       {m.get('groupArtUnitNumber', '')}",
        f"Assignee:       {get_assignee(app_data)}",
        f"Patent number:  {get_patent_number(app_data) or 'N/A'}",
        f"Outcome:        {get_outcome(app_data)}",
        f"Office actions: {count_office_actions(app_data)}",
        f"RCEs:           {count_rces(app_data)}",
        f"Pendency:       {pendency_months(app_data) or 'pending'} months",
        "",
        "Recent prosecution events:",
    ] + event_lines)


@mcp.tool()
def search_applications(
    assignee: str = "",
    examiner: str = "",
    art_unit: str = "",
    status: str = "",
    free_text: str = "",
    rows: int = 20,
) -> str:
    """
    Search USPTO patent applications by multiple criteria.

    Provide at least one non-empty parameter.
    Status options: 'Patented Case', 'Abandoned', 'Pending', 'Published'.

    Args:
        assignee:  Company or applicant name.
        examiner:  Examiner last name.
        art_unit:  4-digit art unit number.
        status:    Application status description.
        free_text: Lucene query (e.g. "machine learning AND neural network").
        rows:      Max results to return (default 20, max 200).
    """
    if not any([assignee, examiner, art_unit, status, free_text]):
        return "Error: provide at least one search criterion."
    apps = uspto_api.search_applications(
        assignee=assignee, examiner=examiner, art_unit=art_unit,
        status=status, free_text=free_text, rows=rows,
    )
    if not apps:
        return "No applications found matching the criteria."
    lines = [f"Found {len(apps)} applications:"]
    for a in apps[:20]:
        m = meta(a)
        lines.append(
            f"  {a.get('applicationNumberText', '?')} | "
            f"{str(m.get('inventionTitle', ''))[:50]} | "
            f"{m.get('applicationStatusDescriptionText', '')} | "
            f"Examiner: {m.get('examinerNameText', '')} | "
            f"AU: {m.get('groupArtUnitNumber', '')}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_company_portfolio(company_name: str) -> str:
    """
    Get patent prosecution portfolio statistics for a company.

    Returns allowance rate, filing trend, top examiners, art unit
    distribution, and overall prosecution health.

    Args:
        company_name: Company or assignee name (e.g. "Apple Inc").
    """
    apps = uspto_api.search_by_assignee(company_name)
    if not apps:
        return f"No applications found for: {company_name}"
    stats = compute_examiner_score(apps)
    examiners = Counter(meta(a).get("examinerNameText", "") for a in apps)
    art_units = Counter(meta(a).get("groupArtUnitNumber", "") for a in apps)
    years = Counter(
        str(meta(a).get("filingDate", ""))[:4]
        for a in apps if meta(a).get("filingDate", "")
    )
    top_ex = "\n".join(f"  {n}: {c} apps" for n, c in examiners.most_common(5))
    top_au = "\n".join(f"  AU {au}: {c} apps" for au, c in art_units.most_common(5))
    trend = " | ".join(f"{yr}: {cnt}" for yr, cnt in sorted(years.items())[-6:])
    return "\n".join([
        f"Portfolio:        {company_name}",
        f"Total (sample):   {stats['total']}",
        f"Patented:         {stats['patented']}  Abandoned: {stats['abandoned']}  Pending: {stats['pending']}",
        f"Allowance rate:   {stats['allowance_rate']}%",
        f"Avg OAs:          {stats['avg_oa']}",
        f"Avg pendency:     {stats['avg_pendency']} months",
        f"Difficulty band:  {stats['band']}",
        "",
        "Top examiners:",
        top_ex,
        "",
        "Top art units:",
        top_au,
        "",
        "Filing trend (recent years):",
        trend,
    ])


@mcp.tool()
def search_ptab_decisions(
    patent_owner: str = "",
    petitioner: str = "",
    rows: int = 25,
) -> str:
    """
    Search PTAB inter partes review (IPR), post-grant review (PGR),
    and covered business method (CBM) trial decisions.

    Args:
        patent_owner: Patent owner / respondent name.
        petitioner:   Petitioner / challenger name.
        rows:         Max results (default 25).
    """
    if not patent_owner and not petitioner:
        return "Error: provide at least patent_owner or petitioner."
    decisions = uspto_api.search_ptab(
        patent_owner=patent_owner, petitioner=petitioner, rows=rows
    )
    if not decisions:
        return "No PTAB decisions found."
    lines = [f"Found {len(decisions)} PTAB decisions:"]
    for d in decisions:
        lines.append(
            f"  {d.get('trialNumber', '?')} | "
            f"{d.get('trialTypeCategory', '?')} | "
            f"{d.get('prosecutionStatus', '?')} | "
            f"{d.get('patentOwnerName', '?')} vs {d.get('petitionerPartyName', '?')} | "
            f"Patent: {d.get('patentNumber', '?')}"
        )
    return "\n".join(lines)


# ── AI tools ──────────────────────────────────────────────────────────────────

@mcp.tool()
def analyze_office_action(office_action_text: str) -> str:
    """
    AI-powered analysis of a USPTO Office Action.

    Explains each rejection in plain English, identifies the legal basis
    (§102 / §103 / §112), summarises cited prior art, highlights weaknesses
    in the examiner's position, and recommends response strategies.

    Requires OPENAI_API_KEY to be configured in the environment.

    Args:
        office_action_text: Full text of the office action.
    """
    if not openai_service._check():
        return "OPENAI_API_KEY not configured. Set it in .env or environment variables."
    return openai_service.analyze_office_action(office_action_text)


@mcp.tool()
def check_patent_claims(
    claims_text: str,
    technology_area: str = "",
    target_art_unit: str = "",
) -> str:
    """
    Pre-filing patent claim analysis for potential rejection risks.

    Identifies §102 novelty risks, §103 obviousness risks, §112 indefiniteness
    issues, and claim scope problems. Recommends specific improvements.
    Optionally fetches live art unit context to tailor the analysis.

    Requires OPENAI_API_KEY to be configured in the environment.

    Args:
        claims_text:      The patent claims text to analyse.
        technology_area:  Technology description (e.g. "Software / G06F").
        target_art_unit:  Target 4-digit art unit for examiner context.
    """
    if not openai_service._check():
        return "OPENAI_API_KEY not configured. Set it in .env or environment variables."
    tech = technology_area
    if target_art_unit:
        au_apps = uspto_api.search_by_art_unit(target_art_unit)
        if au_apps:
            s = compute_examiner_score(au_apps)
            tech += (
                f" | Art Unit {target_art_unit}: "
                f"{s['allowance_rate']}% allowance, {s['avg_oa']} avg OAs, {s['band']}"
            )
    return openai_service.analyze_claims(claims_text, tech_area=tech)


if __name__ == "__main__":
    mcp.run()  # stdio transport – for Claude Desktop
