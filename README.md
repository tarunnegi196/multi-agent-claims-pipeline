# Plum Claims Engine

Multi-agent health insurance claims processing system built for the Plum AI Engineer assignment.

## Architecture

Eight pipeline steps process each claim. Four are LLM-powered (Gemini); four are deterministic:

```
Intake → Classifier Agent → Verifier (GATE) → Extraction Agent
       → Consistency Agent → Fraud Screen → Decision → Report Agent
```

| # | Step | Type | Role |
|---|---|---|---|
| 1 | **Intake** | deterministic | Member roster check · docs present · min-amount |
| 2 | **Classifier Agent** | Gemini | Doc type + quality per uploaded file |
| 3 | **Verifier** | deterministic | Required doc types present and readable — halts with precise message if not |
| 4 | **Extraction Agent** | Gemini Vision | Structured fields + bounding boxes per doc · derives missing date/amount from bills |
| 5 | **Consistency Agent** | Gemini | Semantic cross-doc check: patient / doctor / hospital / date match |
| 6 | **Fraud Screen** | deterministic | Same-day · monthly · high-value · alteration · cross-doc consistency flags |
| 7 | **Decision** | deterministic | Policy engine: waiting periods, exclusions, network discount, copay, sub-limits |
| 8 | **Report Agent** | Gemini | Narrative · confidence reasoning · next-best-actions |

**Design thesis:** LLMs extract, classify, and narrate. Deterministic Python applies every policy rule. Every decision is a fold over the trace — trace and decision can never disagree.

## Stack

| Layer | Choice |
|---|---|
| Orchestration | LangGraph (StateGraph, 8 nodes, conditional halt routing) |
| Backend | FastAPI (async) + aiosqlite |
| LLMs | Gemini 2.5 Flash — classification, vision extraction, consistency, report |
| Policy engine | Deterministic Python (reads `policy_terms.json`) |
| Observability | TraceEvent bus → SSE live stream → React Flow replay |
| Frontend | React + Vite + React Flow |

## Setup

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # add GEMINI_API_KEY
uvicorn app.main:app --reload --port 8000
```

Frontend is bundled into the FastAPI static mount. For local dev with hot-reload:

```bash
cd frontend
npm install
npm run dev   # runs on :5173 with VITE_API_BASE=http://localhost:8000
```

## Tests

```bash
cd backend
pytest tests/ -v
```

44 tests across policy engine, database, graph pipeline, and provider mocks.

## Key design decisions

- **3-input form** — Employee ID + Claim Type + Documents. Treatment date and claimed amount are derived from extracted bill totals and dates when the user doesn't provide them.
- **Bboxes during extraction** — `extract()` and `extract_with_bboxes()` run in parallel via `asyncio.gather`. Regions are cached to disk so the UI never triggers a second Gemini call when you click "View Regions".
- **Consistency before Fraud** — cross-document semantic mismatches surface as `consistency_flags` in Fraud Screen's score, not as a hard halt (patient-name hard mismatch is still halted in the Extractor).
- **LLM for richness, not correctness** — every Gemini call has a deterministic/templated fallback. The pipeline never blocks on a Gemini failure.
- **Every halt reaches the Report Agent** — halted pipelines still get a Gemini-synthesised narrative and next-best-actions so the member always knows what to do.
