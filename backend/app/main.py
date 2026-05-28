"""
FastAPI application — the HTTP boundary for the claims pipeline.

Endpoints:
  POST /api/claims          Submit a claim; runs the full LangGraph pipeline.
  GET  /api/claims          List recent claims (summary).
  GET  /api/claims/{id}     Retrieve a stored claim with full trace.
  GET  /api/claims/{id}/trace  SSE stream of live trace events (TODO: next commit).
"""
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.database import init_db
from app.db.repositories import ClaimRepository, TraceRepository
from app.graph import claims_graph
from app.models.claim import ClaimSubmission
from app.models.decision import Decision, DecisionType, FinalOutput, RejectionReason
from app.models.graph_state import GraphState


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(settings.db_path)
    yield


app = FastAPI(title="Plum Claims Engine", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_halt_decision(claim: ClaimSubmission, halt_message: str, intake_ok: bool | None) -> Decision:
    """Build a Decision when the pipeline halted before the composer ran."""
    # Intake failures are hard rejections; document issues go to MANUAL_REVIEW
    if intake_ok is False:
        # Determine reason from message content
        if "not registered" in halt_message or "not found" in halt_message:
            reason = RejectionReason.MEMBER_NOT_FOUND
        elif "minimum" in halt_message:
            reason = RejectionReason.BELOW_MINIMUM_AMOUNT
        else:
            reason = RejectionReason.DOCUMENT_MISMATCH
        return Decision(
            decision_type=DecisionType.REJECTED,
            claimed_amount=claim.claimed_amount,
            rejection_reasons=[reason],
            confidence=1.0,
            explanation=halt_message,
        )

    # Document verification / extraction halt → ask member to fix and resubmit
    reason = (
        RejectionReason.UNREADABLE_DOCUMENT
        if "re-upload" in halt_message or "quality" in halt_message.lower()
        else RejectionReason.DOCUMENT_MISMATCH
    )
    return Decision(
        decision_type=DecisionType.MANUAL_REVIEW,
        claimed_amount=claim.claimed_amount,
        rejection_reasons=[reason],
        confidence=0.0,
        explanation=halt_message,
        manual_review_note="Resolve the document issue and resubmit to proceed.",
    )


@app.post("/api/claims", response_model=FinalOutput)
async def submit_claim(claim: ClaimSubmission) -> FinalOutput:
    claim_id = str(uuid.uuid4())
    t0 = time.time()

    initial_state: GraphState = {
        "claim": claim,
        "claim_id": claim_id,
        "intake_ok": None,
        "classified_docs": [],
        "verification_ok": None,
        "verification_message": None,
        "fused_docs": [],
        "fraud_result": None,
        "decision": None,
        "trace": [],
        "failed_components": [],
        "extraction_confidence": 1.0,
        "halt": False,
        "halt_message": None,
    }

    result = await claims_graph.ainvoke(initial_state)
    elapsed = int((time.time() - t0) * 1000)

    decision: Decision | None = result.get("decision")
    halt = result.get("halt", False)
    halt_message: str = result.get("halt_message") or "Processing stopped."
    intake_ok = result.get("intake_ok")

    if decision is None:
        decision = _build_halt_decision(claim, halt_message, intake_ok)

    output = FinalOutput(
        claim_id=claim_id,
        member_id=claim.member_id,
        policy_id=claim.policy_id,
        claim_category=claim.claim_category.value,
        treatment_date=str(claim.treatment_date),
        decision=decision,
        trace=result.get("trace", []),
        processing_time_ms=elapsed,
        pipeline_complete=not halt,
        degraded_components=result.get("failed_components", []),
    )

    # Persist claim and trace events asynchronously
    claim_repo = ClaimRepository(settings.db_path)
    trace_repo = TraceRepository(settings.db_path)
    await claim_repo.save(output)
    await trace_repo.save_events(output.trace)

    return output


@app.get("/api/claims", response_model=list[dict])
async def list_claims(limit: int = 20) -> list[dict]:
    repo = ClaimRepository(settings.db_path)
    return await repo.list_recent(limit)


@app.get("/api/claims/{claim_id}", response_model=FinalOutput)
async def get_claim(claim_id: str) -> FinalOutput:
    repo = ClaimRepository(settings.db_path)
    output = await repo.get(claim_id)
    if output is None:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    return output


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
