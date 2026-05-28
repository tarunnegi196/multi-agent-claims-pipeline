"""
DocVerifierAgent — THE GATE. Runs before any LLM extraction.

Two checks (in order):
  1. Quality: halt if any required document is UNREADABLE.
  2. Type completeness: halt if a required document type is missing.

On failure the halt_message is specific: names the uploaded types, the
required types, and what is missing — giving the member precise next steps.
Publishes every TraceEvent to the event bus for live SSE streaming.
"""
import time

from app.models.graph_state import GraphState
from app.models.document import DocumentQuality
from app.models.trace import TraceEvent, TraceStatus
from app.engine.policy_loader import load_policy
from app.db.bus import event_bus


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
    provided_types = {d.document_type.value for d in classified}
    missing = required_types - provided_types

    if missing:
        uploaded_desc = ", ".join(
            f"{d.document_type.value} ('{d.file_name}')" for d in classified
        )
        missing_desc = ", ".join(sorted(missing))
        required_desc = ", ".join(sorted(required_types))
        msg = (
            f"Your {category} claim requires these document types: {required_desc}. "
            f"You uploaded: {uploaded_desc}. "
            f"Missing: {missing_desc}. "
            f"Please upload the missing document(s) and resubmit your claim."
        )
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
    event = await _pub(
        claim_id, "verify.type_check", TraceStatus.PASS,
        detail=f"All required types present: {', '.join(sorted(required_types))}",
        rule=f"document_requirements.{category}.required",
    )
    events.append(event.model_copy(update={"duration_ms": elapsed}))

    return {"verification_ok": True, "halt": False, "trace": events}
