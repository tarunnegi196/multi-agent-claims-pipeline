"""
DocVerifierAgent — THE GATE. Runs before any LLM extraction.

Two checks (in order):
  1. Quality: halt if any required document is UNREADABLE.
  2. Type completeness: halt if a required document type is missing.

On failure the halt_message is specific: names the uploaded types, the
required types, and what is missing — giving the member precise next steps.
Publishes every TraceEvent to the event bus for live SSE streaming.
"""
import logging
import time

from app.models.graph_state import GraphState
from app.models.document import DocumentQuality, DocumentType
from app.models.trace import TraceEvent, TraceStatus
from app.engine.policy_loader import load_policy
from app.db.bus import event_bus

logger = logging.getLogger(__name__)


async def _pub(claim_id: str, step_id: str, status: TraceStatus,
               detail: str = "", rule: str = "") -> TraceEvent:
    event = TraceEvent(
        claim_id=claim_id, step_id=step_id, agent="DocVerifierAgent",
        status=status, detail=detail, rule_reference=rule or None,
    )
    await event_bus.publish(event)
    return event


async def verify_node(state: GraphState) -> dict:
    claim = state["claim"]
    claim_id = state["claim_id"]
    t0 = time.time()
    events: list[TraceEvent] = []

    policy = load_policy()
    classified = state["classified_docs"]
    category = claim.claim_category.value

    logger.info("[VERIFY] start  claim_id=%s  category=%s  docs=%d",
                claim_id, category, len(classified))

    # ── 1. Quality gate ──────────────────────────────────────────────────────
    unreadable = [d for d in classified if d.quality == DocumentQuality.UNREADABLE]
    if unreadable:
        names = ", ".join(
            f"'{d.file_name}' ({d.document_type.value})" for d in unreadable
        )
        msg = (
            f"The following document(s) could not be read due to poor image quality: "
            f"{names}. "
            f"Please re-upload a clear, well-lit photo or scan of each document and "
            f"resubmit — do not re-upload documents that were already readable."
        )
        logger.warning("[VERIFY] HALT  quality_fail  unreadable=%s", names)
        events.append(await _pub(claim_id, "verify.quality", TraceStatus.FAIL,
                                 detail=f"Unreadable: {names}", rule="document_quality"))
        return {
            "verification_ok": False,
            "halt": True,
            "halt_message": msg,
            "trace": events,
        }
    events.append(await _pub(claim_id, "verify.quality", TraceStatus.PASS,
                             detail="All documents are readable"))

    # ── 2. Document-type completeness gate ───────────────────────────────────
    doc_reqs = policy.document_requirements
    if category not in doc_reqs:
        events.append(await _pub(claim_id, "verify.type_check", TraceStatus.WARN,
                                 detail=f"No document requirements configured for '{category}'"))
        return {"verification_ok": True, "halt": False, "trace": events}

    required_types = set(doc_reqs[category].required)
    # Documents the classifier could not identify at all → treat as a
    # readability problem, not a "wrong document" problem.
    unknown_docs = [d for d in classified if d.document_type == DocumentType.UNKNOWN]
    provided_types = {
        d.document_type.value for d in classified
        if d.document_type != DocumentType.UNKNOWN
    }
    missing = required_types - provided_types
    required_desc = ", ".join(sorted(required_types))

    # ── Case A: one or more documents could not be read / identified ─────────
    # Gemini returned UNKNOWN (blurry, dark, cropped, or not a clear medical
    # document). Tell the member exactly which file(s) to re-upload — never a
    # generic "missing document type" message that hides the real cause.
    if unknown_docs and missing:
        unreadable_names = ", ".join(f"'{d.file_name}'" for d in unknown_docs)
        msg = (
            f"We could not read or identify the following document(s): {unreadable_names}. "
            f"The image is likely blurry, too dark, cropped, or not a clear medical "
            f"document. Please re-upload a clear, well-lit photo or scan of each of these "
            f"specific file(s) and resubmit — you do not need to re-upload documents that "
            f"were read correctly. Your {category} claim requires: {required_desc}."
        )
        logger.warning("[VERIFY] HALT  unreadable_unknown  files=%s  required=%s",
                       unreadable_names, sorted(required_types))
        events.append(await _pub(
            claim_id, "verify.type_check", TraceStatus.FAIL,
            detail=f"Could not identify document(s): {unreadable_names}",
            rule="document_quality",
        ))
        return {
            "verification_ok": False,
            "halt": True,
            "halt_message": msg,
            "trace": events,
        }

    # ── Case B: documents are legible & identified, but a required type is
    # genuinely absent (e.g., two prescriptions when a hospital bill is needed) ─
    if missing:
        uploaded_desc = ", ".join(
            f"{d.document_type.value} ('{d.file_name}')" for d in classified
        )
        missing_desc = ", ".join(sorted(missing))
        msg = (
            f"Your {category} claim requires these document types: {required_desc}. "
            f"You uploaded: {uploaded_desc}. "
            f"Missing: {missing_desc}. "
            f"Please upload the missing document(s) and resubmit your claim."
        )
        logger.warning("[VERIFY] HALT  missing_docs  required=%s  provided=%s  missing=%s",
                       sorted(required_types), sorted(provided_types), sorted(missing))
        events.append(await _pub(
            claim_id, "verify.type_check", TraceStatus.FAIL,
            detail=f"Missing required: {missing_desc}",
            rule=f"document_requirements.{category}.required",
        ))
        return {
            "verification_ok": False,
            "halt": True,
            "halt_message": msg,
            "trace": events,
        }

    elapsed = int((time.time() - t0) * 1000)
    logger.info("[VERIFY] PASS  all_docs_present  required=%s  duration=%dms",
                sorted(required_types), elapsed)
    event = await _pub(
        claim_id, "verify.type_check", TraceStatus.PASS,
        detail=f"All required types present: {', '.join(sorted(required_types))}",
        rule=f"document_requirements.{category}.required",
    )
    events.append(event.model_copy(update={"duration_ms": elapsed}))

    return {"verification_ok": True, "halt": False, "trace": events}
