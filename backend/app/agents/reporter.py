"""
ReportAgent — final pipeline node. Adds LLM-synthesised narrative,
confidence_reasoning and next_best_actions to the Decision.

The deterministic policy engine has already produced the verdict, amount and
explanation; this agent only enriches presentation. If the LLM fails, a
templated fallback is used so the field is never empty.

Runs after DecisionComposer and after halt-paths too, so every claim — even
ones that stopped at intake — gets a richer narrative for the UI / PDF.
"""
import logging
import time

from app.models.graph_state import GraphState
from app.models.decision import Decision, DecisionType
from app.models.trace import TraceEvent, TraceStatus
from app.db.bus import event_bus
from app.providers.gemini_report import gemini_report

logger = logging.getLogger(__name__)


def _emit(claim_id: str, step_id: str, status: TraceStatus,
          detail: str = "", confidence: float | None = None) -> TraceEvent:
    return TraceEvent(
        claim_id=claim_id, step_id=step_id, agent="ReportAgent",
        status=status, detail=detail, confidence=confidence,
    )


def _fallback_narrative(decision: Decision, claim_category: str) -> dict:
    """Templated fallback used when the LLM is unavailable / errors."""
    dtype = decision.decision_type
    approved = decision.approved_amount
    claimed = decision.claimed_amount or 0.0

    if dtype == DecisionType.APPROVED:
        narrative = (
            f"Your {claim_category.lower()} claim has been approved. "
            f"Rs.{approved:,.0f} of Rs.{claimed:,.0f} claimed is payable "
            f"after applicable deductions."
        )
        actions = ["Payout will be processed to your registered account within 7 working days."]

    elif dtype == DecisionType.PARTIAL:
        narrative = (
            f"Your {claim_category.lower()} claim has been partially approved at "
            f"Rs.{approved:,.0f} out of Rs.{claimed:,.0f} claimed. "
            f"{decision.explanation}"
        )
        actions = [
            "Review the line-item breakdown to see which items were not covered.",
            "If you believe an excluded item should be reconsidered, raise an appeal with supporting documents.",
        ]

    elif dtype == DecisionType.REJECTED:
        reasons = ", ".join(r.value for r in decision.rejection_reasons) or "policy terms"
        narrative = (
            f"Your {claim_category.lower()} claim has been rejected. "
            f"Reason(s): {reasons}. {decision.explanation}"
        )
        actions = [
            "Review the policy clause cited in the decision reasoning.",
            "If documents were missing or unclear, gather the required paperwork and resubmit.",
        ]

    else:  # MANUAL_REVIEW
        narrative = (
            f"Your {claim_category.lower()} claim has been routed for manual review. "
            f"{decision.explanation}"
        )
        actions = [
            "A claims operator will review your submission within 24-48 hours.",
            "You may be contacted for clarification or additional documents.",
            "No action needed from you unless we reach out.",
        ]

    if decision.component_failures:
        narrative += " Note: one or more processing components ran in degraded mode."
        actions.append("Manual review is recommended due to partial automation.")

    if decision.confidence >= 0.85:
        reasoning = (
            "High confidence — the documents and policy clauses provided "
            "unambiguous support for this verdict."
        )
    elif decision.confidence >= 0.6:
        reasoning = (
            "Moderate confidence — some signals were ambiguous (extraction "
            "quality or cross-document variance) but the verdict still stands."
        )
    else:
        reasoning = (
            "Low confidence — multiple ambiguous signals; manual review is "
            "strongly recommended before payout."
        )

    return {
        "narrative": narrative,
        "confidence_reasoning": reasoning,
        "next_best_actions": actions,
    }


async def report_node(state: GraphState) -> dict:
    claim = state["claim"]
    claim_id = state["claim_id"]
    decision: Decision | None = state.get("decision")
    t0 = time.time()
    events: list[TraceEvent] = []

    if decision is None:
        events.append(_emit(claim_id, "report.skip", TraceStatus.SKIP,
                            detail="No decision to narrate"))
        for e in events:
            await event_bus.publish(e)
        return {"trace": events}

    consistency_flags = state.get("consistency_flags", [])
    failed = state.get("failed_components", [])
    halt = state.get("halt", False)
    halt_message = state.get("halt_message")

    # Build compact context for the LLM
    decision_dict = {
        "decision_type": decision.decision_type.value,
        "approved_amount": decision.approved_amount,
        "claimed_amount": decision.claimed_amount,
        "confidence": decision.confidence,
        "rejection_reasons": [r.value for r in decision.rejection_reasons],
        "explanation": decision.explanation,
        "fraud_flags": decision.fraud_flags,
        "consistency_flags": consistency_flags,
        "component_failures": list(set(list(decision.component_failures) + failed)),
        "amount_breakdown": decision.amount_breakdown.model_dump() if decision.amount_breakdown else None,
        "line_item_decisions": [li.model_dump() for li in decision.line_item_decisions],
        "eligibility_date": decision.eligibility_date,
    }
    claim_dict = {
        "member_id": claim.member_id,
        "category": claim.claim_category.value,
        "treatment_date": str(claim.treatment_date) if claim.treatment_date else None,
        "hospital_name": claim.hospital_name,
    }
    observations = {
        "halt": halt,
        "halt_message": halt_message,
        "consistency_flags": consistency_flags,
        "component_failures": failed,
        "num_documents": len(claim.documents),
    }

    enriched = None
    if gemini_report.is_available():
        enriched = await gemini_report.synthesise(decision_dict, claim_dict, observations)

    if enriched is None or not enriched.get("narrative"):
        enriched = _fallback_narrative(decision, claim.claim_category.value)
        method = "fallback"
    else:
        method = "gemini"

    updated_decision = decision.model_copy(update={
        "narrative": enriched["narrative"],
        "confidence_reasoning": enriched["confidence_reasoning"],
        "next_best_actions": enriched["next_best_actions"],
        "consistency_flags": consistency_flags,
    })

    elapsed = int((time.time() - t0) * 1000)
    events.append(_emit(
        claim_id, "report.synthesise", TraceStatus.PASS,
        detail=(
            f"Narrative+actions generated via {method} "
            f"({len(enriched['next_best_actions'])} actions, "
            f"{len(enriched['narrative'])} chars)"
        ),
        confidence=decision.confidence,
    ))
    events[-1] = events[-1].model_copy(update={"duration_ms": elapsed})

    for e in events:
        await event_bus.publish(e)

    logger.info("[REPORT] method=%s  actions=%d  duration=%dms",
                method, len(enriched["next_best_actions"]), elapsed)

    return {
        "decision": updated_decision,
        "trace": events,
    }
