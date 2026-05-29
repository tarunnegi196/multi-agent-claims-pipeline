"""
ExtractionAgent — turns document files into structured FusedDoc objects.

Extraction priority per document:
  1. Inline content dict  (test stubs / pre-parsed inputs)  ← no API call
  2. patient_name_on_doc shortcut (TC003-style test inputs)
  3. GeminiVisionProvider  (file_path set + API key present)
  4. Degraded stub          (simulate_component_failure or no key/file)

For real-file documents, also captures bounding-box regions in parallel so the
UI can render them later without an extra Gemini round-trip.

After extraction, cross-checks patient names across all documents (hard halt
on mismatch) and derives any missing treatment_date / claimed_amount from
the parsed bill totals + dates.

Publishes every TraceEvent to the event bus for live SSE streaming.
"""
import asyncio
import logging
import time
from datetime import datetime, date as _date
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
        # Shared
        patient_name=ex.patient_name,
        patient_age=ex.patient_age,
        patient_gender=ex.patient_gender,
        date=ex.date,
        # Prescription
        doctor_name=ex.doctor_name,
        doctor_specialization=ex.doctor_specialization,
        doctor_registration=ex.doctor_registration,
        chief_complaint=ex.chief_complaint,
        diagnosis=ex.diagnosis,
        medicines=ex.medicines,
        medicine_details=ex.medicine_details,
        tests_ordered=ex.tests_ordered,
        # Hospital bill
        hospital_name=ex.hospital_name,
        hospital_address=ex.hospital_address,
        gstin=ex.gstin,
        bill_number=ex.bill_number,
        line_items=ex.line_items,
        subtotal_amount=ex.subtotal_amount,
        discount_amount=ex.discount_amount,
        total_amount=ex.total_amount,
        payment_mode=ex.payment_mode,
        # Pharmacy
        pharmacy_name=ex.pharmacy_name,
        drug_license_number=ex.drug_license_number,
        net_amount=ex.net_amount,
        # Lab / diagnostic
        lab_name=ex.lab_name,
        lab_id=ex.lab_id,
        nabl_accredited=ex.nabl_accredited,
        sample_date=ex.sample_date,
        report_date=ex.report_date,
        sample_id=ex.sample_id,
        pathologist_name=ex.pathologist_name,
        pathologist_registration=ex.pathologist_registration,
        test_results=ex.test_results,
        # Quality signals
        language_detected=ex.language_detected,
        quality_flags=ex.quality_flags,
        document_alteration_detected=ex.document_alteration_detected,
        duplicate_stamp_detected=ex.duplicate_stamp_detected,
        # Metadata
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

    bbox_regions: dict[str, list[dict]] = {}

    for cdoc in classified:
        doc_ref = doc_map.get(cdoc.file_id)
        try:
            if doc_ref and doc_ref.file_path and Path(doc_ref.file_path).exists():
                # Real file — always use Gemini Vision; stubs are only for no-file requests.
                # Fire extraction + bbox calls in parallel so the bboxes are ready when
                # the UI asks, with no second Gemini round-trip on click.
                from app.providers.gemini_vision import gemini_vision
                file_bytes = Path(doc_ref.file_path).read_bytes()
                suffix = Path(doc_ref.file_path).suffix.lower()
                _mime_map = {".pdf": "application/pdf", ".png": "image/png", ".webp": "image/webp"}
                mime = _mime_map.get(suffix, "image/jpeg")
                extracted, regions = await asyncio.gather(
                    gemini_vision.extract(cdoc.file_id, cdoc.document_type, file_bytes, mime),
                    gemini_vision.extract_with_bboxes(cdoc.file_id, cdoc.document_type, file_bytes, mime),
                    return_exceptions=False,
                )
                if regions:
                    bbox_regions[cdoc.file_id] = regions
                    # Persist to disk so the /regions endpoint can serve without re-calling Gemini
                    try:
                        import json as _json
                        regions_path = Path(doc_ref.file_path).with_suffix(".regions.json")
                        regions_path.write_text(_json.dumps({
                            "doc_type": cdoc.document_type.value,
                            "regions": regions,
                        }))
                    except Exception as _exc:
                        logger.debug("[EXTRACT] could not cache regions for %s: %s", cdoc.file_id, _exc)

            elif doc_ref and doc_ref.content:
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
            "bbox_regions": bbox_regions,
            "trace": events,
        }

    event = _make_event(
        claim_id, "extract.patient_check", TraceStatus.PASS,
        detail=f"Patient name consistent: {list(unique_names) or ['(not extracted)']}",
    )
    events.append(event)
    await event_bus.publish(event)

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    # ── Derive missing claim fields from extraction ──────────────────────────
    # The simplified UI submits only (member_id, category, documents). We
    # populate treatment_date and claimed_amount here so downstream nodes have
    # a complete claim to work with.
    updated_claim = claim
    claim_updates: dict = {}

    if claim.claimed_amount is None:
        # Prefer hospital-bill totals, then pharmacy net_amount, then any bill total
        billed_total = 0.0
        for fd in fused_docs:
            if fd.total_amount:
                billed_total += float(fd.total_amount)
            elif fd.net_amount:
                billed_total += float(fd.net_amount)
        if billed_total > 0:
            claim_updates["claimed_amount"] = billed_total
            events.append(_make_event(
                claim_id, "extract.derive_amount", TraceStatus.PASS,
                detail=f"Derived claimed_amount=₹{billed_total:,.0f} from bill totals",
                confidence=avg_conf,
            ))
            await event_bus.publish(events[-1])
        else:
            events.append(_make_event(
                claim_id, "extract.derive_amount", TraceStatus.WARN,
                detail="Could not derive claimed amount from any document — defaulting to 0",
            ))
            await event_bus.publish(events[-1])
            claim_updates["claimed_amount"] = 0.0

    if claim.treatment_date is None:
        # Pick the latest valid date among extracted docs (bill > prescription > lab)
        parsed_dates: list[_date] = []
        for fd in fused_docs:
            for raw in (fd.date, fd.sample_date, fd.report_date):
                if not raw:
                    continue
                for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
                    try:
                        parsed_dates.append(datetime.strptime(str(raw), fmt).date())
                        break
                    except ValueError:
                        continue
        if parsed_dates:
            picked = max(parsed_dates)
            claim_updates["treatment_date"] = picked
            events.append(_make_event(
                claim_id, "extract.derive_date", TraceStatus.PASS,
                detail=f"Derived treatment_date={picked.isoformat()} from documents",
                confidence=avg_conf,
            ))
            await event_bus.publish(events[-1])
        else:
            today = datetime.utcnow().date()
            claim_updates["treatment_date"] = today
            events.append(_make_event(
                claim_id, "extract.derive_date", TraceStatus.WARN,
                detail=f"Could not derive treatment_date — using today ({today.isoformat()})",
            ))
            await event_bus.publish(events[-1])

    if claim_updates:
        updated_claim = claim.model_copy(update=claim_updates)

    elapsed = int((time.time() - t0) * 1000)
    events[-1] = events[-1].model_copy(update={"duration_ms": elapsed})

    logger.info("[EXTRACT] done  claim_id=%s  avg_conf=%.2f  failed=%s  bboxes=%d  duration=%dms",
                claim_id, avg_conf, failed or "none", len(bbox_regions), elapsed)
    return {
        "claim": updated_claim,
        "fused_docs": fused_docs,
        "halt": False,
        "extraction_confidence": avg_conf,
        "failed_components": failed,
        "bbox_regions": bbox_regions,
        "trace": events,
    }
