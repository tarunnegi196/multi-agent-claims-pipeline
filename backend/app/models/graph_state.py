from typing import Optional, Annotated
from typing_extensions import TypedDict
import operator

from .claim import ClaimSubmission
from .document import ClassifiedDoc, FusedDoc
from .trace import TraceEvent
from .decision import Decision, FraudResult


class GraphState(TypedDict):
    """
    LangGraph state threaded through every agent node.
    Lists use operator.add so nodes append without overwriting prior entries.
    """
    # ── Input ──────────────────────────────────────────────────────────────
    claim: ClaimSubmission
    claim_id: str

    # ── Agent outputs (None = not yet run) ─────────────────────────────────
    intake_ok: Optional[bool]
    classified_docs: list[ClassifiedDoc]
    verification_ok: Optional[bool]
    verification_message: Optional[str]
    fused_docs: list[FusedDoc]
    fraud_result: Optional[FraudResult]
    decision: Optional[Decision]

    # ── Observability ───────────────────────────────────────────────────────
    trace: Annotated[list[TraceEvent], operator.add]

    # ── Failure tracking ────────────────────────────────────────────────────
    failed_components: Annotated[list[str], operator.add]
    extraction_confidence: float

    # ── Cross-document consistency (set by ConsistencyAgent) ────────────────
    consistency_flags: list[str]

    # ── Bounding-box regions per file_id (set by ExtractionAgent) ───────────
    bbox_regions: dict

    # ── Flow control ────────────────────────────────────────────────────────
    halt: bool
    halt_message: Optional[str]
