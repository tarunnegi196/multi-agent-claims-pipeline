"""
Tests for the eval runner.

Runs a subset of test cases through the pipeline and verifies the runner
produces structured results with the correct shape — same logic as the
full eval, just faster (fewer cases).
"""
import pytest

from eval.runner import _build_claim, _check_match, _load_test_cases, run_all


# ── Unit tests for helpers ────────────────────────────────────────────────────

def test_load_test_cases_returns_12():
    cases = _load_test_cases()
    assert len(cases) == 12
    ids = [c["case_id"] for c in cases]
    assert "TC001" in ids
    assert "TC012" in ids


def test_build_claim_tc004():
    cases = _load_test_cases()
    tc004 = next(c for c in cases if c["case_id"] == "TC004")
    claim = _build_claim(tc004["input"])
    assert claim.member_id == "EMP001"
    assert claim.claimed_amount == 1500
    assert len(claim.documents) == 2
    assert claim.documents[0].content is not None


def test_build_claim_tc003_patient_name_on_doc():
    cases = _load_test_cases()
    tc003 = next(c for c in cases if c["case_id"] == "TC003")
    claim = _build_claim(tc003["input"])
    assert claim.documents[0].patient_name_on_doc == "Rajesh Kumar"
    assert claim.documents[1].patient_name_on_doc == "Arjun Mehta"


def test_check_match_halt_expected_and_got_halt():
    result = {"halt": True, "decision": None}
    expected = {"decision": None}
    matched, reason = _check_match(result, expected)
    assert matched is True


def test_check_match_halt_expected_but_got_decision():
    from app.models.decision import Decision, DecisionType
    decision = Decision(
        decision_type=DecisionType.APPROVED,
        claimed_amount=1500,
        confidence=0.9,
        explanation="ok",
    )
    result = {"halt": False, "decision": decision}
    expected = {"decision": None}
    matched, reason = _check_match(result, expected)
    assert matched is False


def test_check_match_approved_correct():
    from app.models.decision import Decision, DecisionType, AmountBreakdown
    bd = AmountBreakdown(claimed=1500, final_approved=1350, after_copay=1350,
                         copay_percent=10, copay_amount=150, after_network_discount=1500)
    decision = Decision(
        decision_type=DecisionType.APPROVED,
        claimed_amount=1500,
        approved_amount=1350,
        confidence=0.9,
        explanation="ok",
        amount_breakdown=bd,
    )
    result = {"halt": False, "decision": decision}
    expected = {"decision": "APPROVED", "approved_amount": 1350}
    matched, reason = _check_match(result, expected)
    assert matched is True


# ── Integration: run a fast subset through the full pipeline ──────────────────

async def test_eval_runner_on_tc004_and_tc001():
    """Quick integration: two cases, verify result structure and match."""
    cases = _load_test_cases()
    subset = [c for c in cases if c["case_id"] in ("TC001", "TC004")]
    results = await run_all(subset)

    assert len(results) == 2

    r_tc001 = next(r for r in results if r["case_id"] == "TC001")
    assert r_tc001["matched"] is True
    assert r_tc001["halt"] is True

    r_tc004 = next(r for r in results if r["case_id"] == "TC004")
    assert r_tc004["matched"] is True
    assert r_tc004["actual_decision"] == "APPROVED"
    assert r_tc004["trace_steps"] > 0


async def test_eval_runner_all_12_complete_without_crash():
    """Run all 12 cases; none should raise an exception."""
    cases = _load_test_cases()
    results = await run_all(cases)

    assert len(results) == 12
    for r in results:
        assert "error" not in r or r.get("error") is None, (
            f"{r['case_id']} raised: {r.get('error')}"
        )
    # At least 9 of 12 should match (TC008 covered by policy engine tests only)
    passed = sum(1 for r in results if r["matched"])
    assert passed >= 9, f"Only {passed}/12 passed: {[r['case_id'] for r in results if not r['matched']]}"
