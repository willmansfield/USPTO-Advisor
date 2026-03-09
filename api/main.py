"""
PatentAdvisor FastAPI backend.

Start with:  uvicorn api.main:app --reload --port 8000

REST endpoints at /api/*
MCP server (SSE) at /mcp  – connect Claude Desktop or any MCP client here.
Interactive docs at /docs
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from collections import Counter, defaultdict
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from services import uspto_api, openai_service
from services.scoring import compute_examiner_score
from services.uspto_api import (
    meta, get_outcome, get_patent_number, get_assignee,
    count_office_actions, count_rces, pendency_months,
)

app = FastAPI(
    title="PatentAdvisor API",
    version="1.0.0",
    description=(
        "Live USPTO patent data and AI analysis. "
        "MCP server available at /mcp for use with Claude Desktop or any MCP client."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount MCP server ──────────────────────────────────────────────────────────

try:
    from api.mcp_server import mcp
    # sse_app() = SSE transport; streamable_http_app() = newer HTTP transport
    app.mount("/mcp", mcp.sse_app())
except Exception as e:
    import logging
    logging.warning("MCP server not mounted: %s", e)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "version": "1.0.0"}


# ── Examiner ──────────────────────────────────────────────────────────────────

@app.get("/api/examiner/{name}", tags=["Data"])
def get_examiner(name: str):
    """Examiner difficulty profile: score, allowance rate, avg OAs, pendency, RCE rate."""
    apps = uspto_api.search_by_examiner(name)
    if not apps:
        raise HTTPException(404, f"No applications found for examiner: {name}")
    stats = compute_examiner_score(apps)
    names = [meta(a).get("examinerNameText", "") for a in apps]
    art_units = [meta(a).get("groupArtUnitNumber", "") for a in apps]
    canonical = Counter(n for n in names if n).most_common(1)
    primary_au = Counter(au for au in art_units if au).most_common(1)
    return {
        **stats,
        "canonical_name": canonical[0][0] if canonical else name,
        "primary_art_unit": primary_au[0][0] if primary_au else None,
        "sample_count": len(apps),
    }


# ── Art Unit ──────────────────────────────────────────────────────────────────

@app.get("/api/art-unit/{code}", tags=["Data"])
def get_art_unit(code: str):
    """Art unit overview + ranked examiner roster with individual difficulty scores."""
    apps = uspto_api.search_by_art_unit(code)
    if not apps:
        raise HTTPException(404, f"No applications found for art unit: {code}")
    overall = compute_examiner_score(apps)
    by_examiner: dict = defaultdict(list)
    for a in apps:
        ex = meta(a).get("examinerNameText", "Unknown")
        by_examiner[ex].append(a)
    examiners = []
    for ex_name, ex_apps in by_examiner.items():
        s = compute_examiner_score(ex_apps)
        examiners.append({"name": ex_name, "app_count": len(ex_apps), **s})
    examiners.sort(key=lambda x: x.get("score") or 0, reverse=True)
    return {"art_unit": code, "overall": overall, "examiners": examiners}


# ── Application ───────────────────────────────────────────────────────────────

@app.get("/api/application/{app_num}", tags=["Data"])
def get_application(app_num: str):
    """Full application metadata: status, examiner, art unit, assignee, outcome."""
    app_data = uspto_api.get_application(app_num)
    if not app_data:
        raise HTTPException(404, f"Application not found: {app_num}")
    m = meta(app_data)
    return {
        "application_number": app_num,
        "title": m.get("inventionTitle", ""),
        "status": m.get("applicationStatusDescriptionText", ""),
        "status_code": m.get("applicationStatusCode", ""),
        "filing_date": m.get("filingDate", ""),
        "effective_filing_date": m.get("effectiveFilingDate", ""),
        "examiner": m.get("examinerNameText", ""),
        "art_unit": m.get("groupArtUnitNumber", ""),
        "assignee": get_assignee(app_data),
        "patent_number": get_patent_number(app_data),
        "outcome": get_outcome(app_data),
        "office_action_count": count_office_actions(app_data),
        "rce_count": count_rces(app_data),
        "pendency_months": pendency_months(app_data),
        "cpc_classifications": m.get("cpcClassificationBag", []),
    }


@app.get("/api/application/{app_num}/transactions", tags=["Data"])
def get_transactions(app_num: str):
    """Full prosecution event history for an application."""
    txns = uspto_api.get_transactions(app_num)
    return {"application_number": app_num, "transactions": txns}


@app.get("/api/application/{app_num}/documents", tags=["Data"])
def get_documents(app_num: str):
    """List of all IFW file wrapper documents."""
    docs = uspto_api.get_all_documents(app_num)
    return {"application_number": app_num, "documents": docs}


@app.get("/api/application/{app_num}/oa/{doc_id}", tags=["Data"])
def get_oa_text(app_num: str, doc_id: str):
    """Extract text from an office action document."""
    text = uspto_api.fetch_oa_text(app_num, doc_id)
    return {"text": text}


@app.get("/api/application/{app_num}/claims", tags=["Data"])
def get_claims(app_num: str):
    """Extract current claims from the file wrapper."""
    text = uspto_api.fetch_claims_text(app_num)
    return {"claims": text}


# ── Search ────────────────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    app_num: Optional[str] = None
    assignee: Optional[str] = None
    examiner: Optional[str] = None
    art_unit: Optional[str] = None
    status: Optional[str] = None
    free_text: Optional[str] = None
    rows: int = 20


@app.post("/api/search", tags=["Data"])
def search(req: SearchRequest):
    """Multi-field application search."""
    apps = uspto_api.search_applications(
        app_num=req.app_num or "",
        assignee=req.assignee or "",
        examiner=req.examiner or "",
        art_unit=req.art_unit or "",
        status=req.status or "",
        free_text=req.free_text or "",
        rows=req.rows,
    )
    results = []
    for a in apps:
        m = meta(a)
        results.append({
            "application_number": a.get("applicationNumberText", ""),
            "title": m.get("inventionTitle", ""),
            "filing_date": m.get("filingDate", ""),
            "examiner": m.get("examinerNameText", ""),
            "art_unit": m.get("groupArtUnitNumber", ""),
            "status": m.get("applicationStatusDescriptionText", ""),
            "status_date": m.get("applicationStatusDate", ""),
            "patent_number": get_patent_number(a),
            "assignee": get_assignee(a),
            "outcome": get_outcome(a),
        })
    return {"count": len(results), "results": results}


# ── Portfolio ─────────────────────────────────────────────────────────────────

@app.get("/api/portfolio/{assignee:path}", tags=["Data"])
def get_portfolio(assignee: str):
    """Company portfolio: aggregate stats, top examiners, art unit distribution."""
    apps = uspto_api.search_by_assignee(assignee)
    if not apps:
        raise HTTPException(404, f"No applications found for: {assignee}")
    stats = compute_examiner_score(apps)
    examiners = Counter(meta(a).get("examinerNameText", "") for a in apps)
    art_units = Counter(meta(a).get("groupArtUnitNumber", "") for a in apps)
    years = Counter(
        str(meta(a).get("filingDate", ""))[:4]
        for a in apps if meta(a).get("filingDate", "")
    )
    return {
        "assignee": assignee,
        "stats": stats,
        "top_examiners": examiners.most_common(20),
        "art_unit_distribution": art_units.most_common(20),
        "filing_by_year": dict(sorted(years.items())),
        "sample_count": len(apps),
    }


# ── PTAB ──────────────────────────────────────────────────────────────────────

class PTABRequest(BaseModel):
    patent_owner: Optional[str] = None
    petitioner: Optional[str] = None
    rows: int = 25


@app.post("/api/ptab", tags=["Data"])
def ptab_search(req: PTABRequest):
    """Search PTAB IPR/PGR/CBM trial decisions."""
    decisions = uspto_api.search_ptab(
        patent_owner=req.patent_owner or "",
        petitioner=req.petitioner or "",
        rows=req.rows,
    )
    return {"count": len(decisions), "decisions": decisions}


# ── AI endpoints ──────────────────────────────────────────────────────────────

def _ai_guard():
    if not openai_service._check():
        raise HTTPException(503, "OPENAI_API_KEY not configured")


class ExaminerBriefRequest(BaseModel):
    examiner_name: str
    stats: dict


@app.post("/api/ai/examiner-brief", tags=["AI"])
def ai_examiner_brief(req: ExaminerBriefRequest):
    """AI narrative brief on an examiner's prosecution style and strategy tips."""
    _ai_guard()
    return {"analysis": openai_service.examiner_summary(req.examiner_name, req.stats)}


class OARequest(BaseModel):
    oa_text: str


@app.post("/api/ai/oa-analysis", tags=["AI"])
def ai_oa_analysis(req: OARequest):
    """AI plain-English explanation of an office action: rejections, §102/103/112, prior art."""
    _ai_guard()
    return {"analysis": openai_service.analyze_office_action(req.oa_text)}


class StrategyRequest(BaseModel):
    oa_text: str
    claims: str


@app.post("/api/ai/response-strategy", tags=["AI"])
def ai_response_strategy(req: StrategyRequest):
    """AI-drafted response strategy: amendment options, arguments, interview tips."""
    _ai_guard()
    return {"strategy": openai_service.response_strategy(req.oa_text, req.claims)}


class ClaimsRequest(BaseModel):
    claims: str
    tech_area: Optional[str] = None
    art_unit: Optional[str] = None


@app.post("/api/ai/claim-check", tags=["AI"])
def ai_claim_check(req: ClaimsRequest):
    """Pre-filing claim analysis: §102/103/112 risks, scope issues, improvement suggestions."""
    _ai_guard()
    tech = req.tech_area or ""
    if req.art_unit:
        au_apps = uspto_api.search_by_art_unit(req.art_unit)
        if au_apps:
            s = compute_examiner_score(au_apps)
            tech += (
                f" | Art Unit {req.art_unit}: "
                f"{s['allowance_rate']}% allowance, {s['avg_oa']} avg OAs"
            )
    return {"analysis": openai_service.analyze_claims(req.claims, tech_area=tech)}


class PortfolioReportRequest(BaseModel):
    entity: str
    stats: dict
    app_sample: list = []


@app.post("/api/ai/portfolio-report", tags=["AI"])
def ai_portfolio_report(req: PortfolioReportRequest):
    """AI executive summary of a company's patent prosecution health."""
    _ai_guard()
    return {"report": openai_service.portfolio_summary(req.entity, req.stats, req.app_sample)}


class ChatRequest(BaseModel):
    messages: list
    use_tools: bool = True


@app.post("/api/ai/chat", tags=["AI"])
def ai_chat(req: ChatRequest):
    """Multi-turn patent AI chat with live USPTO tool calling."""
    _ai_guard()
    response, tool_calls = openai_service.general_chat(req.messages, req.use_tools)
    return {"response": response, "tool_calls": tool_calls}


class PTABAnalysisRequest(BaseModel):
    decision_text: str


@app.post("/api/ai/ptab-analysis", tags=["AI"])
def ai_ptab_analysis(req: PTABAnalysisRequest):
    """AI analysis of a PTAB decision: outcome, legal issues, holdings, prosecutor takeaway."""
    _ai_guard()
    return {"analysis": openai_service.tag_ptab_decision(req.decision_text)}
