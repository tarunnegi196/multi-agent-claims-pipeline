"""
FraudScreenAgent — deterministic fraud checks against policy thresholds.

Signals checked:
  - Same-day claim count vs. same_day_claims_limit
  - Monthly claim count vs. monthly_claims_limit
  - High-value claim flag
  - Document alteration flags from extraction

force_manual_review is set to True when same-day limit is exceeded
or fraud_score reaches fraud_score_manual_review_threshold.
"""
import logging
import time

from app.models.graph_state import GraphState
from app.models.decision import FraudResult
from app.models.trace import TraceEvent, TraceStatus
from app.engine.policy_loader import load_policy
from app.db.bus import event_bus

logger = logging.getLogger(__name__)


def _emit(claim_id: str, step_id: str, status: TraceStatus,
          detail: str = "", rule: str = "", confidence: float | None = None) -> TraceEvent:
    return TraceEvent(
        claim_id=claim_id, step_id=step_id, agent="FraudScreenAgent",
        status=status, detail=detail, rule_reference=rule or None,
        confidence=confidence,
    )


async def fraud_node(state: GraphState) -> dict:
    claim = state["claim"]
    claim_id = state["claim_id"]
    t0 = time.time()
    events: list[TraceEvent] = []

    policy = load_policy()
    thresholds = policy.fraud_thresholds
    flags: list[str] = []
    fraud_score = 0.0

    treatment_date = claim.treatment_date

    # ── 1. Same-day claim count ──────────────────────────────────────────────
    same_day_prior = [h for h in claim.claims_history if h.date == treatment_date]
    same_day_count = len(same_day_prior)

    if same_day_count >= thresholds.same_day_claims_limit:
        total_same_day = same_day_count + 1  # including current
        flags.append(
            f"SAME_DAY_CLAIMS: {total_same_day} claims on {treatment_date} "
            f"(limit: {thresholds.same_day_claims_limit})"
        )
        fraud_score += 0.5
        events.append(_emit(
            claim_id, "fraud.same_day", TraceStatus.WARN,
            detail=(
                f"{same_day_count} prior same-day claims found on {treatment_date}; "
                f"limit is {thresholds.same_day_claims_limit}"
            ),
            rule="fraud_thresholds.same_day_claims_limit",
        ))
    else:
        events.append(_emit(
            claim_id, "fraud.same_day", TraceStatus.PASS,
            detail=f"{same_day_count} prior same-day claim(s) — within limit",
        ))

    # ── 2. Monthly claim count ───────────────────────────────────────────────
    monthly_prior = [
        h for h in claim.claims_history
        if h.date.year == treatment_date.year and h.date.month == treatment_date.month
    ]
    monthly_count = len(monthly_prior)

    if monthly_count >= thresholds.monthly_claims_limit:
        flags.append(
            f"MONTHLY_CLAIMS: {monthly_count + 1} claims this month "
            f"(limit: {thresholds.monthly_claims_limit})"
        )
        fraud_score += 0.3
        events.append(_emit(
            claim_id, "fraud.monthly", TraceStatus.WARN,
            detail=(
                f"{monthly_count} prior claims this month; "
                f"limit is {thresholds.monthly_claims_limit}"
            ),
            rule="fraud_thresholds.monthly_claims_limit",
        ))
    else:
        events.append(_emit(
            claim_id, "fraud.monthly", TraceStatus.PASS,
            detail=f"{monthly_count} prior claim(s) this month — within limit",
        ))

    # ── 3. High-value flag ───────────────────────────────────────────────────
    if claim.claimed_amount >= thresholds.high_value_claim_threshold:
        flags.append(
            f"HIGH_VALUE: ₹{claim.claimed_amount:.0f} ≥ "
            f"threshold ₹{thresholds.high_value_claim_threshold:.0f}"
        )
        fraud_score += 0.1
        events.append(_emit(
            claim_id, "fraud.high_value", TraceStatus.WARN,
            detail=f"High-value claim: ₹{claim.claimed_amount:.0f}",
            rule="fraud_thresholds.high_value_claim_threshold",
        ))
    else:
        events.append(_emit(
            claim_id, "fraud.high_value", TraceStatus.PASS,
            detail=f"₹{claim.claimed_amount:.0f} below high-value threshold",
        ))

    # ── 4. Document alteration flags from extraction ─────────────────────────
    for fdoc in state.get("fused_docs", []):
        if "DOCUMENT_ALTERATION" in fdoc.flags:
            flags.append(f"DOCUMENT_ALTERATION in {fdoc.file_id}")
            fraud_score += 0.3

    # ── 5. Cross-document consistency flags (from ConsistencyAgent) ──────────
    consistency_flags = state.get("consistency_flags") or []
    for cflag in consistency_flags:
        flags.append(f"CROSS_DOC: {cflag}")
        fraud_score += 0.15
        events.append(_emit(
            claim_id, "fraud.cross_doc", TraceStatus.WARN,
            detail=cflag,
            rule="cross_document_consistency",
        ))

    fraud_score = min(fraud_score, 1.0)

    # force_manual_review if same-day limit breached OR score at threshold
    force_review = (
        same_day_count >= thresholds.same_day_claims_limit
        or fraud_score >= thresholds.fraud_score_manual_review_threshold
        or claim.claimed_amount >= thresholds.auto_manual_review_above
    )

    result = FraudResult(
        fraud_score=fraud_score,
        flags=flags,
        force_manual_review=force_review,
        same_day_count=same_day_count,
        monthly_count=monthly_count,
    )

    if force_review:
        logger.warning("[FRAUD] force_manual_review  score=%.2f  flags=%s", fraud_score, flags)
    else:
        logger.info("[FRAUD] clear  score=%.2f  same_day=%d  monthly=%d",
                    fraud_score, same_day_count, monthly_count)

    summary_status = TraceStatus.WARN if force_review else TraceStatus.PASS
    events.append(_emit(
        claim_id, "fraud.summary", summary_status,
        detail=(
            f"score={fraud_score:.2f}, force_review={force_review}, "
            f"flags={flags or 'none'}"
        ),
        rule="fraud_thresholds",
        confidence=1.0 - fraud_score,
    ))

    elapsed = int((time.time() - t0) * 1000)
    events[-1] = events[-1].model_copy(update={"duration_ms": elapsed})

    for e in events:
        await event_bus.publish(e)

    return {"fraud_result": result, "trace": events}
