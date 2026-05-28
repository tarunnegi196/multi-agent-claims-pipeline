# Plum Claims Engine

Multi-agent health insurance claims processing system built for the Plum AI Engineer assignment.

## Architecture

Seven LangGraph agents process each claim in sequence:

```
Intake → DocClassifier → DocVerifier (GATE) → Extraction → ConfidenceFusion → FraudScreen → PolicyEngine → DecisionComposer
```

**Design thesis:** LLMs extract structured data from messy documents; deterministic Python applies policy rules. Every decision step emits a `TraceEvent` — the decision is a fold over the trace, so the trace and decision can never disagree.

## Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI (async) + LangGraph |
| LLM | Gemini 2.5 Flash (vision extraction) |
| Decision | Deterministic Python engine (reads `data/policy_terms.json`) |
| Persistence | SQLite + aiosqlite |
| Frontend | React + Vite + React Flow (live trace viewer) |

## Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # add GEMINI_API_KEY
uvicorn app.main:app --reload
```

## Tests

```bash
cd backend
pytest --cov=app tests/
```

## Eval

```bash
cd backend
python -m app.eval.run_eval
```
