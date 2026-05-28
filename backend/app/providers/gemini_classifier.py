"""
GeminiClassifierProvider — classifies a document image into a DocumentType.

Uses Gemini 2.5 Flash Lite with a concise classification prompt.
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
You are classifying an Indian medical document image for a health insurance claims system.
Return ONLY valid JSON — no explanation, no markdown fences:
{{"document_type": "CATEGORY", "confidence": 0.0, "signals": ["key visual clues you used"]}}

━━━ CATEGORIES (pick exactly one) ━━━

PRESCRIPTION
  Visual signals: doctor's letterhead with name + degree + registration number,
  "Rx" or "℞" symbol, medicine list with dosages (Tab/Cap/Syp/Inj),
  frequency notation (1-0-1, BD, TDS, OD), patient name + age + date,
  doctor's signature + stamp at bottom.
  Indian variants: handwritten on plain paper, pre-printed Rx pads,
  stamps with "KA/", "MH/", "DL/" registration codes.

HOSPITAL_BILL
  Visual signals: hospital/clinic name as header, "BILL", "RECEIPT", or "INVOICE"
  title, itemised table (Description | Qty | Rate | Amount), subtotal + total rows,
  GSTIN number (15 chars starting with state code), cashier stamp or signature.
  Indian variants: handwritten bills from small clinics, UPI QR code visible,
  "Dr [Name] Clinic" letterhead, amounts in ₹ or Rs.

LAB_REPORT
  Visual signals: diagnostic lab name as header, "NABL Accredited" logo or text,
  tabular results with columns (Test Name | Result | Unit | Normal Range),
  patient barcode/sample ID, pathologist's signature + "MD Pathology" credentials,
  "Reported by:", "Verified by:" at bottom.
  Indian variants: Quest, SRL, Thyrocare, Metropolis, Dr. Lal Path Labs branding,
  CBC / LFT / KFT / Lipid Profile / HbA1c result tables.

PHARMACY_BILL
  Visual signals: pharmacy/chemist shop name as header, "Drug Lic. No:" or
  "D.L. No:" license number, medicine table (Medicine | Batch | Expiry | Qty | MRP | Amount),
  batch numbers + expiry dates, pharmacist name + stamp.
  Indian variants: MedPlus, Apollo Pharmacy, 1mg branding, handwritten chits
  from local medical shops.

DISCHARGE_SUMMARY
  Visual signals: hospital letterhead, "DISCHARGE SUMMARY" or "DISCHARGE CARD" title,
  admission date + discharge date both present, "Diagnosis on Admission",
  "Diagnosis at Discharge", procedure list, "Condition on Discharge",
  attending doctor's name.

DENTAL_REPORT
  Visual signals: dental clinic name, tooth chart or diagram, FDI tooth numbers
  (11–48) or Universal numbers (1–32), procedure names like "RCT", "Extraction",
  "Scaling", "Crown", "Filling", X-ray image or X-ray report text,
  "BDS", "MDS" dentist qualification.

DIAGNOSTIC_REPORT
  Visual signals: "MRI", "CT Scan", "X-Ray", "Ultrasound", "PET Scan", "ECG",
  "Echo", "2D Echo" in title or header. Radiologist name with "DMRD", "MD Radiology",
  "DNB Radiology" credentials. "Impression:", "Findings:", "Opinion:" sections.
  AERB registration number may be visible.

UNKNOWN
  Use only when the document is completely illegible, is clearly not a medical document,
  or could equally match two or more categories.

━━━ CONFIDENCE GUIDE ━━━
  0.95–1.00 : Multiple strong visual signals clearly match one category.
  0.80–0.94 : Primary signals match, minor ambiguity (e.g. combined bill+prescription).
  0.60–0.79 : Likely match but image quality or unusual format reduces certainty.
  0.40–0.59 : Weak match; only one or two partial signals visible.
  < 0.40    : Very uncertain — lean towards UNKNOWN.
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
                    model_name=settings.gemini_classifier_model,
                    generation_config={"response_mime_type": "application/json", "temperature": 0.0},
                )
                self._ready = True
                logger.info("GeminiClassifierProvider ready (model=%s)", settings.gemini_classifier_model)
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
        size_kb = len(file_bytes) / 1024
        logger.info(
            "[GEMINI-CLASSIFY] CALL  model=%s  size=%.1fKB  mime=%s",
            settings.gemini_classifier_model, size_kb, mime_type,
        )
        t0 = asyncio.get_event_loop().time()

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

        elapsed = asyncio.get_event_loop().time() - t0
        logger.info(
            "[GEMINI-CLASSIFY] DONE  result=%s  confidence=%.2f  duration=%.2fs",
            dtype_str, confidence, elapsed,
        )
        return DocumentType(dtype_str), confidence


# Module singleton
gemini_classifier = GeminiClassifierProvider()
