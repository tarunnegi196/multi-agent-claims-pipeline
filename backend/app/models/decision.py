from enum import Enum
from typing import Optional
from pydantic import BaseModel

from .trace import TraceEvent


class DecisionType(str, Enum):
    APPROVED = "APPROVED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class RejectionReason(str, Enum):
    WAITING_PERIOD = "WAITING_PERIOD"
    PRE_AUTH_MISSING = "PRE_AUTH_MISSING"
    PER_CLAIM_EXCEEDED = "PER_CLAIM_EXCEEDED"
    ANNUAL_LIMIT_EXCEEDED = "ANNUAL_LIMIT_EXCEEDED"
    EXCLUDED_CONDITION = "EXCLUDED_CONDITION"
    EXCLUDED_PROCEDURE = "EXCLUDED_PROCEDURE"
    MEMBER_NOT_FOUND = "MEMBER_NOT_FOUND"
    POLICY_INACTIVE = "POLICY_INACTIVE"
    SUBMISSION_DEADLINE_MISSED = "SUBMISSION_DEADLINE_MISSED"
    BELOW_MINIMUM_AMOUNT = "BELOW_MINIMUM_AMOUNT"
    NOT_COVERED = "NOT_COVERED"
    DOCUMENT_MISMATCH = "DOCUMENT_MISMATCH"
    UNREADABLE_DOCUMENT = "UNREADABLE_DOCUMENT"


class LineItemDecision(BaseModel):
    description: str
    claimed_amount: float
    approved_amount: float
    status: str  # "APPROVED" | "REJECTED"
    reason: Optional[str] = None


class AmountBreakdown(BaseModel):
    claimed: float
    network_discount_percent: float = 0.0
    network_discount_amount: float = 0.0
    after_network_discount: float = 0.0
    copay_percent: float = 0.0
    copay_amount: float = 0.0
    after_copay: float = 0.0
    sub_limit_applied: Optional[float] = None
    per_claim_limit_applied: Optional[float] = None
    final_approved: float = 0.0


class FraudResult(BaseModel):
    fraud_score: float
    flags: list[str] = []
    force_manual_review: bool = False
    same_day_count: int = 0
    monthly_count: int = 0


class Decision(BaseModel):
    decision_type: DecisionType
    approved_amount: float = 0.0
    claimed_amount: float
    amount_breakdown: Optional[AmountBreakdown] = None
    line_item_decisions: list[LineItemDecision] = []
    rejection_reasons: list[RejectionReason] = []
    confidence: float
    explanation: str
    manual_review_note: Optional[str] = None
    fraud_flags: list[str] = []
    component_failures: list[str] = []
    eligibility_date: Optional[str] = None


class FinalOutput(BaseModel):
    """Top-level response returned by POST /claims and stored in SQLite."""
    claim_id: str
    member_id: str
    policy_id: str
    claim_category: str
    treatment_date: str
    decision: Decision
    trace: list[TraceEvent]
    processing_time_ms: int
    pipeline_complete: bool = True
    degraded_components: list[str] = []
