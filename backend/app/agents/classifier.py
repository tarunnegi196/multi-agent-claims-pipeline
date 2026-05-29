"""
DocClassifierAgent — assigns a DocumentType to each uploaded file.

Resolution priority:
  1. actual_type stub (set by test cases / API when type is already known)
  2. GeminiClassifierProvider (when file_path is set and API key is present)
  3. Filename heuristics (fallback, low confidence)

Emits one TraceEvent per document and publishes each to the event bus
for live SSE streaming.
"""
import logging
import time
from pathlib import Path

from app.models.graph_state import GraphState
from app.models.document import ClassifiedDoc, DocumentType, DocumentQuality
from app.models.trace import TraceEvent, TraceStatus
from app.db.bus import event_bus

logger = logging.getLogger(__name__)


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

    logger.info("[CLASSIFY] start  claim_id=%s  docs=%d", claim_id, len(claim.documents))

    for doc in claim.documents:
        # ── Resolve document type + quality ───────────────────────────────
        # Priority: real file (Gemini) > stub > filename heuristic.
        # When a file is on disk, Gemini always runs — stubs are only for
        # programmatic/test requests that never upload a file.
        quality = DocumentQuality.GOOD

        if doc.file_path and Path(doc.file_path).exists():
            from app.providers.gemini_classifier import gemini_classifier
            file_bytes = Path(doc.file_path).read_bytes()
            suffix = Path(doc.file_path).suffix.lower()
            _mime_map = {".pdf": "application/pdf", ".png": "image/png", ".webp": "image/webp"}
            mime = _mime_map.get(suffix, "image/jpeg")
            dtype, confidence, quality = await gemini_classifier.classify(doc.file_id, file_bytes, mime)
            method = "gemini_classifier" if gemini_classifier.is_available() else "gemini_fallback"

        elif doc.actual_type:
            try:
                dtype = DocumentType(doc.actual_type)
                confidence = 0.95
                method = "stub"
            except ValueError:
                dtype = DocumentType.UNKNOWN
                confidence = 0.30
                method = "stub(invalid)"
            # Allow explicit quality override from stub (for test cases like TC002)
            if doc.quality:
                try:
                    quality = DocumentQuality(doc.quality.upper())
                except ValueError:
                    pass

        else:
            dtype, confidence = _classify_by_filename(doc.file_name)
            method = "filename_heuristic"

        classified.append(ClassifiedDoc(
            file_id=doc.file_id,
            file_name=doc.file_name,
            document_type=dtype,
            confidence=confidence,
            quality=quality,
        ))

        logger.info("[CLASSIFY] '%s' → %s  method=%s  conf=%.2f",
                    doc.file_name, dtype.value, method, confidence)

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

    logger.info("[CLASSIFY] done  claim_id=%s  results=[%s]  duration=%dms",
                claim_id,
                ", ".join(f"{c.document_type.value}({c.confidence:.2f})" for c in classified),
                elapsed)
    return {"classified_docs": classified, "trace": events}
