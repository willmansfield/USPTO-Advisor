"""
PatentsView API service – granted patents with examiner fields.
Endpoint: https://api.patentsview.org/patents/query  (free, no key required)

Used primarily to supplement PEDS data for granted-patent metrics.
"""

import requests
import streamlit as st
from config import PATENTSVIEW_API_URL

_TIMEOUT = 30
_HEADERS = {"Content-Type": "application/json"}

FIELDS = [
    "patent_id",
    "patent_number",
    "patent_title",
    "patent_date",
    "patent_processing_time",
    "examiner_id",
    "examiner_last_name",
    "examiner_first_name",
    "examiner_art_unit",
    "examiner_role",
    "assignee_organization",
    "inventor_last_name",
]


def _pv_query(q: dict, fields: list | None = None, page: int = 1, per_page: int = 100) -> dict:
    body = {
        "q": q,
        "f": fields or FIELDS,
        "o": {"page": page, "per_page": per_page},
        "s": [{"patent_date": "desc"}],
    }
    resp = requests.post(PATENTSVIEW_API_URL, json=body, headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


@st.cache_data(ttl=3600, show_spinner=False)
def search_by_examiner(last_name: str, first_name: str = "") -> list[dict]:
    """Return granted patents for a given examiner from PatentsView."""
    try:
        q: dict
        if first_name:
            q = {"_and": [
                {"examiner_last_name": last_name},
                {"examiner_first_name": first_name},
            ]}
        else:
            q = {"examiner_last_name": last_name}
        data = _pv_query(q, per_page=100)
        return data.get("patents") or []
    except requests.HTTPError as e:
        st.warning(f"PatentsView API error: {e}")
        return []
    except Exception as e:
        st.warning(f"PatentsView unavailable: {e}")
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def search_by_assignee(assignee: str) -> list[dict]:
    try:
        q = {"_text_any": {"assignee_organization": assignee}}
        data = _pv_query(q, per_page=100)
        return data.get("patents") or []
    except Exception as e:
        st.warning(f"PatentsView unavailable: {e}")
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def get_assignee_org_variants(term: str) -> dict:
    """
    Search PatentsView using the first word of *term*, return
    {assignee_organization: grant_count} for the unique org names found.
    Used to enrich the disambiguation table with granted-patent counts.
    """
    from collections import Counter
    try:
        first_word = term.split()[0]
        data = _pv_query(
            {"_text_any": {"assignee_organization": first_word}},
            fields=["assignee_organization"],
            per_page=100,
        )
        patents = data.get("patents") or []
        counts = Counter(
            p.get("assignee_organization", "")
            for p in patents
            if p.get("assignee_organization")
        )
        return dict(counts.most_common(15))
    except Exception:
        return {}


@st.cache_data(ttl=3600, show_spinner=False)
def search_by_art_unit(art_unit: str) -> list[dict]:
    try:
        q = {"examiner_art_unit": art_unit}
        data = _pv_query(q, per_page=100)
        return data.get("patents") or []
    except Exception as e:
        st.warning(f"PatentsView unavailable: {e}")
        return []
