"""
USPTO API service – uses the USPTO Open Data Portal (ODP) REST API.
Base: https://api.uspto.gov/api/v1/patent/

Auth: api_key query param  +  X-API-KEY header  (both required).
SSL:  verify=False used because this environment's cert store has a clock-skew
      issue; remove in production if not needed.

Rate-limiting: USPTO ODP enforces burst=1 (no parallel requests per API key).
  - _API_LOCK serialises every outbound call so we never have two in-flight at once.
  - On HTTP 429 we sleep _RETRY_WAIT seconds (minimum 5 s as required) then retry,
    up to _MAX_RETRIES attempts. The lock is held during the sleep so no other
    thread fires against the same key while the server is overloaded.

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

import functools
import logging
import threading
import time
import urllib3
import requests

from config import (
    USPTO_API_KEY, PAGE_LIMIT, MAX_PAGES,
    OFFICE_ACTION_CODES, RCE_CODES,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _cache(fn):
    """Use st.cache_data when running inside Streamlit, else plain lru_cache."""
    try:
        import streamlit as st
        return st.cache_data(ttl=3600, show_spinner=False)(fn)
    except Exception:
        return functools.lru_cache(maxsize=256)(fn)

_BASE      = "https://api.uspto.gov/api/v1/patent"
_PTAB_URL  = f"{_BASE}/trials/decisions/search"
_APPS_URL  = f"{_BASE}/applications/search"
_TIMEOUT   = 20

# Enforce USPTO ODP burst=1: only one request in-flight per API key at a time.
_API_LOCK    = threading.Lock()
_RETRY_WAIT  = 5   # minimum seconds to wait after a 429 (USPTO recommendation)
_MAX_RETRIES = 3   # retry attempts on 429 before giving up


# ── Auth + low-level HTTP ─────────────────────────────────────────────────────

def _auth() -> tuple[dict, dict]:
    """Return (params_dict, headers_dict) with credentials."""
    return (
        {"api_key": USPTO_API_KEY},
        {"Accept": "application/json", "X-API-KEY": USPTO_API_KEY},
    )


def _get(url: str, extra_params: dict | None = None) -> dict:
    """
    Single serialised GET with 429 retry.

    _API_LOCK ensures only one request is in-flight at a time (burst=1).
    On 429 we sleep inside the lock — this blocks other threads from firing
    while the API is already rejecting requests, preventing a retry storm.
    Wait time backs off: 5 s, 10 s, 15 s across successive attempts.
    """
    p, h = _auth()
    if extra_params:
        p.update(extra_params)

    with _API_LOCK:
        for attempt in range(1, _MAX_RETRIES + 1):
            r = requests.get(url, params=p, headers=h, timeout=_TIMEOUT, verify=False)
            if r.status_code == 429:
                wait = _RETRY_WAIT * attempt      # 5 s → 10 s → 15 s
                logging.warning(
                    "USPTO API 429 Too Many Requests — waiting %d s before retry %d/%d",
                    wait, attempt, _MAX_RETRIES,
                )
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        # All retries exhausted — surface the 429 as an HTTPError
        r.raise_for_status()
    return {}  # unreachable; satisfies type-checker


def _apps_query(q: str, limit: int = PAGE_LIMIT, offset: int = 0) -> dict:
    return _get(_APPS_URL, {"q": q, "limit": limit, "offset": offset})


def _safe_query(q: str, limit: int = PAGE_LIMIT, offset: int = 0) -> dict:
    try:
        return _apps_query(q, limit, offset)
    except requests.HTTPError as e:
        resp = e.response
        if resp is not None and resp.status_code == 404:
            return {}  # No results — not a real error
        logging.warning(
            "USPTO API %s: %s",
            resp.status_code if resp is not None else "?",
            resp.text[:300] if resp is not None else str(e),
        )
    except requests.ConnectionError:
        logging.warning("Cannot reach USPTO API.")
    except Exception as e:
        logging.warning("USPTO API error: %s", e)
    return {}


def _fetch_all(q: str, max_pages: int = MAX_PAGES) -> list[dict]:
    """
    Fetch up to max_pages x PAGE_LIMIT records from the ODP sequentially.

    Pages are fetched one at a time to respect the USPTO burst limit of 1
    concurrent request per API key.  Each _safe_query call acquires _API_LOCK
    for the duration of its HTTP round-trip.
    """
    # Page 0 – also reveals total count
    data0 = _safe_query(q, limit=PAGE_LIMIT, offset=0)
    if not data0:
        return []
    docs0 = data0.get("patentFileWrapperDataBag", [])
    if not docs0:
        return []

    total      = int(data0.get("count", 0))
    pages_need = min(max_pages, -(-total // PAGE_LIMIT))  # ceiling division
    offsets    = [i * PAGE_LIMIT for i in range(1, pages_need)]

    all_docs = list(docs0)
    for off in offsets:
        data = _safe_query(q, PAGE_LIMIT, off)
        if data:
            all_docs.extend(data.get("patentFileWrapperDataBag", []))

    return all_docs


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

@_cache
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


@_cache
def search_by_art_unit(art_unit: str) -> list[dict]:
    return _fetch_all(f"applicationMetaData.groupArtUnitNumber:{art_unit.strip()}")


@_cache
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


@_cache
def get_application(app_num: str) -> dict:
    clean = app_num.replace("/", "").replace(",", "").replace(" ", "").strip()
    data  = _safe_query(f"applicationNumberText:{clean}", limit=1)
    docs  = data.get("patentFileWrapperDataBag", [])
    return docs[0] if docs else {}


@_cache
def get_transactions(app_num: str) -> list[dict]:
    app = get_application(app_num)
    return app.get("eventDataBag", [])


@_cache
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

@_cache
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
        with _API_LOCK:
            for attempt in range(1, _MAX_RETRIES + 1):
                r = requests.get(_PTAB_URL, params=p, headers=h,
                                 timeout=_TIMEOUT, verify=False)
                if r.status_code == 429:
                    wait = _RETRY_WAIT * attempt
                    logging.warning(
                        "USPTO PTAB API 429 — waiting %d s before retry %d/%d",
                        wait, attempt, _MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                if r.status_code == 200:
                    return r.json().get("patentTrialDocumentDataBag", [])
                break
    except Exception as e:
        logging.warning("PTAB API error: %s", e)
    return []


@_cache
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


def _extract_xml_from_tar(content: bytes) -> str:
    """Return the XML string from the first readable file in a tar archive."""
    import io
    import tarfile

    tf = tarfile.open(fileobj=io.BytesIO(content))
    for member in tf.getmembers():
        if not member.isfile():
            continue
        f = tf.extractfile(member)
        if f is None:
            continue
        raw = f.read().decode("utf-8", errors="replace")
        if raw.strip():
            return raw
    raise ValueError("Archive contains no readable files")


def _xml_to_text(xml_str: str) -> str:
    """
    Extract readable text from a USPTO XML string.

    Strategy 1 — known paragraph namespaces (structured, clean output).
    Strategy 2 — itertext() across the entire element tree.
    Strategy 3 — regex tag-strip (may leave some markup artifacts, but always
                  returns something rather than silently failing).
    """
    import re as _re
    import xml.etree.ElementTree as ET

    # Remove processing instructions that confuse ElementTree
    clean = _re.sub(r"<\?[^?]+\?>", "", xml_str)

    try:
        root = ET.fromstring(clean)

        # Try known paragraph-level namespaces used by USPTO documents
        for ns in (
            "urn:us:gov:doc:uspto:common",
            "urn:us:gov:doc:uspto:patent",
            "",  # no namespace
        ):
            tag = f"{{{ns}}}P" if ns else "P"
            paragraphs = [
                "".join(el.itertext()).strip()
                for el in root.iter(tag)
            ]
            paragraphs = [p for p in paragraphs if p]
            if paragraphs:
                return "\n\n".join(paragraphs)

        # No known paragraph elements — dump all text from the tree
        text = "".join(root.itertext()).strip()
        if text:
            return text

    except ET.ParseError:
        pass

    # Last resort: strip XML tags with regex.
    text = _re.sub(r"<[^>]+>", " ", xml_str)
    text = _re.sub(r"\s{2,}", " ", text).strip()
    return text if text else xml_str


def fetch_oa_text(app_num: str, doc_identifier: str) -> str:
    """Download the XML archive for an OA document and return extracted plain text."""
    clean = app_num.replace("/", "").replace(",", "").replace(" ", "").strip()
    url = f"https://api.uspto.gov/api/v1/download/applications/{clean}/{doc_identifier}/xmlarchive"
    p, h = _auth()
    with _API_LOCK:
        for attempt in range(1, _MAX_RETRIES + 1):
            r = requests.get(url, params=p, headers=h, timeout=30, verify=False)
            if r.status_code == 429:
                wait = _RETRY_WAIT * attempt
                logging.warning("USPTO download 429 — waiting %d s (attempt %d/%d)", wait, attempt, _MAX_RETRIES)
                time.sleep(wait)
                continue
            r.raise_for_status()
            xml_str = _extract_xml_from_tar(r.content)
            return _xml_to_text(xml_str)
        r.raise_for_status()
    return ""  # unreachable


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
    import re as _re
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
    with _API_LOCK:
        for attempt in range(1, _MAX_RETRIES + 1):
            r = requests.get(dl_url, params=p, headers=h, timeout=30, verify=False)
            if r.status_code == 429:
                wait = _RETRY_WAIT * attempt
                logging.warning("USPTO download 429 — waiting %d s (attempt %d/%d)", wait, attempt, _MAX_RETRIES)
                time.sleep(wait)
                continue
            r.raise_for_status()
            break
        else:
            r.raise_for_status()

    xml_str = _extract_xml_from_tar(r.content)
    xml_str = _re.sub(r"<\?[^?]+\?>", "", xml_str)

    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return _xml_to_text(xml_str)

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
            claims.append(f"{num}. {' '.join(parts)}")

    if claims:
        return "\n\n".join(claims)

    return _xml_to_text(xml_str)


@_cache
def get_all_documents(app_num: str) -> list[dict]:
    """Return ALL IFW documents for an application (unfiltered)."""
    clean = app_num.replace("/", "").replace(",", "").replace(" ", "").strip()
    url = f"{_BASE}/applications/{clean}/documents"
    try:
        data = _get(url)
    except Exception:
        return []
    return data.get("documentBag", [])


@_cache
def get_applicant_name_variants(term: str) -> dict:
    """
    Fetch first 50 ODP results for *term* and return a dict of
    {firstApplicantName: count_in_sample} for every unique name found.
    Tries an exact-phrase query first, falls back to first-word.
    """
    from collections import Counter as _Counter
    first_word = term.split()[0]
    for q in [
        f'applicationMetaData.firstApplicantName:"{term}"',
        f"applicationMetaData.firstApplicantName:{first_word}",
    ]:
        data = _safe_query(q, limit=50)
        docs = data.get("patentFileWrapperDataBag", [])
        if docs:
            counts = _Counter(
                meta(d).get("firstApplicantName", "")
                for d in docs
                if meta(d).get("firstApplicantName")
            )
            return dict(counts.most_common(10))
    return {}


@_cache
def odp_filing_count(name: str) -> int:
    """Return the total ODP application count for an exact firstApplicantName match."""
    data = _safe_query(f'applicationMetaData.firstApplicantName:"{name}"', limit=1)
    return int(data.get("count", 0))


@_cache
def fetch_document_text(app_num: str, doc_identifier: str) -> str:
    """Generic document text extractor - works for any XML-archive document."""
    return fetch_oa_text(app_num, doc_identifier)


@_cache
def fetch_pdf(app_num: str, doc_identifier: str) -> bytes:
    """Download the PDF for a document and return raw bytes."""
    clean = app_num.replace("/", "").replace(",", "").replace(" ", "").strip()
    url = f"https://api.uspto.gov/api/v1/download/applications/{clean}/{doc_identifier}/pdf"
    p, h = _auth()
    with _API_LOCK:
        for attempt in range(1, _MAX_RETRIES + 1):
            r = requests.get(url, params=p, headers=h, timeout=30, verify=False)
            if r.status_code == 429:
                wait = _RETRY_WAIT * attempt
                logging.warning("USPTO download 429 — waiting %d s (attempt %d/%d)", wait, attempt, _MAX_RETRIES)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.content
        r.raise_for_status()
    return b""  # unreachable


@_cache
def get_law_firm_name_variants(term: str) -> dict:
    """
    Fetch first 50 ODP results for *term* searched against corresOrganizationName
    and return a dict of {name: count_in_sample} for unique firm names found.
    """
    from collections import Counter as _Counter
    first_word = term.split()[0]
    for q in [
        f'applicationMetaData.corresOrganizationName:"{term}"',
        f"applicationMetaData.corresOrganizationName:{first_word}",
    ]:
        data = _safe_query(q, limit=50)
        docs = data.get("patentFileWrapperDataBag", [])
        if docs:
            counts = _Counter(
                meta(d).get("corresOrganizationName", "")
                for d in docs
                if meta(d).get("corresOrganizationName")
            )
            if counts:
                return dict(counts.most_common(10))
    return {}


@_cache
def law_firm_filing_count(name: str) -> int:
    """Return total ODP application count for an exact law firm name match."""
    data = _safe_query(f'applicationMetaData.corresOrganizationName:"{name}"', limit=1)
    return int(data.get("count", 0))


@_cache
def search_by_law_firm(firm_name: str) -> list[dict]:
    """Fetch applications where the correspondent is the given law firm."""
    for q in [
        f'applicationMetaData.corresOrganizationName:"{firm_name}"',
        f"applicationMetaData.corresOrganizationName:{firm_name.split()[0]}",
    ]:
        apps = _fetch_all(q)
        if apps:
            return apps
    return []
