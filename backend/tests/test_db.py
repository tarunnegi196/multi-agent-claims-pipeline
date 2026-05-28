"""
Integration tests for the SQLite persistence layer.
Each test gets a fresh in-memory-style temp database via tmp_path.
"""
import asyncio
import pytest
from datetime import datetime, date
from pathlib import Path

from app.db.database import init_db
from app.db.repositories import ClaimRepository, TraceRepository
from app.db.bus import TraceEventBus
from app.models.trace import TraceEvent, TraceStatus
from app.models.decision import (
    Decision, DecisionType, FinalOutput, AmountBreakdown,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "test_claims.db")
    await init_db(path)
    return path


def _make_decision() -> Decision:
    return Decision(
        decision_type=DecisionType.APPROVED,
        approved_amount=1350.0,
        claimed_amount=1500.0,
        amount_breakdown=AmountBreakdown(
            claimed=1500.0,
            copay_percent=10.0,
            copay_amount=150.0,
            after_copay=1350.0,
            final_approved=1350.0,
        ),
        rejection_reasons=[],
        confidence=0.90,
        explanation="Claim approved for ₹1,350. Co-pay (10%): ₹150 deducted.",
    )


def _make_events(claim_id: str) -> list[TraceEvent]:
    return [
        TraceEvent(
            claim_id=claim_id,
            step_id="eligibility.member_lookup",
            agent="PolicyEngine",
            timestamp=datetime.utcnow(),
            status=TraceStatus.PASS,
            detail="Member found",
            confidence=1.0,
        ),
        TraceEvent(
            claim_id=claim_id,
            step_id="decision.final",
            agent="PolicyEngine",
            timestamp=datetime.utcnow(),
            status=TraceStatus.PASS,
            detail="APPROVED ₹1350",
            confidence=0.90,
        ),
    ]


def _make_output(claim_id: str, events: list[TraceEvent]) -> FinalOutput:
    return FinalOutput(
        claim_id=claim_id,
        member_id="EMP001",
        policy_id="PLUM_GHI_2024",
        claim_category="CONSULTATION",
        treatment_date="2024-11-01",
        decision=_make_decision(),
        trace=events,
        processing_time_ms=342,
        pipeline_complete=True,
        degraded_components=[],
    )


# ── ClaimRepository tests ─────────────────────────────────────────────────────

async def test_save_and_retrieve_claim(db_path):
    repo = ClaimRepository(db_path)
    events = _make_events("CLM001")
    output = _make_output("CLM001", events)

    await TraceRepository(db_path).save_events(events)
    await repo.save(output)

    retrieved = await repo.get("CLM001")
    assert retrieved is not None
    assert retrieved.claim_id == "CLM001"
    assert retrieved.member_id == "EMP001"
    assert retrieved.decision.decision_type == DecisionType.APPROVED
    assert retrieved.decision.approved_amount == pytest.approx(1350.0)
    assert retrieved.decision.confidence == pytest.approx(0.90)


async def test_get_nonexistent_claim_returns_none(db_path):
    repo = ClaimRepository(db_path)
    result = await repo.get("DOES_NOT_EXIST")
    assert result is None


async def test_list_recent_claims(db_path):
    claim_repo = ClaimRepository(db_path)
    trace_repo = TraceRepository(db_path)

    for i in range(3):
        cid = f"CLM00{i}"
        events = _make_events(cid)
        await trace_repo.save_events(events)
        await claim_repo.save(_make_output(cid, events))

    rows = await claim_repo.list_recent(limit=10)
    assert len(rows) == 3
    assert all("claim_id" in r for r in rows)
    assert all("decision_type" in r for r in rows)


async def test_save_overwrites_on_duplicate_claim_id(db_path):
    repo = ClaimRepository(db_path)
    trace_repo = TraceRepository(db_path)

    events = _make_events("CLM_DUP")
    await trace_repo.save_events(events)
    output = _make_output("CLM_DUP", events)
    await repo.save(output)

    # Save again with different approved amount
    output.decision.approved_amount = 999.0
    output.decision.decision_type = DecisionType.PARTIAL
    await repo.save(output)

    retrieved = await repo.get("CLM_DUP")
    assert retrieved.decision.decision_type == DecisionType.PARTIAL


# ── TraceRepository tests ─────────────────────────────────────────────────────

async def test_save_and_retrieve_trace_events(db_path):
    trace_repo = TraceRepository(db_path)
    events = _make_events("CLM_TRACE")
    await trace_repo.save_events(events)

    retrieved = await trace_repo.get_events("CLM_TRACE")
    assert len(retrieved) == 2
    assert retrieved[0].step_id == "eligibility.member_lookup"
    assert retrieved[1].step_id == "decision.final"
    assert retrieved[0].status == TraceStatus.PASS


async def test_get_events_for_unknown_claim_returns_empty(db_path):
    trace_repo = TraceRepository(db_path)
    events = await trace_repo.get_events("NO_SUCH_CLAIM")
    assert events == []


async def test_save_events_noop_on_empty_list(db_path):
    # Should not raise
    await TraceRepository(db_path).save_events([])


# ── TraceEventBus tests ───────────────────────────────────────────────────────

async def test_bus_publishes_to_subscriber():
    bus = TraceEventBus()
    q = bus.subscribe("CLM_BUS")

    event = TraceEvent(
        claim_id="CLM_BUS", step_id="test.step", agent="TestAgent",
        timestamp=datetime.utcnow(), status=TraceStatus.PASS, detail="ok",
    )
    await bus.publish(event)

    received = await asyncio.wait_for(q.get(), timeout=1.0)
    assert received.step_id == "test.step"


async def test_bus_close_stream_sends_sentinel():
    bus = TraceEventBus()
    q = bus.subscribe("CLM_DONE")
    await bus.close_stream("CLM_DONE")

    item = await asyncio.wait_for(q.get(), timeout=1.0)
    assert bus.is_done(item)


async def test_bus_unsubscribe_stops_delivery():
    bus = TraceEventBus()
    q = bus.subscribe("CLM_UNSUB")
    bus.unsubscribe("CLM_UNSUB", q)

    event = TraceEvent(
        claim_id="CLM_UNSUB", step_id="x", agent="A",
        timestamp=datetime.utcnow(), status=TraceStatus.PASS,
    )
    await bus.publish(event)
    assert q.empty()
