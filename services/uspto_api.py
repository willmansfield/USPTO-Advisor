"""
USPTO API service – uses the USPTO Open Data Portal (ODP) REST API.
Base: https://api.uspto.gov/api/v1/patent/

Auth: api_key query param  +  X-API-KEY header  (both required).
SSL:  verify=False used because this environment's cert store has a clock-skew
      issue; remove in production if not needed.

Rate-limiting: USPTO ODP enforces burst=1 (no parallel requests per API key).
  - _API_LOCK serialises every outbound call so we never have two in-flight at once.
  - On HTTP 429 we sleep _RETRY_WAIT seconds (minimum 5 s as required) then retry,
    up to _MAX_RETRIES attempts.
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

# Simple lru_cache for all functions
_cache = functools.lru_cache(maxsize=256)

_BASE      = "https://api.uspto.gov/api/v1/patent"
_PTAB_URL  = f"{_BASE}/trials/decisions/search"
_APPS_URL  = f"{_BASE}/applications/search"
_TIMEOUT   = 20

_API_LOCK    = threading.Lock()
_RETRY_WAIT  = 5
_MAX_RETRIES = 3


# ── Auth + low-level HTTP ─────────────────────────────────────────────────────

def _auth() -> tuple[dict, dict]:
    return (
        {"api_key": USPTO_API_KEY},
        {"Accept": "application/json", "X-API-KEY": USPTO_API_KEY},
    )


def _get(url: str, extra_params: dict | None = None) -> dict:
    p, h = _auth()
    if extra_params:
        p.update(extra_params)

    with _API_LOCK:
        for attempt in range(1, _MAX_RETRIES + 1):
            r = requests.get(url, params=p, headers=h, timeout=_TIMEOUT, verify=False)
            if r.status_code == 429:
                wait = _RETRY_WAIT * attempt
                logging.warning(
                    "USPTO API 429 Too Many Requests — waiting %d s before retry %d/%d",
                    wait, attempt, _MAX_RETRIES,
                )
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
    return {}


def _apps_query(q: str, limit: int = PAGE_LIMIT, offset: int = 0) -> dict:
    return _get(_APPS_URL, {"q": q, "limit": limit, "offset": offset})


def _safe_query(q: str, limit: int = PAGE_LIMIT, offset: int = 0) -> dict:
    try:
        return _apps_query(q, limit, offset)
    except requests.HTTPError as e:
        resp = e.response
        status = resp.status_code if resp is not None else None
        if status == 404:
            return {}
        if status == 413 and limit > 10:
            smaller = max(limit // 2, 10)
            logging.warning("USPTO API 413 — retrying with limit=%d", smaller)
            return _safe_query(q, smaller, offset)
        logging.warning(
            "USPTO API %s: %s",
            status or "?",
            resp.text[:300] if resp is not None else str(e),
        )
    except requests.ConnectionError:
        logging.warning("Cannot reach USPTO API.")
    except Exception as e:
        logging.warning("USPTO API error: %s", e)
    return {}


def _fetch_all(q: str, max_pages: int = MAX_PAGES) -> list[dict]:
    data0 = _safe_query(q, limit=PAGE_LIMIT, offset=0)
    if not data0:
        return []
    docs0 = data0.get("patentFileWrapperDataBag", [])
    if not docs0:
        return []

    total      = int(data0.get("count", 0))
    pages_need = min(max_pages, -(-total // PAGE_LIMIT))
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
    """
    Search USPTO applications by one or more criteria.

    Strategy: the ODP Lucene API does not reliably handle AND queries that
    mix examiner/assignee/art-unit with applicationStatusDescriptionText.
    When a status filter is combined with a primary key (examiner, assignee,
    or art unit), we fetch all results for the primary key then filter
    client-side with a case-insensitive substring match.
    This is also more forgiving of minor phrasing differences in the status
    text (e.g. "Final Action Mailed" vs "Final Rejection Mailed").
    """
    has_primary = bool(examiner or assignee or art_unit)

    # ── Case 1: primary key + optional status filter ──────────────────────────
    if has_primary:
        # Fetch all apps for the primary key
        if examiner:
            apps = search_by_examiner(examiner.strip())
        elif assignee:
            apps = search_by_assignee(assignee.strip())
        else:
            apps = search_by_art_unit(art_unit.strip())

        # Apply app_num filter client-side
        if app_num:
            clean = app_num.replace("/", "").replace(",", "").replace(" ", "")
            apps = [a for a in apps
                    if str(a.get("applicationNumberText", "")).replace(" ", "") == clean]

        # Apply status filter client-side (case-insensitive substring)
        if status:
            needle = status.strip().lower()
            apps = [
                a for a in apps
                if needle in (meta(a).get("applicationStatusDescriptionText") or "").lower()
            ]

        # Apply free_text filter client-side (against title)
        if free_text:
            needle = free_text.strip().lower()
            apps = [
                a for a in apps
                if needle in (meta(a).get("inventionTitle") or "").lower()
            ]

        return apps[:rows]

    # ── Case 2: no primary key — build ODP query from remaining fields ────────
    parts = []
    if app_num:
        parts.append(f"applicationNumberText:{app_num.replace('/', '').replace(',', '').strip()}")
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
    OA_CODES = {"CTNF", "CTFR", "MCTNF", "MCTFR"}
    clean = app_num.replace("/", "").replace(",", "").replace(" ", "").strip()
    url = f"{_BASE}/applications/{clean}/documents"
    try:
        data = _get(url)
    except Exception:
        return []
    return [doc for doc in data.get("documentBag", []) if doc.get("documentCode") in OA_CODES]


def _extract_xml_from_tar(content: bytes) -> str:
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
    import re as _re
    import xml.etree.ElementTree as ET

    clean = _re.sub(r"<\?[^?]+\?>", "", xml_str)

    try:
        root = ET.fromstring(clean)

        for ns in (
            "urn:us:gov:doc:uspto:common",
            "urn:us:gov:doc:uspto:patent",
            "",
        ):
            tag = f"{{{ns}}}P" if ns else "P"
            paragraphs = [
                "".join(el.itertext()).strip()
                for el in root.iter(tag)
            ]
            paragraphs = [p for p in paragraphs if p]
            if paragraphs:
                return "\n\n".join(paragraphs)

        text = "".join(root.itertext()).strip()
        if text:
            return text

    except ET.ParseError:
        pass

    text = _re.sub(r"<[^>]+>", " ", xml_str)
    text = _re.sub(r"\s{2,}", " ", text).strip()
    return text if text else xml_str


def fetch_oa_text(app_num: str, doc_identifier: str) -> str:
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
    return ""


def _text_no_del(el):
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
    clean = app_num.replace("/", "").replace(",", "").replace(" ", "").strip()
    url = f"{_BASE}/applications/{clean}/documents"
    try:
        data = _get(url)
    except Exception:
        return []
    return data.get("documentBag", [])


@_cache
def get_applicant_name_variants(term: str) -> dict:
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
    data = _safe_query(f'applicationMetaData.firstApplicantName:"{name}"', limit=1)
    return int(data.get("count", 0))


def _corr_name(doc: dict) -> str:
    cab = doc.get("correspondenceAddressBag") or []
    if cab:
        return cab[0].get("nameLineOneText", "")
    return ""


def _q_clean(term: str) -> str:
    import re as _re
    cleaned = _re.sub(r"[&()\[\]{}.,]", " ", term)
    return _re.sub(r"\s+", " ", cleaned).strip()


@_cache
def get_law_firm_name_variants(term: str) -> dict:
    from collections import Counter as _Counter
    clean = _q_clean(term)
    first_word = clean.split()[0]
    for q in [
        f'correspondenceAddressBag.nameLineOneText:"{clean}"',
        f"correspondenceAddressBag.nameLineOneText:{first_word}",
    ]:
        data = _safe_query(q, limit=50)
        docs = data.get("patentFileWrapperDataBag", [])
        if docs:
            counts = _Counter(
                _corr_name(d)
                for d in docs
                if _corr_name(d)
            )
            if counts:
                return dict(counts.most_common(10))
    return {}


@_cache
def law_firm_filing_count(name: str) -> int:
    clean = _q_clean(name)
    data = _safe_query(f'correspondenceAddressBag.nameLineOneText:"{clean}"', limit=1)
    return int(data.get("count", 0))


@_cache
def search_by_law_firm(firm_name: str) -> list[dict]:
    clean = _q_clean(firm_name)
    first_word = clean.split()[0]
    for q in [
        f'correspondenceAddressBag.nameLineOneText:"{clean}"',
        f"correspondenceAddressBag.nameLineOneText:{first_word}",
    ]:
        apps = _fetch_all(q)
        if apps:
            return apps
    return []
