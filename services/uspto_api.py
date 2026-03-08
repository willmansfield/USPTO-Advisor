"""
USPTO API service – wraps PEDS (Patent Examination Data System) and the
newer Open Data Portal (ODP) endpoints.

All calls are made on-the-fly; results are cached only in st.session_state
(per browser session) to avoid repeated network hits on the same query.
"""

import time
import requests
import streamlit as st
from config import (
    PEDS_API_URL, PEDS_TRANSACTION_URL,
    PTAB_ODP_URL, PTAB_DEVHUB_URL,
    PAGE_LIMIT, MAX_PAGES,
    PATENTED_CODES, ABANDONED_CODES,
    OFFICE_ACTION_CODES, ALLOWANCE_CODES, RCE_CODES,
    USPTO_API_KEY,
)

_HEADERS = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
_TIMEOUT = 30


def _auth_params() -> dict:
    """Return query params dict with API key if configured."""
    return {"api_key": USPTO_API_KEY} if USPTO_API_KEY else {}


# ── Low-level PEDS call ───────────────────────────────────────────────────────

def _peds_query(search_text: str, rows: int = PAGE_LIMIT, start: int = 0) -> dict:
    """POST a Solr-style query to PEDS and return the parsed JSON."""
    payload = {
        "searchText": search_text,
        "qf": "appExamNameText appEarlyPubNumber patentNumber appGroupArtUnitNumber",
        "fl": "*",
        "facet": "false",
        "rows": rows,
        "start": start,
    }
    resp = requests.post(PEDS_API_URL, data=payload, headers=_HEADERS,
                         params=_auth_params(), timeout=_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data.get("queryResults", {}).get("searchResponse", {}).get("response", {})


def _safe_peds(search_text: str, rows: int = PAGE_LIMIT, start: int = 0) -> dict:
    """Wrapper that converts HTTP/network errors into a user-visible Streamlit error."""
    try:
        return _peds_query(search_text, rows, start)
    except requests.HTTPError as e:
        st.error(f"USPTO PEDS API error {e.response.status_code}: {e.response.text[:300]}")
        return {}
    except requests.ConnectionError:
        st.error("Cannot reach USPTO PEDS API. Check your network connection.")
        return {}
    except Exception as e:
        st.error(f"Unexpected error querying PEDS: {e}")
        return {}


# ── Pagination helper ─────────────────────────────────────────────────────────

def _fetch_all_pages(search_text: str, max_pages: int = MAX_PAGES) -> list[dict]:
    """
    Fetch up to max_pages × PAGE_LIMIT records from PEDS.
    Returns flat list of application dicts.
    """
    apps = []
    for page in range(max_pages):
        start = page * PAGE_LIMIT
        result = _safe_peds(search_text, rows=PAGE_LIMIT, start=start)
        if not result:
            break
        docs = result.get("docs", [])
        apps.extend(docs)
        if start + PAGE_LIMIT >= result.get("numFound", 0):
            break
        time.sleep(0.2)   # polite pause
    return apps


# ── Public helpers ────────────────────────────────────────────────────────────

def get_outcome(app: dict) -> str:
    """Classify an application as 'patented', 'abandoned', or 'pending'."""
    code = str(app.get("applicationStatusCode", ""))
    if app.get("patentNumber") or code in PATENTED_CODES:
        return "patented"
    if code in ABANDONED_CODES:
        return "abandoned"
    return "pending"


def count_office_actions(transactions: list[dict]) -> int:
    return sum(1 for t in transactions if t.get("eventCode", "") in OFFICE_ACTION_CODES)


def count_rces(transactions: list[dict]) -> int:
    return sum(1 for t in transactions if t.get("eventCode", "") in RCE_CODES)


def pendency_months(app: dict) -> float | None:
    """Months from filing to disposition (or None if still pending)."""
    from datetime import datetime
    filing = app.get("appFilingDate") or app.get("applicationFilingDate")
    end = app.get("patentIssueDate") or app.get("applicationStatusDate")
    if not filing or not end:
        return None
    try:
        fmt = "%Y-%m-%d"
        delta = datetime.strptime(end[:10], fmt) - datetime.strptime(filing[:10], fmt)
        return round(delta.days / 30.44, 1)
    except Exception:
        return None


# ── Examiner search ───────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def search_by_examiner(name: str) -> list[dict]:
    """
    Return up to MAX_PAGES × PAGE_LIMIT applications assigned to this examiner.
    Cached per session for 1 hour.
    """
    # Try exact match first, then last-name-only
    for query in [f'appExamNameText:("{name}")', f"appExamNameText:({name})"]:
        apps = _fetch_all_pages(query)
        if apps:
            return apps
    return []


@st.cache_data(ttl=3600, show_spinner=False)
def get_application(app_num: str) -> dict:
    """Return full detail for a single application number."""
    clean = app_num.replace("/", "").replace(",", "").strip()
    result = _safe_peds(f'patentApplicationNumber:("{clean}")', rows=1)
    docs = result.get("docs", [])
    return docs[0] if docs else {}


@st.cache_data(ttl=3600, show_spinner=False)
def get_transactions(app_num: str) -> list[dict]:
    """Fetch prosecution transaction history for an application."""
    clean = app_num.replace("/", "").replace(",", "").strip()
    url = PEDS_TRANSACTION_URL.format(app_num=clean)
    try:
        resp = requests.get(url, headers={"Accept": "application/json"},
                            params=_auth_params(), timeout=_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    # Fallback: transactions may be embedded in the main doc
    app = get_application(app_num)
    return app.get("transactions", [])


@st.cache_data(ttl=3600, show_spinner=False)
def search_by_assignee(assignee: str, max_pages: int = MAX_PAGES) -> list[dict]:
    return _fetch_all_pages(f'assigneeEntityName:("{assignee}")', max_pages=max_pages)


@st.cache_data(ttl=3600, show_spinner=False)
def search_by_art_unit(art_unit: str, max_pages: int = MAX_PAGES) -> list[dict]:
    return _fetch_all_pages(f"appGroupArtUnitNumber:({art_unit})", max_pages=max_pages)


@st.cache_data(ttl=3600, show_spinner=False)
def search_applications(
    query_str: str = "",
    app_num: str = "",
    assignee: str = "",
    attorney: str = "",
    art_unit: str = "",
    status: str = "",
    rows: int = 50,
) -> list[dict]:
    """Multi-field application search."""
    parts = []
    if app_num:
        parts.append(f'patentApplicationNumber:("{app_num.strip()}")')
    if assignee:
        parts.append(f'assigneeEntityName:("{assignee.strip()}")')
    if attorney:
        parts.append(f'appAttyDocketNumber:("{attorney.strip()}")')
    if art_unit:
        parts.append(f"appGroupArtUnitNumber:({art_unit.strip()})")
    if status:
        parts.append(f'applicationStatusDescriptionText:("{status.strip()}")')
    if query_str:
        parts.append(query_str.strip())
    if not parts:
        return []
    search = " AND ".join(parts)
    result = _safe_peds(search, rows=rows)
    return result.get("docs", [])


# ── PTAB decisions ────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def search_ptab(
    patent_owner: str = "",
    petitioner: str = "",
    art_unit: str = "",
    rows: int = 25,
) -> list[dict]:
    """
    Search PTAB trial decisions.  Tries ODP first, then legacy Developer Hub.
    """
    params: dict = {"recordTotalQuantity": rows, "recordStartQuantity": 1}
    if patent_owner:
        params["respondentPatentOwnerName"] = patent_owner
    if petitioner:
        params["petitionerPartyName"] = petitioner

    # Try ODP
    try:
        r = requests.get(PTAB_ODP_URL, params={**params, **_auth_params()},
                         headers={"Accept": "application/json"}, timeout=_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            return data.get("results", data.get("decisions", []))
    except Exception:
        pass

    # Fallback: Developer Hub PTAB API
    try:
        r = requests.get(PTAB_DEVHUB_URL, params={**params, **_auth_params()},
                         headers={"Accept": "application/json"}, timeout=_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            return data.get("results", data.get("decisions", []))
    except Exception:
        pass

    return []
