"""
GeminiClassifierProvider — classifies a document image into a DocumentType.

Uses Gemini 2.0 Flash with a concise classification prompt.
Falls back to DocumentType.UNKNOWN on failure (the verifier then catches
the missing required type and gives the member an actionable message).
"""
import asyncio
import json
import logging

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import settings
from app.models.document import DocumentType

logger = logging.getLogger(__name__)

_CLASSIFY_PROMPT = """\
Classify this medical document image into exactly one category.

Return ONLY valid JSON — no explanation, no markdown:
{{"document_type": "CATEGORY", "confidence": 0.0}}

Valid categories (pick one):
PRESCRIPTION         - Doctor's Rx / prescription slip
HOSPITAL_BILL        - Hospital or clinic invoice/receipt
LAB_REPORT           - Laboratory or diagnostic test report
PHARMACY_BILL        - Pharmacy/chemist invoice
DISCHARGE_SUMMARY    - Hospital discharge summary
DENTAL_REPORT        - Dental treatment report or dental X-ray report
DIAGNOSTIC_REPORT    - Radiology or imaging report (MRI/CT/X-ray)
UNKNOWN              - Cannot determine

Confidence: 0.0–1.0. Use 0.9+ when you are certain, 0.6–0.89 for likely, below 0.6 for uncertain.
"""

_TIMEOUT_SECONDS = 15

_VALID_TYPES = {t.value for t in DocumentType}


class GeminiClassifierProvider:
    """Classifies a document image into a DocumentType using Gemini."""

    def __init__(self) -> None:
        self._model = None
        self._ready = False
        if settings.gemini_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings.gemini_api_key)
                self._model = genai.GenerativeModel(
                    model_name="gemini-2.0-flash",
                    generation_config={"response_mime_type": "application/json", "temperature": 0.0},
                )
                self._ready = True
                logger.info("GeminiClassifierProvider ready")
            except Exception as exc:
                logger.warning("GeminiClassifierProvider init failed: %s", exc)

    def is_available(self) -> bool:
        return self._ready

    async def classify(self, file_id: str, file_bytes: bytes,
                       mime_type: str = "image/jpeg") -> tuple[DocumentType, float]:
        """Returns (DocumentType, confidence). Falls back to UNKNOWN on any error."""
        if not self._ready:
            return DocumentType.UNKNOWN, 0.30
        try:
            return await asyncio.wait_for(
                self._call_gemini(file_bytes, mime_type),
                timeout=_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("GeminiClassifier timeout for %s", file_id)
            return DocumentType.UNKNOWN, 0.30
        except Exception as exc:
            logger.warning("GeminiClassifier error for %s: %s", file_id, exc)
            return DocumentType.UNKNOWN, 0.30

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    async def _call_gemini(self, file_bytes: bytes,
                           mime_type: str) -> tuple[DocumentType, float]:
        image_part = {"mime_type": mime_type, "data": file_bytes}
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._model.generate_content([_CLASSIFY_PROMPT, image_part]),
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        dtype_str = str(data.get("document_type", "UNKNOWN")).upper()
        if dtype_str not in _VALID_TYPES:
            dtype_str = "UNKNOWN"
        confidence = float(data.get("confidence", 0.70))
        return DocumentType(dtype_str), confidence


# Module singleton
gemini_classifier = GeminiClassifierProvider()
