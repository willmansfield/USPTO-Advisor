"""
USPTO API service – uses the USPTO Open Data Portal (ODP) REST API.
Base: https://api.uspto.gov/api/v1/patent/

Auth: api_key query param  +  X-API-KEY header  (both required).
SSL:  verify=False used because this environment's cert store has a clock-skew
      issue; remove in production if not needed.

Key ODP response schema (patentFileWrapperDataBag[]):
  applicationNumberText
  applicationMetaData:
    inventionTitle, filingDate, applicationStatusCode (int),
    applicationStatusDescriptionText, applicationStatusDate,
    examinerNameText ("LAST, FIRST M"), groupArtUnitNumber ("2143"),
    firstApplicantName, firstInventorName, cpcClassificationBag
  eventDataBag[]:  { eventCode, eventDescriptionText, eventDate }
  assignmentBag[]: { assigneeBag[].assigneeNameText, ... }
  grantDocumentMetaData: { patentNumber }  (present when granted)
"""

from __future__ import annotations

import time
import urllib3
import requests
import streamlit as st

from config import (
    USPTO_API_KEY, PAGE_LIMIT, MAX_PAGES,
    OFFICE_ACTION_CODES, RCE_CODES,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_BASE      = "https://api.uspto.gov/api/v1/patent"
_PTAB_URL  = f"{_BASE}/trials/decisions/search"
_APPS_URL  = f"{_BASE}/applications/search"
_TIMEOUT   = 20


# ── Auth + low-level HTTP ─────────────────────────────────────────────────────

def _auth() -> tuple[dict, dict]:
    """Return (params_dict, headers_dict) with credentials."""
    return (
        {"api_key": USPTO_API_KEY},
        {"Accept": "application/json", "X-API-KEY": USPTO_API_KEY},
    )


def _get(url: str, extra_params: dict | None = None) -> dict:
    p, h = _auth()
    if extra_params:
        p.update(extra_params)
    r = requests.get(url, params=p, headers=h, timeout=_TIMEOUT, verify=False)
    r.raise_for_status()
    return r.json()


def _apps_query(q: str, limit: int = PAGE_LIMIT, offset: int = 0) -> dict:
    return _get(_APPS_URL, {"q": q, "limit": limit, "offset": offset})


def _safe_query(q: str, limit: int = PAGE_LIMIT, offset: int = 0) -> dict:
    try:
        return _apps_query(q, limit, offset)
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return {}  # No results found � not a real error
        st.error(f"USPTO API {e.response.status_code}: {e.response.text[:300]}")
    except requests.ConnectionError:
        st.error("Cannot reach USPTO API. Check network connection.")
    except Exception as e:
        st.error(f"USPTO API error: {e}")
    return {}


def _fetch_all(q: str, max_pages: int = MAX_PAGES) -> list[dict]:
    """Paginate up to max_pages × PAGE_LIMIT records."""
    records: list[dict] = []
    for page in range(max_pages):
        offset = page * PAGE_LIMIT
        data = _safe_query(q, limit=PAGE_LIMIT, offset=offset)
        if not data:
            break
        docs = data.get("patentFileWrapperDataBag", [])
        records.extend(docs)
        total = data.get("count", 0)
        if offset + PAGE_LIMIT >= total or not docs:
            break
        time.sleep(0.25)
    return records


# ── Field helpers ─────────────────────────────────────────────────────────────

def meta(app: dict) -> dict:
    return app.get("applicationMetaData", {})


def get_outcome(app: dict) -> str:
    m    = meta(app)
    code = m.get("applicationStatusCode")
    desc = (m.get("applicationStatusDescriptionText") or "").lower()

    if isinstance(code, int) and 150 <= code <= 160:
        return "patented"
    if app.get("grantDocumentMetaData"):
        return "patented"
    if "patented" in desc:
        return "patented"
    if isinstance(code, int) and code >= 161:
        return "abandoned"
    if "abandon" in desc:
        return "abandoned"
    return "pending"


def get_patent_number(app: dict) -> str:
    gdm = app.get("grantDocumentMetaData") or {}
    return gdm.get("patentNumber", "")


def get_assignee(app: dict) -> str:
    name = meta(app).get("firstApplicantName", "")
    if name:
        return name
    for ab in (app.get("assignmentBag") or []):
        for a in (ab.get("assigneeBag") or []):
            n = a.get("assigneeNameText", "")
            if n:
                return n
    return ""


def count_office_actions(app: dict) -> int:
    return sum(1 for e in (app.get("eventDataBag") or [])
               if e.get("eventCode", "") in OFFICE_ACTION_CODES)


def count_rces(app: dict) -> int:
    return sum(1 for e in (app.get("eventDataBag") or [])
               if e.get("eventCode", "") in RCE_CODES)


def pendency_months(app: dict) -> float | None:
    from datetime import datetime
    m       = meta(app)
    filing  = m.get("filingDate") or m.get("effectiveFilingDate")
    end     = m.get("applicationStatusDate")
    outcome = get_outcome(app)
    if not filing or not end or outcome == "pending":
        return None
    try:
        delta = (datetime.strptime(end[:10], "%Y-%m-%d")
                 - datetime.strptime(filing[:10], "%Y-%m-%d"))
        return round(delta.days / 30.44, 1)
    except Exception:
        return None


# ── Public search functions ───────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def search_by_examiner(name: str) -> list[dict]:
    """Fetch applications for an examiner by last name (or 'LAST, FIRST')."""
    last = name.split(",")[0].strip()
    for q in [
        f'applicationMetaData.examinerNameText:"{name.upper()}"',
        f"applicationMetaData.examinerNameText:{last.upper()}",
    ]:
        apps = _fetch_all(q)
        if apps:
            return apps
    return []


@st.cache_data(ttl=3600, show_spinner=False)
def search_by_art_unit(art_unit: str) -> list[dict]:
    return _fetch_all(f"applicationMetaData.groupArtUnitNumber:{art_unit.strip()}")


@st.cache_data(ttl=3600, show_spinner=False)
def search_by_assignee(assignee: str) -> list[dict]:
    for q in [
        f'applicationMetaData.firstApplicantName:"{assignee}"',
        f'assignmentBag.assigneeBag.assigneeNameText:"{assignee}"',
        f"applicationMetaData.firstApplicantName:{assignee.split()[0]}",
    ]:
        apps = _fetch_all(q)
        if apps:
            return apps
    return []


@st.cache_data(ttl=3600, show_spinner=False)
def get_application(app_num: str) -> dict:
    clean = app_num.replace("/", "").replace(",", "").replace(" ", "").strip()
    data  = _safe_query(f"applicationNumberText:{clean}", limit=1)
    docs  = data.get("patentFileWrapperDataBag", [])
    return docs[0] if docs else {}


@st.cache_data(ttl=3600, show_spinner=False)
def get_transactions(app_num: str) -> list[dict]:
    app = get_application(app_num)
    return app.get("eventDataBag", [])


@st.cache_data(ttl=3600, show_spinner=False)
def search_applications(
    app_num:   str = "",
    assignee:  str = "",
    examiner:  str = "",
    art_unit:  str = "",
    status:    str = "",
    free_text: str = "",
    rows:      int = 50,
) -> list[dict]:
    parts = []
    if app_num:
        parts.append(f"applicationNumberText:{app_num.replace('/', '').replace(',', '').strip()}")
    if assignee:
        parts.append(f'applicationMetaData.firstApplicantName:"{assignee.strip()}"')
    if examiner:
        parts.append(f"applicationMetaData.examinerNameText:{examiner.strip().split(',')[0].upper()}")
    if art_unit:
        parts.append(f"applicationMetaData.groupArtUnitNumber:{art_unit.strip()}")
    if status:
        parts.append(f'applicationMetaData.applicationStatusDescriptionText:"{status.strip()}"')
    if free_text:
        parts.append(free_text.strip())
    if not parts:
        return []
    data = _safe_query(" AND ".join(parts), limit=rows)
    return data.get("patentFileWrapperDataBag", [])


# ── PTAB decisions ────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def search_ptab(
    patent_owner: str = "",
    petitioner:   str = "",
    rows:         int = 25,
) -> list[dict]:
    params: dict = {"recordTotalQuantity": rows, "recordStartQuantity": 1}
    if patent_owner:
        params["respondentPatentOwnerName"] = patent_owner
    if petitioner:
        params["petitionerPartyName"] = petitioner
    try:
        p, h = _auth()
        p.update(params)
        r = requests.get(_PTAB_URL, params=p, headers=h,
                         timeout=_TIMEOUT, verify=False)
        if r.status_code == 200:
            return r.json().get("patentTrialDocumentDataBag", [])
    except Exception as e:
        st.error(f"PTAB API error: {e}")
    return []


@st.cache_data(ttl=3600, show_spinner=False)
def get_oa_documents(app_num: str) -> list[dict]:
    """Return IFW Office Action documents for an application (with XML archive URLs)."""
    OA_CODES = {"CTNF", "CTFR", "MCTNF", "MCTFR"}
    clean = app_num.replace("/", "").replace(",", "").replace(" ", "").strip()
    url = f"{_BASE}/applications/{clean}/documents"
    try:
        data = _get(url)
    except Exception:
        return []
    return [doc for doc in data.get("documentBag", []) if doc.get("documentCode") in OA_CODES]


def fetch_oa_text(app_num: str, doc_identifier: str) -> str:
    """Download the XML archive for an OA document and return extracted plain text."""
    import io
    import re as _re
    import tarfile
    import xml.etree.ElementTree as ET

    clean = app_num.replace("/", "").replace(",", "").replace(" ", "").strip()
    url = f"https://api.uspto.gov/api/v1/download/applications/{clean}/{doc_identifier}/xmlarchive"
    p, h = _auth()
    r = requests.get(url, params=p, headers=h, timeout=30, verify=False)
    r.raise_for_status()

    tf = tarfile.open(fileobj=io.BytesIO(r.content))
    xml_str = tf.extractfile(tf.getmembers()[0]).read().decode("utf-8", errors="replace")

    # Strip processing instructions that ElementTree cannot handle mid-document
    xml_str = _re.sub("<[?][^?]+[?]>", "", xml_str)

    root = ET.fromstring(xml_str)
    USCOM = "urn:us:gov:doc:uspto:common"
    paragraphs = [
        "".join(el.itertext()).strip()
        for el in root.iter("{" + USCOM + "}P")
    ]
    newline = chr(10)
    return (newline + newline).join(t for t in paragraphs if t)



def _text_no_del(el):
    """Collect all text from el, skipping com:Del subtrees (for amended claims)."""
    COM_DEL = "{http://www.wipo.int/standards/XMLSchema/ST96/Common}Del"
    buf = []
    if el.text:
        buf.append(el.text)
    for child in el:
        if child.tag != COM_DEL:
            buf.append(_text_no_del(child))
        if child.tail:
            buf.append(child.tail)
    return "".join(buf)


def fetch_claims_text(app_num: str) -> str:
    """Fetch the most recent claims document and return numbered claim text."""
    import io
    import re as _re
    import tarfile
    import xml.etree.ElementTree as ET

    clean = app_num.replace("/", "").replace(",", "").replace(" ", "").strip()
    url = f"{_BASE}/applications/{clean}/documents"
    try:
        data = _get(url)
    except Exception:
        return ""

    clm_docs = [d for d in data.get("documentBag", []) if d.get("documentCode") == "CLM"]
    if not clm_docs:
        return ""

    clm_docs.sort(key=lambda d: d.get("officialDate", ""), reverse=True)
    doc_id = clm_docs[0]["documentIdentifier"]

    dl_url = f"https://api.uspto.gov/api/v1/download/applications/{clean}/{doc_id}/xmlarchive"
    p, h = _auth()
    r = requests.get(dl_url, params=p, headers=h, timeout=30, verify=False)
    r.raise_for_status()

    tf = tarfile.open(fileobj=io.BytesIO(r.content))
    xml_str = tf.extractfile(tf.getmembers()[0]).read().decode("utf-8", errors="replace")
    xml_str = _re.sub("<[?][^?]+[?]>", "", xml_str)

    root = ET.fromstring(xml_str)
    USPAT = "urn:us:gov:doc:uspto:patent"
    PAT = "http://www.wipo.int/standards/XMLSchema/ST96/Patent"

    claims = []
    for claim_el in root.iter("{" + USPAT + "}Claim"):
        num_el = claim_el.find("{" + PAT + "}ClaimNumber")
        num = num_el.text.strip() if num_el is not None and num_el.text else "?"
        parts = []
        for text_el in claim_el.iter("{" + USPAT + "}ClaimText"):
            t = _text_no_del(text_el).strip()
            if t:
                parts.append(t)
        if parts:
            claims.append(" ".join(parts))

    newline = chr(10)
    return (newline + newline).join(claims)

@st.cache_data(ttl=3600, show_spinner=False)
def get_all_documents(app_num: str) -> list[dict]:
    """Return ALL IFW documents for an application (unfiltered)."""
    clean = app_num.replace("/", "").replace(",", "").replace(" ", "").strip()
    url = f"{_BASE}/applications/{clean}/documents"
    try:
        data = _get(url)
    except Exception:
        return []
    return data.get("documentBag", [])


def fetch_document_text(app_num: str, doc_identifier: str) -> str:
    """Generic document text extractor - works for any XML-archive document."""
    return fetch_oa_text(app_num, doc_identifier)

@st.cache_data(ttl=3600, show_spinner=False)
def get_all_documents(app_num: str) -> list[dict]:
    """Return ALL IFW documents for an application (unfiltered)."""
    clean = app_num.replace("/", "").replace(",", "").replace(" ", "").strip()
    url = f"{_BASE}/applications/{clean}/documents"
    try:
        data = _get(url)
    except Exception:
        return []
    return data.get("documentBag", [])


def fetch_document_text(app_num: str, doc_identifier: str) -> str:
    """Generic document text extractor - works for any XML-archive document."""
    return fetch_oa_text(app_num, doc_identifier)
