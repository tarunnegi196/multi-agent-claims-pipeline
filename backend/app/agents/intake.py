"""
IntakeAgent — validates the claim envelope before any document work begins.

Checks: member in roster, amount ≥ minimum, at least one document attached.
Fast-fails structural garbage without spending LLM tokens.
Publishes every TraceEvent to the event bus for live SSE streaming.
"""
import time

from app.models.graph_state import GraphState
from app.models.trace import TraceEvent, TraceStatus
from app.engine.policy_loader import load_policy
from app.db.bus import event_bus


async def _pub(claim_id: str, step_id: str, status: TraceStatus,
               detail: str = "", rule: str = "",
               confidence: float | None = None, error: str | None = None) -> TraceEvent:
    """Create a TraceEvent, publish to bus, and return it."""
    event = TraceEvent(
        claim_id=claim_id, step_id=step_id, agent="IntakeAgent",
        status=status, detail=detail, rule_reference=rule or None,
        confidence=confidence, error=error,
    )
    await event_bus.publish(event)
    return event


async def intake_node(state: GraphState) -> dict:
    claim = state["claim"]
    claim_id = state["claim_id"]
    t0 = time.time()
    events: list[TraceEvent] = []

    policy = load_policy()

    # 1. Member lookup
    member = policy.get_member(claim.member_id)
    if member is None:
        events.append(await _pub(claim_id, "intake.member", TraceStatus.FAIL,
                                 detail=f"Member '{claim.member_id}' not found in policy roster",
                                 rule="members"))
        return {
            "intake_ok": False,
            "halt": True,
            "halt_message": (
                f"Member ID '{claim.member_id}' is not registered under policy "
                f"'{claim.policy_id}'. Please verify your member ID."
            ),
            "trace": events,
        }
    events.append(await _pub(claim_id, "intake.member", TraceStatus.PASS,
                             detail=f"Member '{member.name}' ({claim.member_id}) found",
                             rule="members", confidence=1.0))

    # 2. Minimum claim amount
    min_amt = policy.submission_rules.minimum_claim_amount
    if claim.claimed_amount < min_amt:
        events.append(await _pub(claim_id, "intake.min_amount", TraceStatus.FAIL,
                                 detail=f"₹{claim.claimed_amount:.0f} < minimum ₹{min_amt:.0f}",
                                 rule="submission_rules.minimum_claim_amount"))
        return {
            "intake_ok": False,
            "halt": True,
            "halt_message": (
                f"Claimed amount ₹{claim.claimed_amount:.0f} is below the minimum "
                f"claimable amount of ₹{min_amt:.0f}."
            ),
            "trace": events,
        }
    events.append(await _pub(claim_id, "intake.min_amount", TraceStatus.PASS,
                             detail=f"₹{claim.claimed_amount:.0f} ≥ minimum ₹{min_amt:.0f}",
                             rule="submission_rules.minimum_claim_amount", confidence=1.0))

    # 3. Documents attached
    if not claim.documents:
        events.append(await _pub(claim_id, "intake.docs_present", TraceStatus.FAIL,
                                 detail="No documents uploaded"))
        return {
            "intake_ok": False,
            "halt": True,
            "halt_message": "At least one document must be uploaded with your claim.",
            "trace": events,
        }
    elapsed = int((time.time() - t0) * 1000)
    events.append(await _pub(claim_id, "intake.docs_present", TraceStatus.PASS,
                             detail=f"{len(claim.documents)} document(s) attached",
                             confidence=1.0))
    events[-1] = events[-1].model_copy(update={"duration_ms": elapsed})

    return {"intake_ok": True, "halt": False, "trace": events}
