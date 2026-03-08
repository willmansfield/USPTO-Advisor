# PatentAdvisor POC

A Python/Streamlit proof-of-concept that reproduces the core features of [LexisNexis PatentAdvisor®](https://www.lexisnexisip.com/solutions/patent-prosecution/patentadvisor/) using only free, live calls to the USPTO Open Data Portal API, augmented with an optional OpenAI layer for AI-powered analysis.

---

## Running the app

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open `http://localhost:8501` in your browser.

**Demo credentials**

| Username | Password |
|----------|----------|
| admin    | admin123 |
| demo     | demo123  |

---

## Configuration

Copy `.env.example` to `.env` and fill in your keys:

```
OPENAI_API_KEY=sk-...          # Required for all AI pages
USPTO_API_KEY=your_key_here    # Required for USPTO data
```

The app works without `OPENAI_API_KEY` — all PA-mode analytics pages remain fully functional. AI pages will show a configuration warning instead.

---

## Pages

### PA Analytics Mode

| Page | What it does |
|------|-------------|
| **🔍 Examiner Search** | Enter an examiner's last name (e.g. `SMITH`) to see their difficulty score (Green/Yellow/Red), allowance rate, average office action count, average pendency, RCE rate, outcome donut chart, and filing trend. Optional AI narrative brief. |
| **📋 Application Search** | Multi-field search by application number, assignee, examiner, art unit, or status. Click any result to load its full prosecution timeline. |
| **💼 Portfolio View** | Enter a company name to get a portfolio-level dashboard: outcome distribution, filing trend, top examiners, art unit breakdown. Optional AI report. |
| **🏛️ Art Unit Explorer** | Enter a 4-digit art unit to see aggregate stats and an examiner roster with individual difficulty scores and a score-distribution pie. |
| **⚖️ PTAB Decisions** | Search PTAB trial decisions (IPR/PGR/CBM) by patent owner or petitioner. Optional AI analysis of any pasted decision text. |

### AI Assistant Mode

| Page | What it does |
|------|-------------|
| **💬 AI Chat** | Conversational patent assistant. Toggle "Fetch live USPTO data" to automatically pull real examiner or art unit stats to ground the AI's answers. |
| **📄 OA Analyzer** | Paste a USPTO Office Action → AI produces a plain-English breakdown of each rejection and a recommended response strategy. |
| **✅ Claim Checker** | Paste patent claims before filing → AI flags §102 novelty risks, §103 obviousness risks, and §112 indefiniteness issues. Optionally enter the target art unit for examiner context. |

---

## Architecture

```
app.py                  Login page + home dashboard
config.py               API keys, scoring thresholds, constants
requirements.txt

services/
  uspto_api.py          All USPTO ODP API calls (cached 1 hr per session)
  scoring.py            Composite Green/Yellow/Red examiner scorer
  openai_service.py     All GPT-4o functions
  patentsview_api.py    (stub – kept for future use)

utils/
  auth.py               Session-state auth guard + logout

pages/
  1_Examiner_Search.py
  2_Application_Search.py
  3_Portfolio_View.py
  4_Art_Unit_Explorer.py
  5_PTAB_Decisions.py
  6_AI_Chat.py
  7_OA_Analyzer.py
  8_Claim_Checker.py
```

---

## Data source

All patent data is fetched live (no local database) from the **USPTO Open Data Portal**:

- **`api.uspto.gov/api/v1/patent/applications/search`** — patent applications, examiner data, prosecution history, assignee data
- **`api.uspto.gov/api/v1/patent/trials/decisions/search`** — PTAB trial decisions

Results are cached in Streamlit session state for 1 hour to avoid redundant API calls within a session.

Each examiner/art-unit search fetches up to **200 most-recent applications** (10 pages × 20 records). Stats are computed from this sample and labelled accordingly.

---

## Examiner Scoring

The difficulty score (0–100) is a weighted composite — analogous to PatentAdvisor ETA™ but computed from open data:

| Component | Weight | Direction |
|-----------|--------|-----------|
| Allowance rate | 40 % | Higher = easier |
| Avg office actions per disposed app | 30 % | Lower = easier |
| Avg pendency (months) | 20 % | Lower = easier |
| RCE rate | 10 % | Lower = easier |

**Bands:**
- 🟢 **Easy (Green)** — score ≥ 60
- 🟡 **Moderate (Yellow)** — score 35–59
- 🔴 **Difficult (Red)** — score < 35

---

## What this reproduces vs. PatentAdvisor

| Feature | Reproduced? | Notes |
|---------|-------------|-------|
| Examiner difficulty score | ~70% | Different algorithm; correlates well |
| Examiner prosecution stats | ✅ Yes | Allowance rate, OAs, pendency, RCE rate |
| Art unit analytics | ✅ Yes | Full roster with per-examiner scores |
| Application / file wrapper search | ✅ Yes | Multi-field search + prosecution timeline |
| Portfolio analysis | ✅ Yes | Assignee dashboard with charts |
| PTAB decisions search | ✅ Yes | Full IPR/PGR/CBM search |
| Examiner ETA™ exact score | ❌ No | Proprietary algorithm |
| Efficiency Score™ | ❌ No | Proprietary metric |
| 20-year pre-aggregated rejection data | ❌ No | On-the-fly from sample of 200 apps |
| Full-text OCR file wrapper search | ❌ No | ODP provides metadata, not OCR |
| PTAB decisions tagged to 227 issues | Partial | AI can tag on demand |
| AI examiner brief | ✅ Bonus | Not in PatentAdvisor |
| Office action explainer + strategy | ✅ Bonus | Not in PatentAdvisor |
| Pre-filing claim checker | ✅ Bonus | Not in PatentAdvisor |

---

## Notes

- This is a **proof of concept only** — no authentication security, no rate-limit handling, no persistent storage.
- USPTO API key is loaded from `.env` (gitignored). Never commit `.env`.
- The USPTO ODP requires both `api_key` as a query param **and** `X-API-KEY` as a request header.
- Lucene dot-notation is required for nested field queries: `applicationMetaData.examinerNameText:SMITH`.
- `verify=False` is set on all requests due to an SSL certificate clock-skew in the development environment. Remove in production if not needed.
