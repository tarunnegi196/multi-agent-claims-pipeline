"""
Integration tests for the full LangGraph claims pipeline.

Each test mirrors an assignment test case. Extraction is stubbed via the
DocumentRef.content and DocumentRef.actual_type fields — no Gemini call
is made, making tests fast and deterministic.

asyncio_mode = auto (pytest.ini) — no @pytest.mark.asyncio needed.
"""
import pytest
from datetime import date

from app.models.claim import ClaimSubmission, ClaimCategory, DocumentRef, ClaimHistory
from app.models.decision import DecisionType
from app.graph import claims_graph


# ── Helpers ─────────────────────────────────────────────────────────────────

def _initial_state(claim: ClaimSubmission) -> dict:
    import uuid
    return {
        "claim": claim,
        "claim_id": str(uuid.uuid4()),
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
        "halt": False,
        "halt_message": None,
    }


def _ref(file_id: str, file_name: str, actual_type: str,
         content: dict | None = None, quality: str | None = None,
         patient_name_on_doc: str | None = None) -> DocumentRef:
    return DocumentRef(
        file_id=file_id,
        file_name=file_name,
        actual_type=actual_type,
        content=content,
        quality=quality,
        patient_name_on_doc=patient_name_on_doc,
    )


# ── TC001: Wrong document uploaded ──────────────────────────────────────────

async def test_tc001_wrong_document_halts_at_verifier():
    """Two prescriptions for a CONSULTATION claim — HOSPITAL_BILL is missing."""
    claim = ClaimSubmission(
        member_id="EMP001",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory.CONSULTATION,
        treatment_date=date(2024, 11, 1),
        claimed_amount=1500,
        documents=[
            _ref("F001", "dr_sharma_prescription.jpg", "PRESCRIPTION"),
            _ref("F002", "another_prescription.jpg", "PRESCRIPTION"),
        ],
    )
    result = await claims_graph.ainvoke(_initial_state(claim))

    assert result["halt"] is True
    assert result["decision"] is None
    assert result["verification_ok"] is False

    msg = result["halt_message"]
    assert msg is not None
    assert "HOSPITAL_BILL" in msg
    assert "PRESCRIPTION" in msg
    # Message must name what was uploaded and what is missing
    assert "Missing" in msg or "missing" in msg


# ── TC002: Unreadable document ───────────────────────────────────────────────

async def test_tc002_unreadable_document_halts_with_reupload_message():
    """PHARMACY claim with a blurry pharmacy bill — must halt, not outright reject."""
    claim = ClaimSubmission(
        member_id="EMP004",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory.PHARMACY,
        treatment_date=date(2024, 10, 25),
        claimed_amount=800,
        documents=[
            _ref("F003", "prescription.jpg", "PRESCRIPTION", quality="GOOD"),
            _ref("F004", "blurry_bill.jpg", "PHARMACY_BILL", quality="UNREADABLE"),
        ],
    )
    result = await claims_graph.ainvoke(_initial_state(claim))

    assert result["halt"] is True
    assert result["decision"] is None

    msg = result["halt_message"]
    assert msg is not None
    # Must tell the member to re-upload (not just "rejected")
    assert "re-upload" in msg.lower() or "resubmit" in msg.lower()
    assert "blurry_bill.jpg" in msg


# ── TC003: Documents belong to different patients ────────────────────────────

async def test_tc003_different_patients_halts_with_names():
    """Prescription for Rajesh, bill for Arjun — mismatch must be named."""
    claim = ClaimSubmission(
        member_id="EMP001",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory.CONSULTATION,
        treatment_date=date(2024, 11, 1),
        claimed_amount=1500,
        documents=[
            _ref("F005", "prescription_rajesh.jpg", "PRESCRIPTION",
                 patient_name_on_doc="Rajesh Kumar"),
            _ref("F006", "bill_arjun.jpg", "HOSPITAL_BILL",
                 patient_name_on_doc="Arjun Mehta"),
        ],
    )
    result = await claims_graph.ainvoke(_initial_state(claim))

    assert result["halt"] is True
    assert result["decision"] is None

    msg = result["halt_message"]
    assert msg is not None
    assert "Rajesh Kumar" in msg
    assert "Arjun Mehta" in msg


# ── TC004: Clean consultation — full approval ────────────────────────────────

async def test_tc004_clean_consultation_approved():
    """All valid — expect APPROVED at ₹1350 (10% copay on ₹1500)."""
    claim = ClaimSubmission(
        member_id="EMP001",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory.CONSULTATION,
        treatment_date=date(2024, 11, 1),
        claimed_amount=1500,
        ytd_claims_amount=5000,
        documents=[
            _ref("F007", "prescription.jpg", "PRESCRIPTION", content={
                "doctor_name": "Dr. Arun Sharma",
                "doctor_registration": "KA/45678/2015",
                "patient_name": "Rajesh Kumar",
                "date": "2024-11-01",
                "diagnosis": "Viral Fever",
                "medicines": ["Paracetamol 650mg", "Vitamin C 500mg"],
            }),
            _ref("F008", "hospital_bill.jpg", "HOSPITAL_BILL", content={
                "hospital_name": "City Clinic, Bengaluru",
                "patient_name": "Rajesh Kumar",
                "date": "2024-11-01",
                "line_items": [
                    {"description": "Consultation Fee", "amount": 1000},
                    {"description": "CBC Test", "amount": 300},
                    {"description": "Dengue NS1 Test", "amount": 200},
                ],
                "total": 1500,
            }),
        ],
    )
    result = await claims_graph.ainvoke(_initial_state(claim))

    assert result["halt"] is False
    decision = result["decision"]
    assert decision is not None
    assert decision.decision_type == DecisionType.APPROVED
    assert abs(decision.approved_amount - 1350.0) < 1.0  # 10% copay
    assert decision.confidence >= 0.85
    assert len(result["trace"]) > 0


# ── TC005: Waiting period — diabetes ────────────────────────────────────────

async def test_tc005_waiting_period_diabetes_rejected():
    """EMP005 joined 2024-09-01; diabetes claim on 2024-10-15 = 44 days < 90 wait."""
    claim = ClaimSubmission(
        member_id="EMP005",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory.CONSULTATION,
        treatment_date=date(2024, 10, 15),
        claimed_amount=3000,
        documents=[
            _ref("F009", "prescription.jpg", "PRESCRIPTION", content={
                "doctor_name": "Dr. Sunil Mehta",
                "doctor_registration": "GJ/56789/2014",
                "patient_name": "Vikram Joshi",
                "diagnosis": "Type 2 Diabetes Mellitus",
                "medicines": ["Metformin 500mg", "Glimepiride 1mg"],
            }),
            _ref("F010", "bill.jpg", "HOSPITAL_BILL", content={
                "patient_name": "Vikram Joshi",
                "date": "2024-10-15",
                "total": 3000,
            }),
        ],
    )
    result = await claims_graph.ainvoke(_initial_state(claim))

    assert result["halt"] is False
    decision = result["decision"]
    assert decision is not None
    assert decision.decision_type == DecisionType.REJECTED
    reasons = [r.value for r in decision.rejection_reasons]
    assert "WAITING_PERIOD" in reasons
    # Eligibility date must be in explanation
    assert decision.eligibility_date is not None or "eligible" in decision.explanation.lower()


# ── TC006: Dental partial approval ──────────────────────────────────────────

async def test_tc006_dental_partial_cosmetic_excluded():
    """Root canal approved; teeth whitening excluded — expect PARTIAL at ₹8000."""
    claim = ClaimSubmission(
        member_id="EMP002",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory.DENTAL,
        treatment_date=date(2024, 10, 15),
        claimed_amount=12000,
        documents=[
            _ref("F011", "dental_bill.jpg", "HOSPITAL_BILL", content={
                "hospital_name": "Smile Dental Clinic",
                "patient_name": "Priya Singh",
                "line_items": [
                    {"description": "Root Canal Treatment", "amount": 8000},
                    {"description": "Teeth Whitening", "amount": 4000},
                ],
                "total": 12000,
            }),
        ],
    )
    result = await claims_graph.ainvoke(_initial_state(claim))

    assert result["halt"] is False
    decision = result["decision"]
    assert decision is not None
    assert decision.decision_type == DecisionType.PARTIAL
    assert abs(decision.approved_amount - 8000.0) < 1.0
    # Line-item decisions must be present
    assert len(decision.line_item_decisions) >= 2
    statuses = {li.description: li.status for li in decision.line_item_decisions}
    assert statuses.get("Root Canal Treatment") == "APPROVED"
    assert statuses.get("Teeth Whitening") == "REJECTED"


# ── TC007: MRI without pre-authorization ────────────────────────────────────

async def test_tc007_mri_without_preauth_rejected():
    """MRI at ₹15000 (> ₹10K threshold) without pre-auth — must REJECT."""
    claim = ClaimSubmission(
        member_id="EMP007",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory.DIAGNOSTIC,
        treatment_date=date(2024, 11, 2),
        claimed_amount=15000,
        documents=[
            _ref("F012", "prescription.jpg", "PRESCRIPTION", content={
                "doctor_name": "Dr. Venkat Rao",
                "doctor_registration": "AP/67890/2017",
                "diagnosis": "Suspected Lumbar Disc Herniation",
                "tests_ordered": ["MRI Lumbar Spine"],
            }),
            _ref("F013", "lab_report.jpg", "LAB_REPORT", content={
                "patient_name": "Suresh Patil",
            }),
            _ref("F014", "bill.jpg", "HOSPITAL_BILL", content={
                "patient_name": "Suresh Patil",
                "line_items": [{"description": "MRI Lumbar Spine", "amount": 15000}],
                "total": 15000,
            }),
        ],
    )
    result = await claims_graph.ainvoke(_initial_state(claim))

    assert result["halt"] is False
    decision = result["decision"]
    assert decision is not None
    assert decision.decision_type == DecisionType.REJECTED
    reasons = [r.value for r in decision.rejection_reasons]
    assert "PRE_AUTH_MISSING" in reasons


# ── TC009: Fraud signal — multiple same-day claims ───────────────────────────

async def test_tc009_fraud_same_day_routes_to_manual_review():
    """3 prior same-day claims (limit=2) — must be MANUAL_REVIEW, not rejected."""
    claim = ClaimSubmission(
        member_id="EMP008",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory.CONSULTATION,
        treatment_date=date(2024, 10, 30),
        claimed_amount=4800,
        claims_history=[
            ClaimHistory(claim_id="CLM_0081", date=date(2024, 10, 30),
                         amount=1200, provider="City Clinic A"),
            ClaimHistory(claim_id="CLM_0082", date=date(2024, 10, 30),
                         amount=1800, provider="City Clinic B"),
            ClaimHistory(claim_id="CLM_0083", date=date(2024, 10, 30),
                         amount=2100, provider="Wellness Center"),
        ],
        documents=[
            _ref("F017", "prescription.jpg", "PRESCRIPTION", content={
                "patient_name": "Ravi Menon",
                "diagnosis": "Migraine",
                "doctor_name": "Dr. S. Khan",
            }),
            _ref("F018", "bill.jpg", "HOSPITAL_BILL", content={
                "patient_name": "Ravi Menon",
                "total": 4800,
            }),
        ],
    )
    result = await claims_graph.ainvoke(_initial_state(claim))

    assert result["halt"] is False
    decision = result["decision"]
    assert decision is not None
    assert decision.decision_type == DecisionType.MANUAL_REVIEW
    # Fraud flags must be visible
    fraud = result.get("fraud_result")
    assert fraud is not None
    assert fraud.force_manual_review is True
    assert any("SAME_DAY" in f for f in fraud.flags)


# ── TC010: Network hospital discount applied correctly ───────────────────────

async def test_tc010_network_hospital_discount_order():
    """Apollo Hospitals: 20% discount first, then 10% copay. Final = ₹3240."""
    claim = ClaimSubmission(
        member_id="EMP010",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory.CONSULTATION,
        treatment_date=date(2024, 11, 3),
        claimed_amount=4500,
        hospital_name="Apollo Hospitals",
        ytd_claims_amount=8000,
        documents=[
            _ref("F019", "prescription.jpg", "PRESCRIPTION", content={
                "doctor_name": "Dr. S. Iyer",
                "doctor_registration": "TN/56789/2013",
                "patient_name": "Deepak Shah",
                "diagnosis": "Acute Bronchitis",
                "medicines": ["Amoxicillin 500mg", "Salbutamol Inhaler"],
            }),
            _ref("F020", "bill.jpg", "HOSPITAL_BILL", content={
                "hospital_name": "Apollo Hospitals",
                "patient_name": "Deepak Shah",
                "line_items": [
                    {"description": "Consultation Fee", "amount": 1500},
                    {"description": "Medicines", "amount": 3000},
                ],
                "total": 4500,
            }),
        ],
    )
    result = await claims_graph.ainvoke(_initial_state(claim))

    assert result["halt"] is False
    decision = result["decision"]
    assert decision is not None
    assert decision.decision_type == DecisionType.APPROVED
    assert abs(decision.approved_amount - 3240.0) < 1.0  # 4500 * 0.8 * 0.9
    bd = decision.amount_breakdown
    assert bd is not None
    assert abs(bd.network_discount_amount - 900.0) < 1.0
    assert abs(bd.copay_amount - 360.0) < 1.0


# ── TC011: Component failure — graceful degradation ──────────────────────────

async def test_tc011_component_failure_degrades_not_crashes():
    """Simulated failure: pipeline must complete, confidence drops, no crash."""
    claim = ClaimSubmission(
        member_id="EMP006",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory.ALTERNATIVE_MEDICINE,
        treatment_date=date(2024, 10, 28),
        claimed_amount=4000,
        simulate_component_failure=True,
        documents=[
            _ref("F021", "prescription.jpg", "PRESCRIPTION", content={
                "doctor_name": "Vaidya T. Krishnan",
                "doctor_registration": "AYUR/KL/2345/2019",
                "patient_name": "Kavita Nair",
                "diagnosis": "Chronic Joint Pain",
                "treatment": "Panchakarma Therapy",
            }),
            _ref("F022", "bill.jpg", "HOSPITAL_BILL", content={
                "hospital_name": "Ayur Wellness Centre",
                "patient_name": "Kavita Nair",
                "line_items": [
                    {"description": "Panchakarma Therapy (5 sessions)", "amount": 3000},
                    {"description": "Consultation", "amount": 1000},
                ],
                "total": 4000,
            }),
        ],
    )
    result = await claims_graph.ainvoke(_initial_state(claim))

    # Must not crash
    assert result["halt"] is False
    decision = result["decision"]
    assert decision is not None
    # Component failure must be visible
    assert len(result.get("failed_components", [])) > 0 or len(decision.component_failures) > 0
    # Confidence must be lower than a clean run (normal would be ~0.9+)
    assert decision.confidence < 0.85
    # Pipeline completed (got a decision)
    assert decision.decision_type in (DecisionType.APPROVED, DecisionType.MANUAL_REVIEW)


# ── TC012: Excluded treatment — obesity/bariatric ────────────────────────────

async def test_tc012_excluded_treatment_rejected():
    """Bariatric consultation + diet plan — both excluded under policy."""
    claim = ClaimSubmission(
        member_id="EMP009",
        policy_id="PLUM_GHI_2024",
        claim_category=ClaimCategory.CONSULTATION,
        treatment_date=date(2024, 10, 18),
        claimed_amount=8000,
        documents=[
            _ref("F023", "prescription.jpg", "PRESCRIPTION", content={
                "doctor_name": "Dr. P. Banerjee",
                "doctor_registration": "WB/34567/2015",
                "patient_name": "Anita Desai",
                "diagnosis": "Morbid Obesity — BMI 37",
                "treatment": "Bariatric Consultation and Customised Diet Plan",
            }),
            _ref("F024", "bill.jpg", "HOSPITAL_BILL", content={
                "patient_name": "Anita Desai",
                "line_items": [
                    {"description": "Bariatric Consultation", "amount": 3000},
                    {"description": "Personalised Diet and Nutrition Program", "amount": 5000},
                ],
                "total": 8000,
            }),
        ],
    )
    result = await claims_graph.ainvoke(_initial_state(claim))

    assert result["halt"] is False
    decision = result["decision"]
    assert decision is not None
    assert decision.decision_type == DecisionType.REJECTED
    reasons = [r.value for r in decision.rejection_reasons]
    assert "EXCLUDED_CONDITION" in reasons or "EXCLUDED_PROCEDURE" in reasons
    assert decision.confidence >= 0.90
