"""
ExtractionAgent — turns document files into structured FusedDoc objects.

Extraction priority per document:
  1. Inline `content` dict (test stubs and pre-parsed inputs)
  2. `patient_name_on_doc` shortcut (TC003-style inputs without full content)
  3. Gemini Vision (when API key available — added in next commit)
  4. Degraded stub (simulate_component_failure or no key)

After extraction, cross-checks patient names across all documents.
A mismatch halts the pipeline with a specific message naming both patients.
"""
import time

from app.models.graph_state import GraphState
from app.models.document import ExtractedDoc, FusedDoc, DocumentType, LineItem
from app.models.trace import TraceEvent, TraceStatus
from app.models.claim import DocumentRef


def _emit(claim_id: str, step_id: str, status: TraceStatus,
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

    # Emit degradation warning early so it appears first in the trace
    if claim.simulate_component_failure:
        events.append(_emit(
            claim_id, "extract.component_failure", TraceStatus.WARN,
            detail=(
                "Component failure simulated (simulate_component_failure=true). "
                "Extraction running in degraded mode — confidence will be reduced."
            ),
            error="SimulatedComponentFailure",
        ))
        failed.append("ExtractionAgent(degraded)")

    for cdoc in classified:
        doc_ref = doc_map.get(cdoc.file_id)
        try:
            if doc_ref and doc_ref.content:
                extracted = _content_to_extracted(cdoc.file_id, cdoc.document_type, doc_ref.content)
            elif doc_ref and doc_ref.patient_name_on_doc:
                # Minimal extraction for TC003-style inputs
                extracted = ExtractedDoc(
                    file_id=cdoc.file_id,
                    document_type=cdoc.document_type,
                    patient_name=doc_ref.patient_name_on_doc,
                    extraction_method="patient_name_stub",
                    overall_confidence=0.85,
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
                # No content, no Gemini key — minimal stub
                extracted = ExtractedDoc(
                    file_id=cdoc.file_id,
                    document_type=cdoc.document_type,
                    extraction_method="no_content_stub",
                    overall_confidence=0.50,
                    unextracted_fields=["all_fields"],
                )

            fused = _extracted_to_fused(extracted)

            # Degrade confidence for simulated failures
            if claim.simulate_component_failure:
                fused = fused.model_copy(update={
                    "overall_confidence": min(fused.overall_confidence, 0.35),
                    "flags": list(fused.flags) + ["DEGRADED_EXTRACTION"],
                })

            fused_docs.append(fused)
            confidences.append(fused.overall_confidence)
            events.append(_emit(
                claim_id, f"extract.{cdoc.file_id}", TraceStatus.PASS,
                detail=(
                    f"Extracted {cdoc.document_type.value} from '{cdoc.file_name}' "
                    f"via {extracted.extraction_method}"
                ),
                confidence=fused.overall_confidence,
            ))

        except Exception as exc:
            failed.append(f"extract.{cdoc.file_id}")
            fused_docs.append(FusedDoc(
                file_id=cdoc.file_id,
                document_type=cdoc.document_type,
                overall_confidence=0.0,
                flags=["EXTRACTION_FAILED"],
            ))
            confidences.append(0.0)
            events.append(_emit(
                claim_id, f"extract.{cdoc.file_id}", TraceStatus.FAIL,
                detail=f"Extraction failed for '{cdoc.file_name}'",
                error=str(exc),
            ))

    # ── Patient-name consistency check ───────────────────────────────────────
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
        events.append(_emit(claim_id, "extract.patient_check", TraceStatus.FAIL,
                            detail=f"Patient name mismatch: {sorted(unique_names)}"))
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        return {
            "fused_docs": fused_docs,
            "halt": True,
            "halt_message": msg,
            "extraction_confidence": avg_conf,
            "failed_components": failed,
            "trace": events,
        }

    events.append(_emit(
        claim_id, "extract.patient_check", TraceStatus.PASS,
        detail=f"Patient name consistent: {list(unique_names) or ['(not extracted)']}",
    ))

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
    elapsed = int((time.time() - t0) * 1000)
    events[-1] = events[-1].model_copy(update={"duration_ms": elapsed})

    return {
        "fused_docs": fused_docs,
        "halt": False,
        "extraction_confidence": avg_conf,
        "failed_components": failed,
        "trace": events,
    }
