"""
Eval runner — executes all 12 assignment test cases through the claims pipeline
and produces a structured report.

Usage:
    cd backend
    python -m eval.runner                    # prints report + saves eval_report.json
    python -m eval.runner --case TC004       # run a single case
    python -m eval.runner --json             # machine-readable JSON only

The runner uses DocumentRef content stubs (no Gemini calls), so results are
deterministic and fast. Real-document testing is done via the API with actual
uploaded files.
"""
import argparse
import asyncio
import json
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any

# Resolve project root so runner works from any CWD
_BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

from app.graph import claims_graph
from app.models.claim import (
    ClaimCategory,
    ClaimHistory,
    ClaimSubmission,
    DocumentRef,
)
from app.models.decision import DecisionType


# ── Helpers ─────────────────────────────────────────────────────────────────

def _load_test_cases() -> list[dict]:
    path = _BACKEND_DIR.parent / "data" / "test_cases.json"
    return json.loads(path.read_text(encoding="utf-8"))["test_cases"]


def _doc_ref(doc: dict) -> DocumentRef:
    return DocumentRef(
        file_id=doc["file_id"],
        file_name=doc.get("file_name", f"{doc['file_id']}.jpg"),
        actual_type=doc.get("actual_type"),
        content=doc.get("content"),
        quality=doc.get("quality"),
        patient_name_on_doc=doc.get("patient_name_on_doc"),
    )


def _build_claim(tc_input: dict) -> ClaimSubmission:
    history = [
        ClaimHistory(
            claim_id=h["claim_id"],
            date=date.fromisoformat(h["date"]),
            amount=h["amount"],
            provider=h.get("provider"),
        )
        for h in tc_input.get("claims_history", [])
    ]
    return ClaimSubmission(
        member_id=tc_input["member_id"],
        policy_id=tc_input["policy_id"],
        claim_category=ClaimCategory(tc_input["claim_category"]),
        treatment_date=date.fromisoformat(tc_input["treatment_date"]),
        claimed_amount=tc_input["claimed_amount"],
        hospital_name=tc_input.get("hospital_name"),
        ytd_claims_amount=tc_input.get("ytd_claims_amount", 0.0),
        claims_history=history,
        simulate_component_failure=tc_input.get("simulate_component_failure", False),
        documents=[_doc_ref(d) for d in tc_input["documents"]],
    )


def _initial_state(claim: ClaimSubmission, claim_id: str) -> dict:
    return {
        "claim": claim,
        "claim_id": claim_id,
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


def _check_match(result: dict, expected: dict) -> tuple[bool, str]:
    """
    Returns (matched, reason).

    For TC001–TC003 expected["decision"] is null — match when halt=True.
    For TC004–TC012 expected["decision"] is a string — match on decision type.
    """
    halt = result.get("halt", False)
    decision = result.get("decision")
    expected_decision = expected.get("decision")

    if expected_decision is None:
        # Pipeline must have halted before a formal decision
        if halt and decision is None:
            return True, "pipeline halted as expected (no decision)"
        return False, f"expected halt with no decision; got halt={halt}, decision={decision}"

    actual = decision.decision_type.value if decision else None
    if actual == expected_decision:
        # Check approved amount if specified
        if "approved_amount" in expected and decision:
            delta = abs(decision.approved_amount - expected["approved_amount"])
            if delta > 5:
                return False, (
                    f"decision matched ({actual}) but amount off: "
                    f"expected ₹{expected['approved_amount']}, got ₹{decision.approved_amount:.0f}"
                )
        return True, "decision and amount matched"

    return False, f"expected {expected_decision}, got {actual}"


# ── Core eval loop ────────────────────────────────────────────────────────────

async def run_all(cases: list[dict]) -> list[dict]:
    results = []
    for tc in cases:
        claim_id = f"EVAL-{tc['case_id']}-{uuid.uuid4().hex[:6]}"
        claim = _build_claim(tc["input"])
        state = _initial_state(claim, claim_id)

        try:
            result = await claims_graph.ainvoke(state)
        except Exception as exc:
            results.append({
                "case_id": tc["case_id"],
                "case_name": tc["case_name"],
                "error": str(exc),
                "matched": False,
                "match_reason": f"pipeline raised: {exc}",
            })
            continue

        decision = result.get("decision")
        matched, reason = _check_match(result, tc["expected"])

        entry: dict[str, Any] = {
            "case_id": tc["case_id"],
            "case_name": tc["case_name"],
            "matched": matched,
            "match_reason": reason,
            "halt": result.get("halt", False),
            "halt_message": result.get("halt_message"),
            "expected_decision": tc["expected"].get("decision"),
            "actual_decision": decision.decision_type.value if decision else None,
            "approved_amount": decision.approved_amount if decision else None,
            "confidence": decision.confidence if decision else None,
            "rejection_reasons": (
                [r.value for r in decision.rejection_reasons] if decision else []
            ),
            "fraud_flags": (
                result["fraud_result"].flags if result.get("fraud_result") else []
            ),
            "degraded_components": result.get("failed_components", []),
            "trace_steps": len(result.get("trace", [])),
            "claim_id": claim_id,
        }
        results.append(entry)

    return results


# ── Report formatting ─────────────────────────────────────────────────────────

def _print_report(results: list[dict]) -> None:
    passed = sum(1 for r in results if r.get("matched"))
    total = len(results)

    print()
    print("=" * 70)
    print(f"  EVAL REPORT — {passed}/{total} cases matched")
    print("=" * 70)

    for r in results:
        icon = "[PASS]" if r.get("matched") else "[FAIL]"
        print(f"\n{icon}  {r['case_id']}: {r['case_name']}")

        if r.get("error"):
            print(f"   ERROR: {r['error']}")
            continue

        exp = r["expected_decision"] or "(halt)"
        act = r["actual_decision"] or "(halt)"
        print(f"   Expected: {exp:<20} Actual: {act}")

        if r.get("halt"):
            msg = (r.get("halt_message") or "")[:120]
            print(f"   Halt msg: {msg}{'...' if len(r.get('halt_message','')) > 120 else ''}")
        else:
            amt = r.get("approved_amount")
            conf = r.get("confidence")
            if amt is not None:
                print(f"   Amount:   Rs.{amt:.0f}   Confidence: {conf:.2f}")
            reasons = r.get("rejection_reasons", [])
            if reasons:
                print(f"   Reasons:  {', '.join(reasons)}")
            flags = r.get("fraud_flags", [])
            if flags:
                print(f"   Fraud:    {'; '.join(flags)}")
            degraded = r.get("degraded_components", [])
            if degraded:
                print(f"   Degraded: {', '.join(degraded)}")

        print(f"   Trace:    {r.get('trace_steps', 0)} events")
        if not r.get("matched"):
            print(f"   !! MISMATCH — {r.get('match_reason')}")

    print()
    print("=" * 70)
    print(f"  RESULT: {passed}/{total} passed")
    print("=" * 70)
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

async def _main(case_filter: str | None, json_only: bool) -> None:
    all_cases = _load_test_cases()

    if case_filter:
        cases = [c for c in all_cases if c["case_id"] == case_filter.upper()]
        if not cases:
            sys.exit(f"Case '{case_filter}' not found. Valid IDs: "
                     f"{', '.join(c['case_id'] for c in all_cases)}")
    else:
        cases = all_cases

    results = await run_all(cases)

    if not json_only:
        _print_report(results)

    report_path = Path(__file__).parent / "eval_report.json"
    report_path.write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    if not json_only:
        print(f"Full report saved to {report_path}\n")
    else:
        print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run eval on all 12 test cases")
    parser.add_argument("--case", help="Run a single case by ID (e.g. TC004)")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    args = parser.parse_args()

    asyncio.run(_main(case_filter=args.case, json_only=args.json))
