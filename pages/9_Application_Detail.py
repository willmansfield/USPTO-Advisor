"""
Page 9 - Application Detail
Full prosecution history and file wrapper viewer for a single application.
Navigated to from Examiner Search or Application Search via st.session_state.detail_app_num.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from utils.auth import require_auth, sidebar_user
from services import uspto_api

require_auth()
sidebar_user()

st.title("Application Detail")

app_num = st.session_state.get("detail_app_num", "")
if not app_num:
    st.warning("No application selected. Use Examiner Search or Application Search to open an application.")
    st.stop()

st.caption("Application: " + app_num)

with st.spinner("Loading application data..."):
    app   = uspto_api.get_application(app_num)
    txns  = uspto_api.get_transactions(app_num)
    docs  = uspto_api.get_all_documents(app_num)

if not app:
    st.error("Application " + app_num + " not found.")
    st.stop()

m = uspto_api.meta(app)

# -- Header
st.subheader(m.get("inventionTitle", "Unknown Title"))

c1, c2, c3, c4 = st.columns(4)
c1.metric("Status",      m.get("applicationStatusDescriptionText", "N/A"))
c2.metric("Filing Date", m.get("filingDate", "N/A")[:10] if m.get("filingDate") else "N/A")
c3.metric("Patent #",    uspto_api.get_patent_number(app) or "-")
c4.metric("Art Unit",    m.get("groupArtUnitNumber", "N/A"))

st.markdown("**Examiner:** " + m.get("examinerNameText", "N/A") + "  |  **Assignee:** " + (uspto_api.get_assignee(app) or "N/A"))

# -- Prosecution timeline
if txns:
    st.markdown("---")
    st.subheader("Prosecution Timeline")
    tx_rows = [
        {
            "Date":  t.get("eventDate", ""),
            "Code":  t.get("eventCode", ""),
            "Event": t.get("eventDescriptionText", ""),
        }
        for t in sorted(txns, key=lambda x: x.get("eventDate", ""))
    ]
    st.dataframe(pd.DataFrame(tx_rows), use_container_width=True)
else:
    st.info("No prosecution history available.")

# -- File wrapper documents
st.markdown("---")
st.subheader("File Wrapper Documents")

if not docs:
    st.info("No documents found for this application.")
else:
    sorted_docs = sorted(docs, key=lambda d: d.get("officialDate", ""), reverse=True)
    for doc in sorted_docs:
        code   = doc.get("documentCode", "")
        desc   = doc.get("documentCodeDescriptionText", code)
        date   = (doc.get("officialDate") or "")[:10]
        doc_id = doc.get("documentIdentifier", "")
        dl_bag = doc.get("downloadOptionBag", [])
        formats = [d.get("mimeTypeIdentifier", "") for d in dl_bag]

        col_meta, col_xml, col_pdf = st.columns([5, 1, 1])
        col_meta.markdown(
            "**" + date + "** &nbsp; `" + code + "` &nbsp; " + desc
        )

        if "XML" in formats and doc_id:
            if col_xml.button("Text", key="xml_" + doc_id):
                with st.spinner("Fetching document text..."):
                    text = uspto_api.fetch_document_text(app_num, doc_id)
                with st.expander(code + " " + date, expanded=True):
                    st.text_area("", text, height=300, key="ta_" + doc_id)

        pdf_entry = next((d for d in dl_bag if d.get("mimeTypeIdentifier") == "PDF"), None)
        if pdf_entry and pdf_entry.get("downloadUrl"):
            clean = app_num.replace("/", "").replace(",", "").replace(" ", "")
            pdf_url = pdf_entry["downloadUrl"]
            col_pdf.link_button("PDF", pdf_url)

st.caption("Data: USPTO Open Data Portal (api.uspto.gov).")
