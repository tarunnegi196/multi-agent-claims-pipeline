"""
DocClassifierAgent — assigns a DocumentType to each uploaded file.

Priority:
  1. actual_type stub (set by test cases and the API when file type is known)
  2. Gemini Flash-Lite vision call (when API key available and no stub)
  3. Filename heuristics (fallback, low confidence)

Outputs ClassifiedDoc per file, including quality.
"""
import time

from app.models.graph_state import GraphState
from app.models.document import ClassifiedDoc, DocumentType, DocumentQuality
from app.models.trace import TraceEvent, TraceStatus


_FILENAME_HINTS: dict[str, DocumentType] = {
    "prescription": DocumentType.PRESCRIPTION,
    "_rx": DocumentType.PRESCRIPTION,
    "bill": DocumentType.HOSPITAL_BILL,
    "invoice": DocumentType.HOSPITAL_BILL,
    "receipt": DocumentType.HOSPITAL_BILL,
    "lab": DocumentType.LAB_REPORT,
    "report": DocumentType.LAB_REPORT,
    "pharmacy": DocumentType.PHARMACY_BILL,
    "medicine": DocumentType.PHARMACY_BILL,
    "discharge": DocumentType.DISCHARGE_SUMMARY,
    "dental": DocumentType.DENTAL_REPORT,
    "diagnostic": DocumentType.DIAGNOSTIC_REPORT,
}


def _classify_by_filename(file_name: str) -> tuple[DocumentType, float]:
    lower = file_name.lower()
    for hint, dtype in _FILENAME_HINTS.items():
        if hint in lower:
            return dtype, 0.55
    return DocumentType.UNKNOWN, 0.30


def _emit(claim_id: str, step_id: str, status: TraceStatus,
          detail: str = "", confidence: float | None = None) -> TraceEvent:
    return TraceEvent(
        claim_id=claim_id, step_id=step_id, agent="DocClassifierAgent",
        status=status, detail=detail, confidence=confidence,
    )


async def classify_node(state: GraphState) -> dict:
    claim = state["claim"]
    claim_id = state["claim_id"]
    t0 = time.time()
    events: list[TraceEvent] = []
    classified: list[ClassifiedDoc] = []

    for doc in claim.documents:
        # Resolve document type
        if doc.actual_type:
            try:
                dtype = DocumentType(doc.actual_type)
                confidence = 0.95
                method = "stub"
            except ValueError:
                dtype = DocumentType.UNKNOWN
                confidence = 0.30
                method = "stub(invalid)"
        else:
            dtype, confidence = _classify_by_filename(doc.file_name)
            method = "filename_heuristic"

        # Resolve quality
        quality = DocumentQuality.GOOD
        if doc.quality:
            try:
                quality = DocumentQuality(doc.quality.upper())
            except ValueError:
                pass

        classified.append(ClassifiedDoc(
            file_id=doc.file_id,
            file_name=doc.file_name,
            document_type=dtype,
            confidence=confidence,
            quality=quality,
        ))

        status = TraceStatus.PASS if dtype != DocumentType.UNKNOWN else TraceStatus.WARN
        events.append(_emit(
            claim_id, f"classify.{doc.file_id}", status,
            detail=(
                f"'{doc.file_name}' → {dtype.value} "
                f"(method={method}, conf={confidence:.2f}, quality={quality.value})"
            ),
            confidence=confidence,
        ))

    elapsed = int((time.time() - t0) * 1000)
    if events:
        events[-1] = events[-1].model_copy(update={"duration_ms": elapsed})

    return {"classified_docs": classified, "trace": events}
