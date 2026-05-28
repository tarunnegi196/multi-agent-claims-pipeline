"""
DecisionComposerAgent — the last node in the pipeline.

Calls the deterministic policy engine with the fused documents and fraud
result, then adjusts confidence downward if any components degraded.
Never makes a claim decision itself; it only assembles and annotates the
engine's output.
"""
import time

from app.models.graph_state import GraphState
from app.models.decision import Decision, FraudResult
from app.models.trace import TraceEvent, TraceStatus
from app.engine.policy_engine import evaluate
from app.engine.policy_loader import load_policy


def _emit(claim_id: str, step_id: str, status: TraceStatus,
          detail: str = "", confidence: float | None = None) -> TraceEvent:
    return TraceEvent(
        claim_id=claim_id, step_id=step_id, agent="DecisionComposerAgent",
        status=status, detail=detail, confidence=confidence,
    )


async def compose_node(state: GraphState) -> dict:
    claim = state["claim"]
    claim_id = state["claim_id"]
    t0 = time.time()
    events: list[TraceEvent] = []

    policy = load_policy()
    fused_docs = state.get("fused_docs", [])
    fraud_result: FraudResult = state.get("fraud_result") or FraudResult(fraud_score=0.0)
    failed = state.get("failed_components", [])
    extraction_confidence = state.get("extraction_confidence", 1.0)

    try:
        decision, engine_events = evaluate(
            claim=claim,
            claim_id=claim_id,
            fused_docs=fused_docs,
            fraud_result=fraud_result,
            policy=policy,
            reference_date=claim.treatment_date,
        )
    except Exception as exc:
        failed = list(failed) + ["PolicyEngine"]
        events.append(_emit(
            claim_id, "compose.engine_error", TraceStatus.FAIL,
            detail=f"Policy engine raised: {exc}",
        ))
        # Return a safe MANUAL_REVIEW fallback
        from app.models.decision import DecisionType
        decision = Decision(
            decision_type=DecisionType.MANUAL_REVIEW,
            claimed_amount=claim.claimed_amount,
            confidence=0.0,
            explanation=f"Policy engine error: {exc}. Manual review required.",
            component_failures=failed,
        )
        engine_events = []

    # Degrade confidence when extraction was impaired
    if failed and extraction_confidence < 1.0:
        degraded_conf = round(min(decision.confidence, extraction_confidence * 0.85), 3)
        decision = decision.model_copy(update={
            "confidence": degraded_conf,
            "component_failures": list(set(list(decision.component_failures) + failed)),
            "manual_review_note": (
                "Manual review recommended — one or more pipeline components "
                "operated in degraded mode. Decision confidence has been reduced accordingly."
            ),
        })

    elapsed = int((time.time() - t0) * 1000)
    events.append(_emit(
        claim_id, "compose.decision", TraceStatus.PASS,
        detail=(
            f"Decision: {decision.decision_type.value}, "
            f"approved=₹{decision.approved_amount:.0f}, "
            f"confidence={decision.confidence:.2f}"
        ),
        confidence=decision.confidence,
    ))
    events[-1] = events[-1].model_copy(update={"duration_ms": elapsed})

    return {
        "decision": decision,
        "trace": events + engine_events,
        "failed_components": failed,
    }
