"""
ExtractionAgent — turns document files into structured FusedDoc objects.

Extraction priority per document:
  1. Inline content dict  (test stubs / pre-parsed inputs)  ← no API call
  2. patient_name_on_doc shortcut (TC003-style test inputs)
  3. GeminiVisionProvider  (file_path set + API key present)
  4. Degraded stub          (simulate_component_failure or no key/file)

After extraction, cross-checks patient names across all documents.
A mismatch halts the pipeline with a message naming both patients.

Publishes every TraceEvent to the event bus for live SSE streaming.
"""
import logging
import time
from pathlib import Path

from app.models.graph_state import GraphState

logger = logging.getLogger(__name__)
from app.models.document import ExtractedDoc, FusedDoc, DocumentType, LineItem
from app.models.trace import TraceEvent, TraceStatus
from app.models.claim import DocumentRef
from app.db.bus import event_bus


def _make_event(claim_id: str, step_id: str, status: TraceStatus,
                detail: str = "", confidence: float | None = None,
                error: str | None = None) -> TraceEvent:
    return TraceEvent(
        claim_id=claim_id, step_id=step_id, agent="ExtractionAgent",
        status=status, detail=detail, confidence=confidence, error=error,
    )


def _content_to_extracted(file_id: str, dtype: DocumentType, content: dict) -> ExtractedDoc:
    line_items = [
        LineItem(description=item["description"], amount=float(item["amount"]))
        for item in content.get("line_items", [])
    ]
    return ExtractedDoc(
        file_id=file_id,
        document_type=dtype,
        patient_name=content.get("patient_name"),
        date=content.get("date"),
        doctor_name=content.get("doctor_name"),
        doctor_registration=content.get("doctor_registration"),
        diagnosis=content.get("diagnosis"),
        medicines=content.get("medicines", []),
        tests_ordered=content.get("tests_ordered", []),
        hospital_name=content.get("hospital_name"),
        line_items=line_items,
        total_amount=float(content["total"]) if "total" in content else None,
        extraction_method="content_stub",
        overall_confidence=0.95,
    )


def _extracted_to_fused(ex: ExtractedDoc) -> FusedDoc:
    return FusedDoc(
        file_id=ex.file_id,
        document_type=ex.document_type,
        patient_name=ex.patient_name,
        date=ex.date,
        doctor_name=ex.doctor_name,
        doctor_registration=ex.doctor_registration,
        diagnosis=ex.diagnosis,
        medicines=ex.medicines,
        tests_ordered=ex.tests_ordered,
        hospital_name=ex.hospital_name,
        line_items=ex.line_items,
        total_amount=ex.total_amount,
        overall_confidence=ex.overall_confidence,
        flags=ex.flags,
    )


async def extract_node(state: GraphState) -> dict:
    claim = state["claim"]
    claim_id = state["claim_id"]
    classified = state["classified_docs"]
    t0 = time.time()
    events: list[TraceEvent] = []
    fused_docs: list[FusedDoc] = []
    failed: list[str] = []
    confidences: list[float] = []

    doc_map: dict[str, DocumentRef] = {d.file_id: d for d in claim.documents}

    logger.info("[EXTRACT] start  claim_id=%s  docs=%d  simulate_failure=%s",
                claim_id, len(classified), claim.simulate_component_failure)

    if claim.simulate_component_failure:
        event = _make_event(
            claim_id, "extract.component_failure", TraceStatus.WARN,
            detail=(
                "Component failure simulated — extraction degraded, "
                "pipeline continues with reduced confidence."
            ),
            error="SimulatedComponentFailure",
        )
        events.append(event)
        await event_bus.publish(event)
        failed.append("ExtractionAgent(degraded)")

    for cdoc in classified:
        doc_ref = doc_map.get(cdoc.file_id)
        try:
            if doc_ref and doc_ref.content:
                extracted = _content_to_extracted(
                    cdoc.file_id, cdoc.document_type, doc_ref.content
                )

            elif doc_ref and doc_ref.patient_name_on_doc:
                # Minimal stub for TC003-style inputs (only patient name provided)
                extracted = ExtractedDoc(
                    file_id=cdoc.file_id,
                    document_type=cdoc.document_type,
                    patient_name=doc_ref.patient_name_on_doc,
                    extraction_method="patient_name_stub",
                    overall_confidence=0.85,
                )

            elif doc_ref and doc_ref.file_path and Path(doc_ref.file_path).exists():
                # Real file — call Gemini Vision
                from app.providers.gemini_vision import gemini_vision
                file_bytes = Path(doc_ref.file_path).read_bytes()
                suffix = Path(doc_ref.file_path).suffix.lower()
                mime = "application/pdf" if suffix == ".pdf" else "image/jpeg"
                extracted = await gemini_vision.extract(
                    cdoc.file_id, cdoc.document_type, file_bytes, mime
                )

            elif claim.simulate_component_failure:
                extracted = ExtractedDoc(
                    file_id=cdoc.file_id,
                    document_type=cdoc.document_type,
                    extraction_method="degraded_stub",
                    overall_confidence=0.30,
                    flags=["EXTRACTION_DEGRADED"],
                )

            else:
                extracted = ExtractedDoc(
                    file_id=cdoc.file_id,
                    document_type=cdoc.document_type,
                    extraction_method="no_content_stub",
                    overall_confidence=0.50,
                    unextracted_fields=["all_fields"],
                )

            fused = _extracted_to_fused(extracted)

            if claim.simulate_component_failure:
                fused = fused.model_copy(update={
                    "overall_confidence": min(fused.overall_confidence, 0.35),
                    "flags": list(fused.flags) + ["DEGRADED_EXTRACTION"],
                })

            fused_docs.append(fused)
            confidences.append(fused.overall_confidence)

            logger.info("[EXTRACT] '%s'  type=%s  method=%s  conf=%.2f",
                        cdoc.file_name, cdoc.document_type.value,
                        extracted.extraction_method, fused.overall_confidence)

            event = _make_event(
                claim_id, f"extract.{cdoc.file_id}", TraceStatus.PASS,
                detail=(
                    f"Extracted {cdoc.document_type.value} from '{cdoc.file_name}' "
                    f"via {extracted.extraction_method}"
                ),
                confidence=fused.overall_confidence,
            )
            events.append(event)
            await event_bus.publish(event)

        except Exception as exc:
            logger.error("[EXTRACT] FAIL  '%s'  error=%s", cdoc.file_name, exc, exc_info=True)
            failed.append(f"extract.{cdoc.file_id}")
            fused_docs.append(FusedDoc(
                file_id=cdoc.file_id,
                document_type=cdoc.document_type,
                overall_confidence=0.0,
                flags=["EXTRACTION_FAILED"],
            ))
            confidences.append(0.0)
            event = _make_event(
                claim_id, f"extract.{cdoc.file_id}", TraceStatus.FAIL,
                detail=f"Extraction failed for '{cdoc.file_name}'",
                error=str(exc),
            )
            events.append(event)
            await event_bus.publish(event)

    # ── Patient-name consistency check ────────────────────────────────────
    named_docs = [(f, f.patient_name) for f in fused_docs if f.patient_name]
    unique_names = {name for _, name in named_docs}

    if len(unique_names) > 1:
        name_details = "; ".join(
            f"'{f.file_id}' ({f.document_type.value}): '{name}'"
            for f, name in named_docs
        )
        msg = (
            f"The uploaded documents belong to different patients. "
            f"Patient names found: {name_details}. "
            f"All documents in a single claim must belong to the same patient. "
            f"Please re-upload the correct documents and resubmit."
        )
        event = _make_event(claim_id, "extract.patient_check", TraceStatus.FAIL,
                            detail=f"Patient name mismatch: {sorted(unique_names)}")
        events.append(event)
        await event_bus.publish(event)
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return {
            "fused_docs": fused_docs,
            "halt": True,
            "halt_message": msg,
            "extraction_confidence": avg_conf,
            "failed_components": failed,
            "trace": events,
        }

    event = _make_event(
        claim_id, "extract.patient_check", TraceStatus.PASS,
        detail=f"Patient name consistent: {list(unique_names) or ['(not extracted)']}",
    )
    events.append(event)
    await event_bus.publish(event)

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    elapsed = int((time.time() - t0) * 1000)
    events[-1] = events[-1].model_copy(update={"duration_ms": elapsed})

    logger.info("[EXTRACT] done  claim_id=%s  avg_conf=%.2f  failed=%s  duration=%dms",
                claim_id, avg_conf, failed or "none", elapsed)
    return {
        "fused_docs": fused_docs,
        "halt": False,
        "extraction_confidence": avg_conf,
        "failed_components": failed,
        "trace": events,
    }
