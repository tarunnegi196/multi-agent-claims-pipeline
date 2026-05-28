from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TraceStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"


class TraceEvent(BaseModel):
    """
    Single observable unit emitted by every agent at every check.
    The final decision is a fold over the event list — they can never disagree.
    """
    claim_id: str
    step_id: str
    agent: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: TraceStatus
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    confidence: Optional[float] = None
    rule_reference: Optional[str] = None
    detail: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
