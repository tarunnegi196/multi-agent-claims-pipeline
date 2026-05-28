"""
GeminiVisionProvider — extracts structured fields from medical document images.

Uses Gemini 2.0 Flash (vision) with a JSON-schema prompt.
Retries up to 3× on transient errors; falls back to a low-confidence stub
on persistent failure so the pipeline never crashes.

Extraction priority in extractor.py:
  1. content stub (test mode)            ← no API call
  2. GeminiVisionProvider (file_path set, API key present)
  3. degraded stub (no key / failure)
"""
import asyncio
import base64
import json
import logging
from pathlib import Path

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.models.document import DocumentType, ExtractedDoc, LineItem

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
You are extracting structured data from an Indian medical document image.

Return ONLY valid JSON — no explanation, no markdown, no extra text.
Use null for any field you cannot reliably read.
For amounts use numeric values only (strip ₹ symbols and commas).
For dates use YYYY-MM-DD format.
For line_items each entry must be: {{"description": "text", "amount": 0.0}}

{{
  "patient_name": null,
  "date": null,
  "doctor_name": null,
  "doctor_registration": null,
  "diagnosis": null,
  "medicines": [],
  "tests_ordered": [],
  "hospital_name": null,
  "bill_number": null,
  "line_items": [],
  "total_amount": null,
  "lab_name": null,
  "test_results": {{}}
}}

Document type hint: {doc_type}
Extract all visible text including handwritten notes, rubber stamps, and partially obscured fields.
"""

_TIMEOUT_SECONDS = 30


def _build_extracted(file_id: str, dtype: DocumentType, data: dict,
                     confidence: float = 0.88) -> ExtractedDoc:
    line_items = [
        LineItem(description=str(item.get("description", "")),
                 amount=float(item.get("amount", 0.0)))
        for item in data.get("line_items") or []
        if item.get("description")
    ]
    return ExtractedDoc(
        file_id=file_id,
        document_type=dtype,
        patient_name=data.get("patient_name"),
        date=str(data["date"]) if data.get("date") else None,
        doctor_name=data.get("doctor_name"),
        doctor_registration=data.get("doctor_registration"),
        diagnosis=data.get("diagnosis"),
        medicines=[m for m in (data.get("medicines") or []) if m],
        tests_ordered=[t for t in (data.get("tests_ordered") or []) if t],
        hospital_name=data.get("hospital_name"),
        bill_number=data.get("bill_number"),
        line_items=line_items,
        total_amount=float(data["total_amount"]) if data.get("total_amount") is not None else None,
        lab_name=data.get("lab_name"),
        test_results=data.get("test_results") or {},
        extraction_method="gemini_vision",
        overall_confidence=confidence,
    )


def _degraded_stub(file_id: str, dtype: DocumentType, reason: str) -> ExtractedDoc:
    logger.warning("GeminiVisionProvider fallback for %s: %s", file_id, reason)
    return ExtractedDoc(
        file_id=file_id,
        document_type=dtype,
        extraction_method="gemini_vision_fallback",
        overall_confidence=0.25,
        unextracted_fields=["all_fields"],
        flags=["EXTRACTION_FALLBACK"],
    )


class GeminiVisionProvider:
    """Extracts structured fields from a document image using Gemini Vision."""

    def __init__(self) -> None:
        self._model = None
        self._ready = False
        if settings.gemini_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings.gemini_api_key)
                self._model = genai.GenerativeModel(
                    model_name="gemini-2.0-flash",
                    generation_config={"response_mime_type": "application/json", "temperature": 0.1},
                )
                self._ready = True
                logger.info("GeminiVisionProvider ready (model=gemini-2.0-flash)")
            except Exception as exc:
                logger.warning("GeminiVisionProvider init failed: %s", exc)

    def is_available(self) -> bool:
        return self._ready

    async def extract(self, file_id: str, dtype: DocumentType,
                      file_bytes: bytes, mime_type: str = "image/jpeg") -> ExtractedDoc:
        if not self._ready:
            logger.warning("[GEMINI-VISION] SKIP  no API key — returning degraded stub  file_id=%s", file_id)
            return _degraded_stub(file_id, dtype, "no API key or init failed")
        try:
            return await asyncio.wait_for(
                self._call_gemini(file_id, dtype, file_bytes, mime_type),
                timeout=_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("[GEMINI-VISION] TIMEOUT  file_id=%s  timeout=%ds", file_id, _TIMEOUT_SECONDS)
            return _degraded_stub(file_id, dtype, f"timeout after {_TIMEOUT_SECONDS}s")
        except Exception as exc:
            logger.error("[GEMINI-VISION] ERROR  file_id=%s  error=%s", file_id, exc, exc_info=True)
            return _degraded_stub(file_id, dtype, str(exc))

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _call_gemini(self, file_id: str, dtype: DocumentType,
                           file_bytes: bytes, mime_type: str) -> ExtractedDoc:
        import google.generativeai as genai

        size_kb = len(file_bytes) / 1024
        logger.info(
            "[GEMINI-VISION] CALL  model=gemini-2.0-flash  task=extract  "
            "file_id=%s  doc_type=%s  size=%.1fKB  mime=%s",
            file_id, dtype.value, size_kb, mime_type,
        )
        t0 = time.time()

        prompt = _EXTRACTION_PROMPT.format(doc_type=dtype.value)
        image_part = {"mime_type": mime_type, "data": file_bytes}

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._model.generate_content([prompt, image_part]),
        )
        raw = response.text.strip()

        # Strip markdown fences if model wraps response despite mime type
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)  # raises JSONDecodeError on bad output → retry

        # Estimate confidence from how many core fields were extracted
        core_fields = ["patient_name", "date", "doctor_name", "diagnosis",
                       "hospital_name", "total_amount"]
        filled = sum(1 for f in core_fields if data.get(f))
        confidence = 0.60 + 0.06 * filled  # 0.60–0.96

        elapsed = time.time() - t0
        logger.info(
            "[GEMINI-VISION] DONE  file_id=%s  doc_type=%s  "
            "fields_filled=%d/6  confidence=%.2f  duration=%.2fs  "
            "patient=%s  diagnosis=%s",
            file_id, dtype.value, filled, confidence, elapsed,
            data.get("patient_name", "(none)"),
            data.get("diagnosis", "(none)"),
        )

        return _build_extracted(file_id, dtype, data, confidence)


# Module singleton — agents import this
gemini_vision = GeminiVisionProvider()
