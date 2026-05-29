"""
FastAPI application — the HTTP boundary for the claims pipeline.

Endpoints (core):
  POST /api/claims             Submit a claim; runs the full LangGraph pipeline.
  GET  /api/claims             List recent claims (summary).
  GET  /api/claims/{id}        Retrieve a stored claim with full trace.

Endpoints (from api/routes.py):
  POST /api/files              Upload a document file; returns file_id + path.
  GET  /api/claims/{id}/trace         SSE live stream (connect before POST for live events).
  GET  /api/claims/{id}/trace/replay  SSE replay of stored events (demo hero).

  GET  /health                 Liveness probe.
"""
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api.report import build_pdf
from app.api.routes import router as extra_router
from app.config import settings
from app.db.bus import event_bus
from app.db.database import init_db
from app.db.repositories import ClaimRepository, TraceRepository
from app.graph import claims_graph
from app.logging_config import setup_logging
from app.models.claim import ClaimSubmission
from app.models.decision import Decision, DecisionType, DocumentSummary, FinalOutput, RejectionReason
from app.models.graph_state import GraphState

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure logging first so all startup messages are formatted correctly
    setup_logging(settings.log_level, settings.log_format)
    logger.info("=== Plum Claims Engine starting up ===")
    logger.info(
        "Config: db=%s  policy=%s  upload_dir=%s  gemini_key=%s",
        settings.db_path,
        settings.policy_file,
        settings.upload_dir,
        "SET" if settings.gemini_api_key else "NOT SET (test/stub mode)",
    )
    await init_db(settings.db_path)
    logger.info("Database initialised at %s", settings.db_path)
    yield
    logger.info("=== Plum Claims Engine shutting down ===")


app = FastAPI(title="Plum Claims Engine", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(extra_router)


# ── HTTP request/response logger ─────────────────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    duration = int((time.time() - t0) * 1000)
    # Skip noisy health-check and static asset logs at INFO level
    if request.url.path not in ("/health", "/favicon.ico"):
        logger.info(
            "%s %s → %d  (%d ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )
    return response


# ── Halt decision builder ────────────────────────────────────────────────────

def _build_halt_decision(claim: ClaimSubmission, halt_message: str,
                         intake_ok: bool | None) -> Decision:
    """
    Build a Decision when the pipeline halted before the composer ran.

    A halt is a legitimate, high-confidence outcome — the system is *certain*
    that the input cannot be processed. Confidence reflects that certainty
    (not zero, because we did make a clear judgement).
    """
    msg_lower = halt_message.lower()
    claimed = claim.claimed_amount or 0.0

    # Intake halts → hard REJECTED with high confidence
    if intake_ok is False:
        if "not registered" in msg_lower or "not found" in msg_lower:
            reason = RejectionReason.MEMBER_NOT_FOUND
        elif "minimum" in msg_lower or "below" in msg_lower:
            reason = RejectionReason.BELOW_MINIMUM_AMOUNT
        else:
            reason = RejectionReason.DOCUMENT_MISMATCH
        return Decision(
            decision_type=DecisionType.REJECTED,
            claimed_amount=claimed,
            rejection_reasons=[reason],
            confidence=0.98,
            explanation=halt_message,
        )

    # Document-stage halts → MANUAL_REVIEW. We are highly confident in the
    # diagnosis (wrong type, unreadable, patient mismatch) but the member can
    # remedy by resubmitting — so a human gate, not a hard reject.
    if "different patients" in msg_lower or "patient name" in msg_lower:
        reason = RejectionReason.DOCUMENT_MISMATCH
        note = (
            "Documents belong to different patients. Re-upload only documents "
            "for the patient on this claim and resubmit."
        )
    elif "re-upload" in msg_lower or "quality" in msg_lower or "unreadable" in msg_lower:
        reason = RejectionReason.UNREADABLE_DOCUMENT
        note = "Re-upload a clearer photo or scan and resubmit."
    else:
        reason = RejectionReason.DOCUMENT_MISMATCH
        note = "Upload the required document type(s) and resubmit."

    return Decision(
        decision_type=DecisionType.MANUAL_REVIEW,
        claimed_amount=claimed,
        rejection_reasons=[reason],
        confidence=0.92,
        explanation=halt_message,
        manual_review_note=note,
    )


# ── Core claim endpoints ──────────────────────────────────────────────────────

@app.post("/api/claims", response_model=FinalOutput)
async def submit_claim(claim: ClaimSubmission) -> FinalOutput:
    claim_id = claim.claim_id or str(uuid.uuid4())
    t0 = time.time()

    amt_str = f"₹{claim.claimed_amount:.0f}" if claim.claimed_amount else "(to be extracted)"
    logger.info(
        "[CLAIM-START] claim_id=%s  member=%s  category=%s  amount=%s  docs=%d  simulate_failure=%s",
        claim_id,
        claim.member_id,
        claim.claim_category.value,
        amt_str,
        len(claim.documents),
        claim.simulate_component_failure,
    )

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
        "consistency_flags": [],
        "bbox_regions": {},
        "halt": False,
        "halt_message": None,
    }

    result = await claims_graph.ainvoke(initial_state)
    elapsed = int((time.time() - t0) * 1000)

    # Signal the SSE live stream that processing is done
    await event_bus.close_stream(claim_id)

    decision: Decision | None = result.get("decision")
    halt = result.get("halt", False)
    halt_message: str = result.get("halt_message") or "Processing stopped."
    intake_ok = result.get("intake_ok")

    if decision is None:
        decision = _build_halt_decision(claim, halt_message, intake_ok)

    # Build doc summaries: use Gemini-classified type + quality where available
    classified_by_id = {c.file_id: c for c in result.get("classified_docs", [])}
    doc_summaries = [
        DocumentSummary(
            file_id=d.file_id,
            file_name=d.file_name,
            doc_type=(classified_by_id[d.file_id].document_type.value
                      if d.file_id in classified_by_id
                      else (d.actual_type or "UNKNOWN")),
            quality=(classified_by_id[d.file_id].quality.value
                     if d.file_id in classified_by_id
                     else (d.quality or "GOOD")),
            viewable=bool(d.file_path),
        )
        for d in claim.documents
    ]

    # Use the (possibly derived) claim from final state so treatment_date/amount
    # reflect values extracted from documents when the user didn't provide them.
    final_claim = result.get("claim") or claim
    td_str = str(final_claim.treatment_date) if final_claim.treatment_date else "—"
    output = FinalOutput(
        claim_id=claim_id,
        member_id=claim.member_id,
        policy_id=claim.policy_id,
        claim_category=claim.claim_category.value,
        treatment_date=td_str,
        decision=decision,
        trace=result.get("trace", []),
        processing_time_ms=elapsed,
        pipeline_complete=not halt,
        degraded_components=result.get("failed_components", []),
        documents=doc_summaries,
    )

    logger.info(
        "[CLAIM-END]   claim_id=%s  decision=%s  approved=₹%.0f  confidence=%.2f  "
        "halt=%s  degraded=%s  trace_events=%d  duration=%dms",
        claim_id,
        decision.decision_type.value,
        decision.approved_amount,
        decision.confidence,
        halt,
        output.degraded_components or "none",
        len(output.trace),
        elapsed,
    )

    claim_repo = ClaimRepository(settings.db_path)
    trace_repo = TraceRepository(settings.db_path)
    await claim_repo.save(output)
    await trace_repo.save_events(output.trace)

    return output


@app.get("/api/claims", response_model=list[dict])
async def list_claims(limit: int = 20) -> list[dict]:
    repo = ClaimRepository(settings.db_path)
    claims = await repo.list_recent(limit)
    logger.debug("list_claims: returned %d records (limit=%d)", len(claims), limit)
    return claims


@app.get("/api/claims/{claim_id}", response_model=FinalOutput)
async def get_claim(claim_id: str) -> FinalOutput:
    repo = ClaimRepository(settings.db_path)
    output = await repo.get(claim_id)
    if output is None:
        logger.warning("get_claim: claim_id=%s not found", claim_id)
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")
    logger.debug("get_claim: claim_id=%s  decision=%s", claim_id, output.decision.decision_type.value)
    return output


@app.get("/api/claims/{claim_id}/report")
async def download_claim_report(claim_id: str) -> Response:
    """
    Generate a PDF report for a completed claim.

    The report bundles the verdict, structured decision Q&A, amount breakdown,
    processed documents and pipeline trace summary. Suitable for evaluation
    bundles — one PDF per claim.
    """
    repo = ClaimRepository(settings.db_path)
    output = await repo.get(claim_id)
    if output is None:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

    claim_meta = {
        "claim_id":         output.claim_id,
        "member_id":        output.member_id,
        "policy_id":        output.policy_id,
        "claim_category":   output.claim_category,
        "treatment_date":   output.treatment_date,
    }
    pdf_bytes = build_pdf(
        claim_meta=claim_meta,
        decision=output.decision,
        documents=[d.model_dump() for d in output.documents],
        trace=output.trace,
        processing_ms=output.processing_time_ms,
    )
    filename = f"plum_claim_{output.claim_id[:8]}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# Serve React frontend — must be last so API routes take priority
import os as _os
from fastapi.staticfiles import StaticFiles as _StaticFiles

_dist = _os.path.normpath(
    _os.path.join(_os.path.dirname(__file__), "..", "..", "frontend", "dist")
)
if _os.path.isdir(_dist):
    app.mount("/", _StaticFiles(directory=_dist, html=True), name="static")
