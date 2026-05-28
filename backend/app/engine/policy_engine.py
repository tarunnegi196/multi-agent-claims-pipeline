"""
Deterministic policy engine.

LLMs never touch this file. Every decision is pure Python reading from policy_terms.json.
Input: structured facts (FusedDoc list). Output: Decision + TraceEvent list.
The decision is a fold over the trace — they can never disagree.
"""
import re
from datetime import date, timedelta
from typing import Optional

from app.models.claim import ClaimSubmission, ClaimCategory
from app.models.document import FusedDoc
from app.models.trace import TraceEvent, TraceStatus
from app.models.decision import (
    Decision, DecisionType, RejectionReason,
    LineItemDecision, AmountBreakdown, FraudResult,
)
from app.models.policy import PolicyTerms


# ── Condition / exclusion keyword maps ─────────────────────────────────────────

# diagnosis text → policy waiting_period condition key
_CONDITION_KEYWORDS: dict[str, list[str]] = {
    "diabetes": ["diabetes", "t2dm", "type 2", "type ii", "diabetic"],
    "hypertension": ["hypertension", "htn", "blood pressure"],
    "thyroid_disorders": ["thyroid", "hypothyroid", "hyperthyroid"],
    "joint_replacement": ["joint replacement", "knee replacement", "hip replacement"],
    "maternity": ["pregnancy", "maternity", "antenatal", "prenatal", "obstetric"],
    "mental_health": ["depression", "anxiety", "psychiatric", "mental health"],
    "obesity_treatment": ["obesity", "bariatric", "weight loss program", "bmi"],
    "hernia": ["hernia"],
    "cataract": ["cataract"],
}

# text → policy exclusion label (checked against diagnosis + treatment + line items)
_EXCLUSION_KEYWORDS: dict[str, list[str]] = {
    "Obesity and weight loss programs": [
        "obesity", "weight loss", "diet plan", "nutrition program", "bariatric",
    ],
    "Bariatric surgery": ["bariatric"],
    "Cosmetic or aesthetic procedures": ["cosmetic", "aesthetic"],
    "Substance abuse treatment": ["substance abuse", "de-addiction", "alcohol abuse"],
    "Infertility and assisted reproduction": ["infertility", "ivf", "iui"],
    "Experimental treatments": ["experimental", "clinical trial"],
}


# ── Helpers ─────────────────────────────────────────────────────────────────────

def _emit(claim_id: str, step_id: str, agent: str, status: TraceStatus,
          detail: str = "", rule: str = "", confidence: float | None = None,
          error: str | None = None) -> TraceEvent:
    return TraceEvent(
        claim_id=claim_id, step_id=step_id, agent=agent,
        status=status, detail=detail, rule_reference=rule,
        confidence=confidence, error=error,
    )


def _doc_text(fused_docs: list[FusedDoc]) -> str:
    """Aggregate all text fields from fused docs into one lowercase string."""
    parts: list[str] = []
    for doc in fused_docs:
        for f in (doc.diagnosis, doc.doctor_name, doc.hospital_name):
            if f:
                parts.append(f.lower())
        parts.extend(m.lower() for m in doc.medicines)
        parts.extend(t.lower() for t in doc.tests_ordered)
        parts.extend(li.description.lower() for li in doc.line_items)
        if doc.patient_name:
            parts.append(doc.patient_name.lower())
    return " ".join(parts)


def _word_match(text: str, keyword: str) -> bool:
    """Case-insensitive whole-word match — prevents 'herniation' triggering 'hernia'."""
    return bool(re.search(r"\b" + re.escape(keyword) + r"\b", text, re.IGNORECASE))


def _match_condition(text: str) -> str | None:
    for condition, keywords in _CONDITION_KEYWORDS.items():
        if any(_word_match(text, kw) for kw in keywords):
            return condition
    return None


def _match_exclusion(text: str) -> str | None:
    for exclusion, keywords in _EXCLUSION_KEYWORDS.items():
        if any(_word_match(text, kw) for kw in keywords):
            return exclusion
    return None


def _evaluate_dental_line_items(
    fused_docs: list[FusedDoc],
    covered: list[str],
    excluded: list[str],
) -> list[LineItemDecision]:
    decisions: list[LineItemDecision] = []
    for doc in fused_docs:
        for item in doc.line_items:
            desc = item.description.lower()
            is_excluded = any(ep.lower() in desc or desc in ep.lower() for ep in excluded)
            if is_excluded:
                matched = next(ep for ep in excluded if ep.lower() in desc or desc in ep.lower())
                decisions.append(LineItemDecision(
                    description=item.description,
                    claimed_amount=item.amount,
                    approved_amount=0.0,
                    status="REJECTED",
                    reason=f"'{matched}' is a cosmetic/excluded dental procedure not covered by policy",
                ))
            else:
                decisions.append(LineItemDecision(
                    description=item.description,
                    claimed_amount=item.amount,
                    approved_amount=item.amount,
                    status="APPROVED",
                ))
    return decisions


def _make_rejected(
    reasons: list[RejectionReason],
    claimed: float,
    confidence: float,
    explanation: str,
    events: list[TraceEvent],
    eligibility_date: str | None = None,
    fraud_flags: list[str] | None = None,
) -> tuple[Decision, list[TraceEvent]]:
    return Decision(
        decision_type=DecisionType.REJECTED,
        approved_amount=0.0,
        claimed_amount=claimed,
        rejection_reasons=reasons,
        confidence=confidence,
        explanation=explanation,
        eligibility_date=eligibility_date,
        fraud_flags=fraud_flags or [],
    ), events


# ── Main engine ──────────────────────────────────────────────────────────────────

def evaluate(
    claim: ClaimSubmission,
    claim_id: str,
    fused_docs: list[FusedDoc],
    fraud_result: FraudResult,
    policy: PolicyTerms,
    reference_date: date | None = None,
) -> tuple[Decision, list[TraceEvent]]:
    """
    Evaluate a claim against policy rules and return (Decision, [TraceEvent]).

    reference_date: override today's date (used in tests to avoid deadline failures).
    """
    today = reference_date or date.today()
    events: list[TraceEvent] = []
    A = "PolicyEngine"

    def ev(step: str, status: TraceStatus, detail: str = "", rule: str = "",
           conf: float | None = None, error: str | None = None) -> None:
        events.append(_emit(claim_id, step, A, status, detail, rule, conf, error))

    # ── 1. Member lookup ────────────────────────────────────────────────────
    member = policy.get_member(claim.member_id)
    if not member:
        ev("eligibility.member_lookup", TraceStatus.FAIL,
           f"Member {claim.member_id} not in roster", rule="members[]")
        return _make_rejected(
            [RejectionReason.MEMBER_NOT_FOUND], claim.claimed_amount, 0.95,
            f"Member ID {claim.member_id} is not enrolled in policy {claim.policy_id}.", events)

    ev("eligibility.member_lookup", TraceStatus.PASS,
       f"Member '{member.name}' ({member.member_id}) found", conf=1.0)

    # ── 2. Policy active ────────────────────────────────────────────────────
    p_start = date.fromisoformat(policy.policy_holder.policy_start_date)
    p_end = date.fromisoformat(policy.policy_holder.policy_end_date)
    if not (p_start <= claim.treatment_date <= p_end):
        ev("eligibility.policy_active", TraceStatus.FAIL,
           f"Treatment {claim.treatment_date} outside policy period {p_start}–{p_end}",
           rule="policy_holder.policy_start_date/policy_end_date")
        return _make_rejected(
            [RejectionReason.POLICY_INACTIVE], claim.claimed_amount, 0.95,
            f"Treatment date {claim.treatment_date} is outside the active policy period "
            f"({p_start} to {p_end}).", events)

    ev("eligibility.policy_active", TraceStatus.PASS,
       f"Treatment date within policy period", conf=1.0)

    # ── 3. Submission deadline ──────────────────────────────────────────────
    days_elapsed = (today - claim.treatment_date).days
    deadline = policy.submission_rules.deadline_days_from_treatment
    if days_elapsed > deadline:
        ev("eligibility.submission_deadline", TraceStatus.FAIL,
           f"Submitted {days_elapsed} days after treatment; deadline is {deadline} days",
           rule="submission_rules.deadline_days_from_treatment")
        return _make_rejected(
            [RejectionReason.SUBMISSION_DEADLINE_MISSED], claim.claimed_amount, 0.95,
            f"Claim submitted {days_elapsed} days after treatment. "
            f"Submission deadline is {deadline} days from treatment date.", events)

    ev("eligibility.submission_deadline", TraceStatus.PASS,
       f"{days_elapsed}d elapsed ≤ {deadline}d deadline", conf=1.0)

    # ── 4. Minimum amount ───────────────────────────────────────────────────
    min_amt = policy.submission_rules.minimum_claim_amount
    if claim.claimed_amount < min_amt:
        ev("eligibility.minimum_amount", TraceStatus.FAIL,
           f"Claimed ₹{claim.claimed_amount} < minimum ₹{min_amt}",
           rule="submission_rules.minimum_claim_amount")
        return _make_rejected(
            [RejectionReason.BELOW_MINIMUM_AMOUNT], claim.claimed_amount, 0.95,
            f"Claimed amount ₹{claim.claimed_amount} is below the minimum "
            f"claimable amount of ₹{min_amt}.", events)

    ev("eligibility.minimum_amount", TraceStatus.PASS,
       f"₹{claim.claimed_amount} ≥ minimum ₹{min_amt}", conf=1.0)

    # ── 5. Coverage check ───────────────────────────────────────────────────
    category_key = claim.claim_category.value.lower()
    category = policy.opd_categories.get(category_key)
    if not category or not category.covered:
        ev("coverage.category_check", TraceStatus.FAIL,
           f"Category {claim.claim_category.value} not covered",
           rule=f"opd_categories.{category_key}.covered")
        return _make_rejected(
            [RejectionReason.NOT_COVERED], claim.claimed_amount, 0.95,
            f"{claim.claim_category.value} treatment is not covered under this policy.", events)

    ev("coverage.category_check", TraceStatus.PASS,
       f"Category {claim.claim_category.value} covered under policy", conf=1.0)

    # ── 7. General exclusions ───────────────────────────────────────────────
    all_text = _doc_text(fused_docs)
    matched_exclusion = _match_exclusion(all_text)
    if matched_exclusion:
        ev("coverage.exclusion_check", TraceStatus.FAIL,
           f"Treatment matches excluded condition: '{matched_exclusion}'",
           rule="exclusions.conditions", conf=0.92)
        return _make_rejected(
            [RejectionReason.EXCLUDED_CONDITION], claim.claimed_amount, 0.92,
            f"This claim covers an excluded treatment: '{matched_exclusion}'. "
            f"This is explicitly not covered under the policy.", events)

    ev("coverage.exclusion_check", TraceStatus.PASS,
       "No policy exclusions matched", conf=1.0)

    # ── 7b. Per-claim limit (consultation/pharmacy/vision/alt-medicine only) ──
    # DENTAL is evaluated line-by-line (sub_limit ₹10 000 governs approved sum).
    # DIAGNOSTIC uses pre-auth as primary gate; its sub_limit ₹10 000 > per_claim_limit.
    # Exclusion check intentionally runs first so excluded treatments are caught
    # before a limit check fires (prevents misleading PER_CLAIM_EXCEEDED on excluded claims).
    _LIMIT_CHECK_CATEGORIES = {
        ClaimCategory.CONSULTATION,
        ClaimCategory.PHARMACY,
        ClaimCategory.VISION,
        ClaimCategory.ALTERNATIVE_MEDICINE,
    }
    per_claim_limit = policy.coverage.per_claim_limit
    if claim.claim_category in _LIMIT_CHECK_CATEGORIES:
        if claim.claimed_amount > per_claim_limit:
            ev("eligibility.per_claim_limit", TraceStatus.FAIL,
               f"Claimed ₹{claim.claimed_amount:,.0f} > per-claim limit ₹{per_claim_limit:,.0f}",
               rule="coverage.per_claim_limit")
            return _make_rejected(
                [RejectionReason.PER_CLAIM_EXCEEDED], claim.claimed_amount, 0.95,
                f"Claimed amount ₹{claim.claimed_amount:,.0f} exceeds the per-claim limit "
                f"of ₹{per_claim_limit:,.0f}. Maximum claimable per claim is ₹{per_claim_limit:,.0f}.",
                events)
        ev("eligibility.per_claim_limit", TraceStatus.PASS,
           f"₹{claim.claimed_amount:,.0f} ≤ per-claim limit ₹{per_claim_limit:,.0f}", conf=1.0)
    else:
        ev("eligibility.per_claim_limit", TraceStatus.SKIP,
           f"{claim.claim_category.value} uses category sub_limit; per-claim limit not applied")

    # ── 8. Waiting period ───────────────────────────────────────────────────
    join_date_str = member.join_date
    eligibility_date_str: str | None = None

    if join_date_str:
        join_date = date.fromisoformat(join_date_str)
        days_since_join = (claim.treatment_date - join_date).days

        # 8a. Initial waiting period
        initial_wait = policy.waiting_periods.initial_waiting_period_days
        if days_since_join < initial_wait:
            eligible_on = join_date + timedelta(days=initial_wait)
            ev("waiting_period.initial", TraceStatus.FAIL,
               f"Only {days_since_join} days since joining; initial wait is {initial_wait} days. "
               f"Eligible from {eligible_on}",
               rule="waiting_periods.initial_waiting_period_days")
            return _make_rejected(
                [RejectionReason.WAITING_PERIOD], claim.claimed_amount, 0.95,
                f"Claim is within the {initial_wait}-day initial waiting period. "
                f"You will be eligible for claims from {eligible_on}.",
                events, eligibility_date=str(eligible_on))

        ev("waiting_period.initial", TraceStatus.PASS,
           f"{days_since_join}d since joining ≥ {initial_wait}d initial wait", conf=1.0)

        # 8b. Condition-specific waiting period
        condition = _match_condition(all_text)
        if condition and condition in policy.waiting_periods.specific_conditions:
            required = policy.waiting_periods.specific_conditions[condition]
            if days_since_join < required:
                eligible_on = join_date + timedelta(days=required)
                eligibility_date_str = str(eligible_on)
                ev("waiting_period.specific_condition", TraceStatus.FAIL,
                   f"Diagnosis maps to '{condition}' (wait: {required}d). "
                   f"Member has {days_since_join}d. Eligible from {eligible_on}",
                   rule=f"waiting_periods.specific_conditions.{condition}")
                return _make_rejected(
                    [RejectionReason.WAITING_PERIOD], claim.claimed_amount, 0.95,
                    f"Treatment for {condition.replace('_', ' ')} has a {required}-day waiting period. "
                    f"Member joined {join_date} ({days_since_join} days ago). "
                    f"Eligible for {condition.replace('_', ' ')} claims from {eligible_on}.",
                    events, eligibility_date=eligibility_date_str)

            ev("waiting_period.specific_condition", TraceStatus.PASS,
               f"Condition '{condition}': {days_since_join}d ≥ {required}d wait", conf=1.0)
        else:
            ev("waiting_period.specific_condition", TraceStatus.PASS,
               "No condition-specific waiting period applies", conf=1.0)
    else:
        ev("waiting_period.check", TraceStatus.SKIP,
           "Dependent member — no join_date; initial waiting period not applicable")

    # ── 9. Pre-authorization ────────────────────────────────────────────────
    if claim.claim_category == ClaimCategory.DIAGNOSTIC:
        pre_auth_threshold = category.pre_auth_threshold or 10_000
        hvt = [t.lower() for t in category.high_value_tests_requiring_pre_auth]
        matched_test = ""
        for doc in fused_docs:
            for test in doc.tests_ordered:
                if any(h in test.lower() for h in hvt):
                    matched_test = test
            for item in doc.line_items:
                if any(h in item.description.lower() for h in hvt):
                    matched_test = item.description

        if matched_test and claim.claimed_amount > pre_auth_threshold:
            ev("pre_auth.check", TraceStatus.FAIL,
               f"'{matched_test}' (₹{claim.claimed_amount:,.0f}) requires pre-auth "
               f"above ₹{pre_auth_threshold:,.0f}. None found.",
               rule="pre_authorization.required_for")
            return _make_rejected(
                [RejectionReason.PRE_AUTH_MISSING], claim.claimed_amount, 0.95,
                f"Pre-authorization is required for {matched_test} when the claim "
                f"exceeds ₹{pre_auth_threshold:,.0f}. No pre-authorization was submitted. "
                f"To resubmit: obtain pre-authorization from ICICI Lombard before the procedure, "
                f"then include the pre-auth reference number with your claim.", events)

        ev("pre_auth.check", TraceStatus.PASS,
           "Pre-authorization check passed", conf=1.0)
    else:
        ev("pre_auth.check", TraceStatus.SKIP,
           f"Pre-auth not required for {claim.claim_category.value}")

    # ── 10. Fraud overlay ───────────────────────────────────────────────────
    if fraud_result.force_manual_review:
        flags_str = "; ".join(fraud_result.flags) or "elevated fraud score"
        ev("fraud.overlay", TraceStatus.WARN,
           f"Fraud signals (score={fraud_result.fraud_score:.2f}): {flags_str}",
           rule="fraud_thresholds", conf=fraud_result.fraud_score)
        return Decision(
            decision_type=DecisionType.MANUAL_REVIEW,
            approved_amount=0.0,
            claimed_amount=claim.claimed_amount,
            confidence=0.70,
            explanation=(
                f"Claim flagged for manual review: {flags_str}. "
                f"A claims reviewer will assess this within 2 business days."
            ),
            manual_review_note=flags_str,
            fraud_flags=fraud_result.flags,
        ), events

    ev("fraud.overlay", TraceStatus.PASS,
       f"Fraud score {fraud_result.fraud_score:.2f} below threshold", conf=1.0)

    # ── 11. Line-item decisions (dental) ────────────────────────────────────
    line_item_decisions: list[LineItemDecision] = []
    if claim.claim_category == ClaimCategory.DENTAL:
        line_item_decisions = _evaluate_dental_line_items(
            fused_docs,
            covered=category.covered_procedures,
            excluded=category.excluded_procedures,
        )
        approved_count = sum(1 for li in line_item_decisions if li.status == "APPROVED")
        rejected_count = sum(1 for li in line_item_decisions if li.status == "REJECTED")
        status = TraceStatus.WARN if rejected_count else TraceStatus.PASS
        ev("coverage.line_items", status,
           f"{approved_count} item(s) approved, {rejected_count} item(s) excluded",
           rule="opd_categories.dental.excluded_procedures", conf=1.0)

    # ── 12. Amount calculation ──────────────────────────────────────────────
    base = (
        sum(li.approved_amount for li in line_item_decisions)
        if line_item_decisions else claim.claimed_amount
    )

    # Determine hospital name from claim field or extracted docs
    hospital = claim.hospital_name or ""
    for doc in fused_docs:
        if doc.hospital_name:
            hospital = doc.hospital_name
            break

    is_network = policy.is_network_hospital(hospital)
    discount_pct = category.network_discount_percent if is_network else 0.0
    discount_amt = round(base * discount_pct / 100, 2)
    after_discount = round(base - discount_amt, 2)

    copay_pct = category.copay_percent
    copay_amt = round(after_discount * copay_pct / 100, 2)
    after_copay = round(after_discount - copay_amt, 2)

    final_approved = after_copay

    breakdown = AmountBreakdown(
        claimed=claim.claimed_amount,
        network_discount_percent=discount_pct,
        network_discount_amount=discount_amt,
        after_network_discount=after_discount,
        copay_percent=copay_pct,
        copay_amount=copay_amt,
        after_copay=after_copay,
        sub_limit_applied=category.sub_limit,
        final_approved=final_approved,
    )

    network_note = f"; network discount {discount_pct:.0f}% → ₹{discount_amt:,.0f} off" if is_network else ""
    ev("amount.calculation", TraceStatus.PASS,
       f"Base ₹{base:,.0f}{network_note}; co-pay {copay_pct:.0f}% → ₹{copay_amt:,.0f} off; "
       f"final ₹{final_approved:,.0f}",
       rule="opd_categories.copay_percent + network_discount_percent", conf=1.0)

    # ── 13. Final decision ──────────────────────────────────────────────────
    has_rejected = any(li.status == "REJECTED" for li in line_item_decisions)
    has_approved = any(li.status == "APPROVED" for li in line_item_decisions)
    decision_type = (
        DecisionType.PARTIAL
        if (line_item_decisions and has_rejected and has_approved)
        else DecisionType.APPROVED
    )

    explanation = _build_explanation(
        decision_type, final_approved, claim.claimed_amount,
        breakdown, is_network, line_item_decisions,
    )

    ev("decision.final", TraceStatus.PASS,
       f"Decision: {decision_type.value}  approved ₹{final_approved:,.0f}", conf=0.90)

    return Decision(
        decision_type=decision_type,
        approved_amount=final_approved,
        claimed_amount=claim.claimed_amount,
        amount_breakdown=breakdown,
        line_item_decisions=line_item_decisions,
        rejection_reasons=[],
        confidence=0.90,
        explanation=explanation,
    ), events


# ── Explanation builders ─────────────────────────────────────────────────────────

def _build_explanation(
    dtype: DecisionType,
    approved: float,
    claimed: float,
    breakdown: AmountBreakdown,
    is_network: bool,
    line_items: list[LineItemDecision],
) -> str:
    parts: list[str] = []

    if dtype == DecisionType.PARTIAL:
        parts.append(f"Partial approval: ₹{approved:,.0f} approved out of ₹{claimed:,.0f} claimed.")
    else:
        parts.append(f"Claim approved for ₹{approved:,.0f}.")

    if line_items:
        for li in line_items:
            if li.status == "REJECTED":
                parts.append(f" '{li.description}' (₹{li.claimed_amount:,.0f}) excluded — {li.reason}.")
            else:
                parts.append(f" '{li.description}' (₹{li.claimed_amount:,.0f}) approved.")

    if is_network and breakdown.network_discount_amount > 0:
        parts.append(
            f" Network hospital discount ({breakdown.network_discount_percent:.0f}%) applied: "
            f"₹{breakdown.claimed:,.0f} → ₹{breakdown.after_network_discount:,.0f}."
        )

    if breakdown.copay_amount > 0:
        parts.append(
            f" Co-pay ({breakdown.copay_percent:.0f}%): ₹{breakdown.copay_amount:,.0f} deducted."
        )

    return "".join(parts)
