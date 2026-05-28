"""
ClaimRepository and TraceRepository.

Both accept db_path so callers (app startup vs tests) can point at different files.
Decision is stored as JSON to avoid a complex relational schema for nested objects.
TraceEvents get individual rows so the frontend can query/stream them independently.
"""
import json
from datetime import datetime

from app.models.decision import Decision, FinalOutput
from app.models.trace import TraceEvent, TraceStatus
from .database import get_db


class ClaimRepository:
    def __init__(self, db_path: str) -> None:
        self._path = db_path

    async def save(self, output: FinalOutput) -> None:
        async with get_db(self._path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO claims
                    (claim_id, member_id, policy_id, claim_category, treatment_date,
                     claimed_amount, decision_type, approved_amount, confidence,
                     decision_json, pipeline_complete, degraded_components, processing_time_ms)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    output.claim_id,
                    output.member_id,
                    output.policy_id,
                    output.claim_category,
                    output.treatment_date,
                    output.decision.claimed_amount,
                    output.decision.decision_type.value,
                    output.decision.approved_amount,
                    output.decision.confidence,
                    output.decision.model_dump_json(),
                    int(output.pipeline_complete),
                    json.dumps(output.degraded_components),
                    output.processing_time_ms,
                ),
            )
            await db.commit()

    async def get(self, claim_id: str) -> FinalOutput | None:
        async with get_db(self._path) as db:
            async with db.execute(
                "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
            ) as cur:
                row = await cur.fetchone()
            if not row:
                return None

            events = await TraceRepository(self._path).get_events(claim_id)
            decision = Decision.model_validate_json(row["decision_json"])
            return FinalOutput(
                claim_id=row["claim_id"],
                member_id=row["member_id"],
                policy_id=row["policy_id"],
                claim_category=row["claim_category"],
                treatment_date=row["treatment_date"],
                decision=decision,
                trace=events,
                pipeline_complete=bool(row["pipeline_complete"]),
                degraded_components=json.loads(row["degraded_components"] or "[]"),
                processing_time_ms=row["processing_time_ms"] or 0,
            )

    async def list_recent(self, limit: int = 50) -> list[dict]:
        async with get_db(self._path) as db:
            async with db.execute(
                """
                SELECT claim_id, member_id, claim_category, treatment_date,
                       claimed_amount, decision_type, approved_amount, confidence,
                       pipeline_complete, created_at
                FROM claims
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(r) for r in rows]


class TraceRepository:
    def __init__(self, db_path: str) -> None:
        self._path = db_path

    async def save_events(self, events: list[TraceEvent]) -> None:
        if not events:
            return
        rows = [
            (
                e.claim_id, e.step_id, e.agent,
                e.timestamp.isoformat(),
                e.status.value,
                e.input_summary, e.output_summary,
                e.confidence, e.rule_reference,
                e.detail, e.duration_ms, e.error,
            )
            for e in events
        ]
        async with get_db(self._path) as db:
            await db.executemany(
                """
                INSERT INTO trace_events
                    (claim_id, step_id, agent, timestamp, status,
                     input_summary, output_summary, confidence, rule_reference,
                     detail, duration_ms, error)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                rows,
            )
            await db.commit()

    async def get_events(self, claim_id: str) -> list[TraceEvent]:
        async with get_db(self._path) as db:
            async with db.execute(
                "SELECT * FROM trace_events WHERE claim_id = ? ORDER BY id",
                (claim_id,),
            ) as cur:
                rows = await cur.fetchall()
        return [
            TraceEvent(
                claim_id=r["claim_id"],
                step_id=r["step_id"],
                agent=r["agent"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
                status=TraceStatus(r["status"]),
                input_summary=r["input_summary"],
                output_summary=r["output_summary"],
                confidence=r["confidence"],
                rule_reference=r["rule_reference"],
                detail=r["detail"],
                duration_ms=r["duration_ms"],
                error=r["error"],
            )
            for r in rows
        ]
