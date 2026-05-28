"""
DocClassifierAgent — assigns a DocumentType to each uploaded file.

Resolution priority:
  1. actual_type stub (set by test cases / API when type is already known)
  2. GeminiClassifierProvider (when file_path is set and API key is present)
  3. Filename heuristics (fallback, low confidence)

Emits one TraceEvent per document and publishes each to the event bus
for live SSE streaming.
"""
import time
from pathlib import Path

from app.models.graph_state import GraphState
from app.models.document import ClassifiedDoc, DocumentType, DocumentQuality
from app.models.trace import TraceEvent, TraceStatus
from app.db.bus import event_bus


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


def _make_event(claim_id: str, step_id: str, status: TraceStatus,
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
        # ── Resolve document type ──────────────────────────────────────────
        if doc.actual_type:
            try:
                dtype = DocumentType(doc.actual_type)
                confidence = 0.95
                method = "stub"
            except ValueError:
                dtype = DocumentType.UNKNOWN
                confidence = 0.30
                method = "stub(invalid)"

        elif doc.file_path and Path(doc.file_path).exists():
            # Real file — use Gemini classifier
            from app.providers.gemini_classifier import gemini_classifier
            file_bytes = Path(doc.file_path).read_bytes()
            suffix = Path(doc.file_path).suffix.lower()
            mime = "application/pdf" if suffix == ".pdf" else "image/jpeg"
            dtype, confidence = await gemini_classifier.classify(doc.file_id, file_bytes, mime)
            method = "gemini_classifier" if gemini_classifier.is_available() else "gemini_fallback"

        else:
            dtype, confidence = _classify_by_filename(doc.file_name)
            method = "filename_heuristic"

        # ── Resolve quality ────────────────────────────────────────────────
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
        event = _make_event(
            claim_id, f"classify.{doc.file_id}", status,
            detail=(
                f"'{doc.file_name}' → {dtype.value} "
                f"(method={method}, conf={confidence:.2f}, quality={quality.value})"
            ),
            confidence=confidence,
        )
        events.append(event)
        await event_bus.publish(event)

    elapsed = int((time.time() - t0) * 1000)
    if events:
        events[-1] = events[-1].model_copy(update={"duration_ms": elapsed})

    return {"classified_docs": classified, "trace": events}
