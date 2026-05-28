import pathlib
from contextlib import asynccontextmanager

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    claim_id            TEXT PRIMARY KEY,
    member_id           TEXT NOT NULL,
    policy_id           TEXT NOT NULL,
    claim_category      TEXT NOT NULL,
    treatment_date      TEXT NOT NULL,
    claimed_amount      REAL NOT NULL,
    decision_type       TEXT,
    approved_amount     REAL,
    confidence          REAL,
    decision_json       TEXT,
    pipeline_complete   INTEGER DEFAULT 1,
    degraded_components TEXT,
    processing_time_ms  INTEGER,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS trace_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id        TEXT NOT NULL,
    step_id         TEXT NOT NULL,
    agent           TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    status          TEXT NOT NULL,
    input_summary   TEXT,
    output_summary  TEXT,
    confidence      REAL,
    rule_reference  TEXT,
    detail          TEXT,
    duration_ms     INTEGER,
    error           TEXT
);

CREATE INDEX IF NOT EXISTS idx_trace_claim ON trace_events(claim_id);
"""


async def init_db(db_path: str) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


@asynccontextmanager
async def get_db(db_path: str):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        yield db
