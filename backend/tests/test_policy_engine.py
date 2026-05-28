"""
Unit tests for the deterministic policy engine.
Covers every decision path exercised by the 12 assignment test cases.
All tests pass reference_date to avoid submission-deadline failures.
"""
import pytest
from datetime import date

from app.models.claim import ClaimSubmission, ClaimCategory, DocumentRef
from app.models.document import FusedDoc, DocumentType, LineItem
from app.models.decision import DecisionType, RejectionReason, FraudResult
from app.engine.policy_loader import load_policy
from app.engine.policy_engine import evaluate


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def policy():
    return load_policy()


def _claim(**kwargs) -> ClaimSubmission:
    defaults = dict(
        member_id="EMP001",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory.CONSULTATION,
        treatment_date=date(2024, 11, 1),
        claimed_amount=1500,
        documents=[DocumentRef(file_id="F1", file_name="doc.pdf")],
    )
    defaults.update(kwargs)
    return ClaimSubmission(**defaults)


def _fused(doc_type=DocumentType.PRESCRIPTION, **kwargs) -> FusedDoc:
    defaults = dict(file_id="F1", document_type=doc_type)
    defaults.update(kwargs)
    return FusedDoc(**defaults)


def _no_fraud() -> FraudResult:
    return FraudResult(fraud_score=0.0)


def _force_fraud(flags: list[str]) -> FraudResult:
    return FraudResult(fraud_score=0.90, flags=flags, force_manual_review=True)


# reference_date is set just after treatment to avoid deadline failures
REF = date(2024, 11, 5)


# ── TC004: Clean consultation — full approval ─────────────────────────────────

def test_tc004_clean_consultation_approved(policy):
    claim = _claim(claimed_amount=1500, treatment_date=date(2024, 11, 1))
    docs = [
        _fused(DocumentType.PRESCRIPTION, patient_name="Rajesh Kumar", diagnosis="Viral Fever"),
        _fused(DocumentType.HOSPITAL_BILL, patient_name="Rajesh Kumar",
               hospital_name="City Clinic", total_amount=1500,
               line_items=[LineItem(description="Consultation Fee", amount=1000),
                           LineItem(description="CBC Test", amount=500)]),
    ]
    decision, trace = evaluate(claim, "TC004", docs, _no_fraud(), policy, reference_date=REF)

    assert decision.decision_type == DecisionType.APPROVED
    assert decision.approved_amount == pytest.approx(1350.0)   # 10% copay on 1500
    assert decision.confidence >= 0.85
    # amount breakdown must be present and correct
    assert decision.amount_breakdown is not None
    assert decision.amount_breakdown.copay_amount == pytest.approx(150.0)
    # trace must include the final decision event
    steps = [e.step_id for e in trace]
    assert "decision.final" in steps


# ── TC005: Waiting period — diabetes ─────────────────────────────────────────

def test_tc005_waiting_period_diabetes(policy):
    # EMP005 joined 2024-09-01; treatment 2024-10-15 = 44 days < 90-day diabetes wait
    claim = _claim(
        member_id="EMP005",
        treatment_date=date(2024, 10, 15),
        claimed_amount=3000,
    )
    docs = [
        _fused(DocumentType.PRESCRIPTION,
               diagnosis="Type 2 Diabetes Mellitus",
               medicines=["Metformin 500mg", "Glimepiride 1mg"],
               patient_name="Vikram Joshi"),
        _fused(DocumentType.HOSPITAL_BILL, patient_name="Vikram Joshi",
               total_amount=3000),
    ]
    decision, trace = evaluate(claim, "TC005", docs, _no_fraud(), policy,
                               reference_date=date(2024, 10, 20))

    assert decision.decision_type == DecisionType.REJECTED
    assert RejectionReason.WAITING_PERIOD in decision.rejection_reasons
    # Must state when eligibility starts
    assert decision.eligibility_date is not None
    assert "2024-11-30" in decision.eligibility_date   # 2024-09-01 + 90d
    assert "waiting_period.specific_condition" in [e.step_id for e in trace]


# ── TC006: Dental partial — cosmetic exclusion ────────────────────────────────

def test_tc006_dental_partial_cosmetic_excluded(policy):
    claim = _claim(
        member_id="EMP002",
        claim_category=ClaimCategory.DENTAL,
        treatment_date=date(2024, 10, 15),
        claimed_amount=12000,
    )
    docs = [
        _fused(DocumentType.HOSPITAL_BILL,
               patient_name="Priya Singh",
               hospital_name="Smile Dental Clinic",
               total_amount=12000,
               line_items=[
                   LineItem(description="Root Canal Treatment", amount=8000),
                   LineItem(description="Teeth Whitening", amount=4000),
               ]),
    ]
    decision, trace = evaluate(claim, "TC006", docs, _no_fraud(), policy,
                               reference_date=date(2024, 10, 20))

    assert decision.decision_type == DecisionType.PARTIAL
    assert decision.approved_amount == pytest.approx(8000.0)
    # Line-item breakdown must show which item was rejected
    rejected = [li for li in decision.line_item_decisions if li.status == "REJECTED"]
    approved = [li for li in decision.line_item_decisions if li.status == "APPROVED"]
    assert len(rejected) == 1
    assert "Teeth Whitening" in rejected[0].description
    assert len(approved) == 1
    assert "Root Canal" in approved[0].description
    assert rejected[0].reason is not None  # reason must be present


# ── TC007: MRI without pre-authorization ─────────────────────────────────────

def test_tc007_mri_no_pre_auth(policy):
    claim = _claim(
        member_id="EMP007",
        claim_category=ClaimCategory.DIAGNOSTIC,
        treatment_date=date(2024, 11, 2),
        claimed_amount=15000,
    )
    docs = [
        _fused(DocumentType.PRESCRIPTION,
               diagnosis="Lumbar Disc Herniation",
               tests_ordered=["MRI Lumbar Spine"]),
        _fused(DocumentType.LAB_REPORT, document_type=DocumentType.LAB_REPORT,
               test_results={"MRI Lumbar Spine": "herniation at L4-L5"}),
        _fused(DocumentType.HOSPITAL_BILL,
               total_amount=15000,
               line_items=[LineItem(description="MRI Lumbar Spine", amount=15000)]),
    ]
    decision, trace = evaluate(claim, "TC007", docs, _no_fraud(), policy,
                               reference_date=date(2024, 11, 5))

    assert decision.decision_type == DecisionType.REJECTED
    assert RejectionReason.PRE_AUTH_MISSING in decision.rejection_reasons
    # Explanation must tell member what to do next
    assert "pre-authorization" in decision.explanation.lower()
    assert "resubmit" in decision.explanation.lower() or "obtain" in decision.explanation.lower()


# ── TC008: Per-claim limit exceeded ──────────────────────────────────────────

def test_tc008_per_claim_limit_exceeded(policy):
    claim = _claim(
        member_id="EMP003",
        treatment_date=date(2024, 10, 20),
        claimed_amount=7500,
    )
    docs = [
        _fused(DocumentType.PRESCRIPTION, diagnosis="Gastroenteritis"),
        _fused(DocumentType.HOSPITAL_BILL, total_amount=7500,
               line_items=[LineItem(description="Consultation", amount=2000),
                           LineItem(description="Medicines", amount=5500)]),
    ]
    decision, trace = evaluate(claim, "TC008", docs, _no_fraud(), policy,
                               reference_date=date(2024, 10, 25))

    assert decision.decision_type == DecisionType.REJECTED
    assert RejectionReason.PER_CLAIM_EXCEEDED in decision.rejection_reasons
    # Must name both the limit and the claimed amount
    assert "5,000" in decision.explanation or "5000" in decision.explanation
    assert "7,500" in decision.explanation or "7500" in decision.explanation


# ── TC009: Fraud — multiple same-day claims → manual review ──────────────────

def test_tc009_fraud_same_day_manual_review(policy):
    claim = _claim(
        member_id="EMP008",
        treatment_date=date(2024, 10, 30),
        claimed_amount=4800,
    )
    docs = [
        _fused(DocumentType.PRESCRIPTION, diagnosis="Migraine"),
        _fused(DocumentType.HOSPITAL_BILL, total_amount=4800),
    ]
    fraud = _force_fraud(flags=[
        "4 claims on same day (limit: 2)",
        "Multiple providers on same day",
    ])
    decision, trace = evaluate(claim, "TC009", docs, fraud, policy,
                               reference_date=date(2024, 11, 1))

    assert decision.decision_type == DecisionType.MANUAL_REVIEW
    assert len(decision.fraud_flags) > 0
    assert "fraud.overlay" in [e.step_id for e in trace]


# ── TC010: Network hospital — discount applied before copay ──────────────────

def test_tc010_network_hospital_discount_order(policy):
    claim = _claim(
        member_id="EMP010",
        treatment_date=date(2024, 11, 3),
        claimed_amount=4500,
        hospital_name="Apollo Hospitals",
    )
    docs = [
        _fused(DocumentType.PRESCRIPTION,
               diagnosis="Acute Bronchitis", patient_name="Deepak Shah"),
        _fused(DocumentType.HOSPITAL_BILL,
               hospital_name="Apollo Hospitals",
               patient_name="Deepak Shah", total_amount=4500,
               line_items=[LineItem(description="Consultation Fee", amount=1500),
                           LineItem(description="Medicines", amount=3000)]),
    ]
    decision, trace = evaluate(claim, "TC010", docs, _no_fraud(), policy,
                               reference_date=date(2024, 11, 5))

    assert decision.decision_type == DecisionType.APPROVED
    assert decision.approved_amount == pytest.approx(3240.0)
    bd = decision.amount_breakdown
    assert bd is not None
    # Discount applied first: 4500 * 0.80 = 3600
    assert bd.after_network_discount == pytest.approx(3600.0)
    # Copay applied on discounted amount: 3600 * 0.90 = 3240
    assert bd.after_copay == pytest.approx(3240.0)
    assert bd.network_discount_percent == 20.0
    assert bd.copay_percent == 10.0


# ── TC012: Excluded condition (bariatric / obesity) ───────────────────────────

def test_tc012_excluded_condition_bariatric(policy):
    claim = _claim(
        member_id="EMP009",
        treatment_date=date(2024, 10, 18),
        claimed_amount=8000,
    )
    docs = [
        _fused(DocumentType.PRESCRIPTION,
               diagnosis="Morbid Obesity – BMI 37",
               medicines=[],
               patient_name="Anita Desai"),
        _fused(DocumentType.HOSPITAL_BILL, total_amount=8000,
               line_items=[
                   LineItem(description="Bariatric Consultation", amount=3000),
                   LineItem(description="Personalised Diet and Nutrition Program", amount=5000),
               ]),
    ]
    decision, trace = evaluate(claim, "TC012", docs, _no_fraud(), policy,
                               reference_date=date(2024, 10, 22))

    assert decision.decision_type == DecisionType.REJECTED
    assert RejectionReason.EXCLUDED_CONDITION in decision.rejection_reasons
    assert decision.confidence >= 0.90


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_member_not_found(policy):
    claim = _claim(member_id="INVALID_999")
    decision, trace = evaluate(claim, "EDGE01", [], _no_fraud(), policy, reference_date=REF)
    assert decision.decision_type == DecisionType.REJECTED
    assert RejectionReason.MEMBER_NOT_FOUND in decision.rejection_reasons


def test_below_minimum_amount(policy):
    claim = _claim(claimed_amount=100)  # min is 500
    decision, _ = evaluate(claim, "EDGE02", [], _no_fraud(), policy, reference_date=REF)
    assert decision.decision_type == DecisionType.REJECTED
    assert RejectionReason.BELOW_MINIMUM_AMOUNT in decision.rejection_reasons


def test_initial_waiting_period(policy):
    # EMP005 joined 2024-09-01; treatment 2024-09-10 = 9 days < 30-day initial wait
    claim = _claim(member_id="EMP005", treatment_date=date(2024, 9, 10), claimed_amount=1000)
    decision, trace = evaluate(claim, "EDGE03", [], _no_fraud(), policy,
                               reference_date=date(2024, 9, 15))
    assert decision.decision_type == DecisionType.REJECTED
    assert RejectionReason.WAITING_PERIOD in decision.rejection_reasons
    assert "2024-10-01" in decision.eligibility_date  # 2024-09-01 + 30d


def test_policy_inactive_date(policy):
    # treatment before policy start date
    claim = _claim(treatment_date=date(2023, 1, 1), claimed_amount=1000)
    decision, _ = evaluate(claim, "EDGE04", [], _no_fraud(), policy,
                           reference_date=date(2023, 1, 5))
    assert decision.decision_type == DecisionType.REJECTED
    assert RejectionReason.POLICY_INACTIVE in decision.rejection_reasons


def test_submission_deadline_exceeded(policy):
    # REF is 90 days after treatment → exceeds 30-day deadline
    claim = _claim(treatment_date=date(2024, 11, 1), claimed_amount=1000)
    decision, _ = evaluate(claim, "EDGE05", [], _no_fraud(), policy,
                           reference_date=date(2025, 2, 1))
    assert decision.decision_type == DecisionType.REJECTED
    assert RejectionReason.SUBMISSION_DEADLINE_MISSED in decision.rejection_reasons


def test_trace_has_all_key_steps_for_approved_claim(policy):
    claim = _claim(claimed_amount=1500, treatment_date=date(2024, 11, 1))
    docs = [_fused(DocumentType.PRESCRIPTION, diagnosis="Viral Fever")]
    decision, trace = evaluate(claim, "TRACE01", docs, _no_fraud(), policy, reference_date=REF)

    step_ids = [e.step_id for e in trace]
    for expected_step in [
        "eligibility.member_lookup",
        "eligibility.policy_active",
        "eligibility.submission_deadline",
        "eligibility.minimum_amount",
        "eligibility.per_claim_limit",
        "coverage.category_check",
        "coverage.exclusion_check",
        "waiting_period.initial",
        "decision.final",
    ]:
        assert expected_step in step_ids, f"Missing trace step: {expected_step}"
