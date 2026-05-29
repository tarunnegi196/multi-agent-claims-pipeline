"""
ConsistencyAgent — cross-document semantic consistency check.

Runs after extraction. For every uploaded document, collects the key entity
fields (patient, doctor, hospital, date, doctor_registration) and asks Gemini
to verify that all documents refer to the same person / provider / episode.

Hard patient mismatches are already halted earlier inside extractor.py.
This agent surfaces softer signals: doctor differs across docs, hospital
mismatch, dates >7 days apart, fuzzy patient variants — none of which halt
the pipeline; they raise consistency_flags consumed by FraudScreen and
DecisionComposer to adjust confidence and route to MANUAL_REVIEW when needed.

Falls back to a deterministic comparison when the LLM is unavailable so the
pipeline never depends on Gemini for correctness — only for richness.
"""
import logging
import time

from app.models.graph_state import GraphState
from app.models.trace import TraceEvent, TraceStatus
from app.db.bus import event_bus
from app.providers.gemini_consistency import gemini_consistency

logger = logging.getLogger(__name__)


def _emit(claim_id: str, step_id: str, status: TraceStatus,
          detail: str = "", confidence: float | None = None,
          rule: str | None = None) -> TraceEvent:
    return TraceEvent(
        claim_id=claim_id, step_id=step_id, agent="ConsistencyAgent",
        status=status, detail=detail, confidence=confidence,
        rule_reference=rule,
    )


def _normalize(s: str | None) -> str:
    if not s:
        return ""
    s = s.lower().strip()
    # strip common titles & punctuation
    for tok in ("dr.", "dr ", "vaidya ", "mr.", "mr ", "mrs.", "mrs ", "ms.", "ms "):
        if s.startswith(tok):
            s = s[len(tok):]
    return s.replace(",", " ").replace(".", " ").replace("  ", " ").strip()


def _deterministic_check(docs: list[dict]) -> dict:
    """Cheap fallback when Gemini isn't available — flags hard mismatches only."""
    flags: list[str] = []
    patients = {_normalize(d.get("patient_name")) for d in docs if d.get("patient_name")}
    doctors = {_normalize(d.get("doctor_name")) for d in docs if d.get("doctor_name")}
    hospitals = {_normalize(d.get("hospital_name")) for d in docs if d.get("hospital_name")}

    patient_match = "MATCH" if len(patients) <= 1 else "MISMATCH"
    doctor_match = "MATCH" if len(doctors) <= 1 else ("FUZZY_MATCH" if len(doctors) == 2 else "MISMATCH")
    hospital_match = "MATCH" if len(hospitals) <= 1 else "FUZZY_MATCH"

    if len(doctors) > 1:
        flags.append(f"Doctor names differ across documents: {sorted(doctors)}")
    if len(hospitals) > 1:
        flags.append(f"Hospital/clinic names differ across documents: {sorted(hospitals)}")
    if len(patients) > 1:
        flags.append(f"Patient names differ across documents: {sorted(patients)}")

    overall = (patient_match != "MISMATCH" and doctor_match != "MISMATCH"
               and hospital_match != "MISMATCH")
    return {
        "patient_match": patient_match,
        "doctor_match": doctor_match,
        "hospital_match": hospital_match,
        "date_match": "UNVERIFIABLE",
        "overall_consistent": overall,
        "confidence": 0.7,
        "flags": flags,
        "reasoning": "Deterministic normalization-based check (LLM unavailable).",
    }


async def consistency_node(state: GraphState) -> dict:
    claim_id = state["claim_id"]
    fused_docs = state.get("fused_docs", [])
    t0 = time.time()
    events: list[TraceEvent] = []

    # Skip if extraction has nothing meaningful
    if not fused_docs:
        events.append(_emit(claim_id, "consistency.skip", TraceStatus.SKIP,
                            detail="No documents to compare"))
        for e in events:
            await event_bus.publish(e)
        return {"consistency_flags": [], "trace": events}

    docs_for_check = [
        {
            "file_id": f.file_id,
            "doc_type": f.document_type.value,
            "patient_name": f.patient_name,
            "date": f.date,
            "doctor_name": f.doctor_name,
            "doctor_registration": f.doctor_registration,
            "hospital_name": f.hospital_name or f.pharmacy_name or f.lab_name,
        }
        for f in fused_docs
    ]

    # Use LLM if available, else deterministic fallback
    verdict = None
    if gemini_consistency.is_available() and len(docs_for_check) >= 2:
        verdict = await gemini_consistency.check(docs_for_check)

    if verdict is None:
        verdict = _deterministic_check(docs_for_check)
        method = "deterministic"
    else:
        method = "gemini"

    flags = list(verdict.get("flags") or [])
    consistent = bool(verdict.get("overall_consistent", True))
    confidence = float(verdict.get("confidence", 0.7))

    # Emit per-dimension trace events for observability
    for dim in ("patient_match", "doctor_match", "hospital_match", "date_match"):
        val = verdict.get(dim, "UNVERIFIABLE")
        status = (
            TraceStatus.PASS if val in ("MATCH", "FUZZY_MATCH", "NOT_APPLICABLE")
            else TraceStatus.WARN if val == "UNVERIFIABLE"
            else TraceStatus.FAIL
        )
        events.append(_emit(
            claim_id, f"consistency.{dim}", status,
            detail=f"{dim.replace('_', ' ')}: {val}",
            confidence=confidence,
        ))

    status = TraceStatus.PASS if consistent else TraceStatus.WARN
    summary_detail = (
        f"method={method}, consistent={consistent}, flags={len(flags)}. "
        + (verdict.get("reasoning", "") or "")
    )
    events.append(_emit(claim_id, "consistency.summary", status,
                        detail=summary_detail, confidence=confidence))
    elapsed = int((time.time() - t0) * 1000)
    events[-1] = events[-1].model_copy(update={"duration_ms": elapsed})

    for e in events:
        await event_bus.publish(e)

    logger.info("[CONSISTENCY] method=%s  consistent=%s  flags=%d  duration=%dms",
                method, consistent, len(flags), elapsed)

    return {
        "consistency_flags": flags,
        "trace": events,
    }
