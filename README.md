# PatentAdvisor POC

A Python/Streamlit proof-of-concept that reproduces the core features of [LexisNexis PatentAdvisor®](https://www.lexisnexisip.com/solutions/patent-prosecution/patentadvisor/) using only free, live calls to the USPTO Open Data Portal API, augmented with an optional OpenAI layer for AI-powered analysis.

The app also exposes a **FastAPI REST backend** and an **MCP server** — give the MCP endpoint to any AI assistant (Claude Desktop, Cursor, etc.) for live patent research during conversations.

---

## Running the app

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

**Demo credentials**

| Username | Password |
|----------|----------|
| admin    | admin123 |
| demo     | demo123  |

### Running the API + MCP server

```bash
# Terminal 2 (optional — needed for REST API and MCP)
uvicorn api.main:app --reload --port 8000
```

- REST API docs: `http://localhost:8000/docs`
- MCP server (SSE): `http://localhost:8000/mcp/sse`

---

## Configuration

Copy `.env.example` to `.env`:

```
OPENAI_API_KEY=sk-...          # Optional – enables all AI features
USPTO_API_KEY=your_key_here    # Required – get free key at developer.uspto.gov
```

The Streamlit app works without `OPENAI_API_KEY` — all data pages remain fully functional. AI analysis will show a warning instead.

---

## Pages (5 focused pages)

| Page | What it does |
|------|-------------|
| **⚖️ Prosecution Hub** | Enter any application number → full prosecution history, inline examiner difficulty profile, AI-narrated prosecution summary, automatic OA analysis and response strategy. |
| **🔬 Examiner Intel** | Two tabs: *Examiner* (difficulty score, AI prosecution brief, stats, filing trends, sample applications) and *Art Unit* (overall score + ranked examiner roster). |
| **💼 Portfolio** | Company or assignee prosecution health dashboard: outcomes, filing trend, examiner concentration, art unit breakdown, AI executive summary. |
| **⚖️ PTAB & Pre-filing** | Two tabs: *PTAB Research* (search IPR/PGR/CBM decisions, click for detail + AI analysis) and *Pre-filing Claim Check* (§102/103/112 risk analysis with live art unit context). |
| **💬 AI Patent Assistant** | Conversational patent AI with automatic live USPTO tool-calling. Suggested questions for quick start; full conversation history. |

### Cross-page navigation

- Click any application row in Examiner Intel or Portfolio → opens it directly in Prosecution Hub
- Click any examiner badge in Prosecution Hub → opens their profile in Examiner Intel
- Click any examiner in the Art Unit roster → loads their profile in the Examiner tab

---

## REST API

Start with `uvicorn api.main:app --port 8000`. Interactive docs at `/docs`.

| Endpoint | Description |
|----------|-------------|
| `GET /api/examiner/{name}` | Examiner difficulty profile + score |
| `GET /api/art-unit/{code}` | Art unit overview + ranked examiner roster |
| `GET /api/application/{num}` | Application metadata |
| `GET /api/application/{num}/transactions` | Prosecution event history |
| `GET /api/application/{num}/documents` | IFW document list |
| `GET /api/application/{num}/claims` | Current claims text |
| `POST /api/search` | Multi-field application search |
| `GET /api/portfolio/{assignee}` | Company portfolio stats |
| `POST /api/ptab` | PTAB decision search |
| `POST /api/ai/examiner-brief` | AI examiner narrative |
| `POST /api/ai/oa-analysis` | AI office action explanation |
| `POST /api/ai/response-strategy` | AI OA response strategy |
| `POST /api/ai/claim-check` | Pre-filing claim risk analysis |
| `POST /api/ai/portfolio-report` | AI portfolio executive summary |
| `POST /api/ai/chat` | Multi-turn patent AI chat |

---

## MCP Server

The MCP server runs at `/mcp/sse` (SSE transport) when the API is running, or as a standalone stdio server for Claude Desktop.

**Claude Desktop config (stdio — local)**

```json
{
  "mcpServers": {
    "patent-advisor": {
      "command": "python",
      "args": ["/absolute/path/to/PatentAdvisor/api/mcp_server.py"],
      "env": {
        "USPTO_API_KEY": "your-key",
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

**HTTP / SSE transport**

```json
{
  "mcpServers": {
    "patent-advisor": {
      "url": "http://localhost:8000/mcp/sse"
    }
  }
}
```

### MCP Tools

| Tool | Description |
|------|-------------|
| `search_examiner` | Examiner difficulty profile |
| `search_art_unit` | Art unit stats + examiner roster |
| `get_application` | Application details + prosecution history |
| `search_applications` | Multi-field application search |
| `get_company_portfolio` | Company portfolio stats |
| `search_ptab_decisions` | PTAB trial decisions |
| `analyze_office_action` | AI OA analysis (requires OpenAI) |
| `check_patent_claims` | AI pre-filing claim check (requires OpenAI) |

---

## Architecture

```
app.py                      Login + home dashboard (Streamlit)
config.py                   API keys, scoring thresholds, constants
requirements.txt

api/
  main.py                   FastAPI REST API + MCP server mount
  mcp_server.py             FastMCP tools (also runnable standalone)

services/
  uspto_api.py              USPTO ODP API calls (1-hr in-memory cache)
  scoring.py                Composite Green/Yellow/Red examiner scorer
  openai_service.py         GPT-4o-mini functions (no Streamlit dependency)

pages/
  1_Prosecution_Hub.py      App lookup + AI-powered prosecution workspace
  2_Examiner_Intel.py       Examiner profile + art unit explorer
  3_Portfolio.py            Company prosecution dashboard
  4_PTAB_Claims.py          PTAB research + pre-filing claim check
  5_AI_Chat.py              Conversational AI assistant

utils/
  auth.py                   Session-state auth guard + logout
```

---

## Examiner Scoring

Composite 0–100 score (analogous to PatentAdvisor ETA™, computed from open data):

| Component | Weight | Direction |
|-----------|--------|-----------|
| Allowance rate | 40% | Higher = easier |
| Avg office actions per disposed app | 30% | Lower = easier |
| Avg pendency (months) | 20% | Lower = easier |
| RCE rate | 10% | Lower = easier |

**Bands:** 🟢 Easy (≥60) · 🟡 Moderate (35–59) · 🔴 Difficult (<35)

---

## Data source

All data fetched live from the **USPTO Open Data Portal**:

- `api.uspto.gov/api/v1/patent/applications/search` — applications, prosecution history
- `api.uspto.gov/api/v1/patent/trials/decisions/search` — PTAB decisions

Results cached in-process for 1 hour.

---

## Notes

- POC only — no production auth, rate limiting, or persistent storage
- `verify=False` on all requests due to cert store clock-skew in dev environment; remove in production
- `USPTO_API_KEY` is in `.env` (gitignored) — never committed
