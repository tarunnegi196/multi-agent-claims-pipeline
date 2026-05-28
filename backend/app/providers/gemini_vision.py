"""
GeminiVisionProvider — extracts structured fields from Indian medical document images.

Uses Gemini 2.5 Flash (vision) with a comprehensive India-specific prompt covering:
  - All 4 core document types: PRESCRIPTION, HOSPITAL_BILL, LAB_REPORT, PHARMACY_BILL
  - Medical shorthand expansion (HTN, T2DM, URI, etc.)
  - State-specific doctor registration formats (KA/XXXXX/YYYY, MH/, DL/, etc.)
  - Document quality flags: handwriting, rubber stamps, alterations, multilingual
  - India-specific billing fields: GSTIN, drug license, NABL accreditation
  - Per-document-type confidence scoring with quality penalty

Extraction priority in extractor.py:
  1. Inline content dict  (test stubs / pre-parsed inputs)  ← no API call
  2. GeminiVisionProvider  (file_path set + API key present)
  3. Degraded stub          (simulate_component_failure or no key/file)
"""
import asyncio
import time
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
from app.models.document import DocumentType, ExtractedDoc, LineItem, MedicineDetail

logger = logging.getLogger(__name__)

# ── Per-document-type core fields used for confidence scoring ────────────────
_CORE_FIELDS: dict[str, list[str]] = {
    "PRESCRIPTION":      ["patient_name", "date", "doctor_name", "doctor_registration", "diagnosis"],
    "HOSPITAL_BILL":     ["patient_name", "date", "hospital_name", "bill_number", "total_amount"],
    "LAB_REPORT":        ["patient_name", "sample_date", "lab_name", "pathologist_name", "test_results"],
    "PHARMACY_BILL":     ["patient_name", "date", "pharmacy_name", "drug_license_number", "net_amount"],
    "DISCHARGE_SUMMARY": ["patient_name", "date", "hospital_name", "diagnosis", "total_amount"],
    "DENTAL_REPORT":     ["patient_name", "date", "hospital_name", "line_items", "total_amount"],
    "DIAGNOSTIC_REPORT": ["patient_name", "report_date", "lab_name", "pathologist_name", "test_results"],
    "UNKNOWN":           ["patient_name", "date", "doctor_name", "hospital_name", "total_amount"],
}

# Quality flags that penalise confidence
_QUALITY_PENALTIES: dict[str, float] = {
    "DOCUMENT_ALTERATION": 0.20,
    "PARTIAL_DOCUMENT":    0.10,
    "LOW_CONTRAST":        0.05,
    "MULTILINGUAL":        0.04,
    "RUBBER_STAMP_PRESENT": 0.02,
    "AMOUNT_CORRECTION":   0.05,
    "DUPLICATE_STAMP":     0.03,
}

_TIMEOUT_SECONDS = 30

_EXTRACTION_PROMPT = """\
You are a specialist extraction engine for Indian health insurance claims.
Your task: read this medical document image and return ALL structured data as JSON.

RULES:
- Return ONLY valid JSON. No markdown fences, no explanation, no extra text.
- Use null for any field you cannot reliably read. NEVER fabricate or guess values.
- Amounts: numeric only. Strip ₹, Rs., commas, spaces. "₹ 1,500.00" → 1500.0
- Dates: YYYY-MM-DD. "01-Nov-2024" → "2024-11-01". "1/11/24" → "2024-11-01".
- Preserve registration numbers exactly as printed (e.g. "KA/45678/2015").
- If a field is in a regional script you cannot read, set it null and add the
  field name to "unextracted_fields".

DOCUMENT TYPE HINT: {doc_type}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 1 — MEDICAL SHORTHAND (expand in "diagnosis" and "chief_complaint")
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  HTN / HT           → Hypertension
  T1DM               → Type 1 Diabetes Mellitus
  T2DM / DM          → Type 2 Diabetes Mellitus
  IHD                → Ischemic Heart Disease
  CAD                → Coronary Artery Disease
  CHF                → Congestive Heart Failure
  AF / AFib          → Atrial Fibrillation
  URI / URTI         → Upper Respiratory Tract Infection
  LRI / LRTI         → Lower Respiratory Tract Infection
  COPD               → Chronic Obstructive Pulmonary Disease
  GERD               → Gastroesophageal Reflux Disease
  IBS                → Irritable Bowel Syndrome
  PUD                → Peptic Ulcer Disease
  UTI                → Urinary Tract Infection
  CKD / CRF          → Chronic Kidney Disease
  CVA                → Cerebrovascular Accident (Stroke)
  TIA                → Transient Ischemic Attack
  OA                 → Osteoarthritis
  RA                 → Rheumatoid Arthritis
  PCOD / PCOS        → Polycystic Ovarian Disease / Syndrome
  TB / PTB           → Pulmonary Tuberculosis
  CA                 → Carcinoma (Cancer)
  NHL                → Non-Hodgkin Lymphoma
  CLD / NASH         → Chronic Liver Disease / Non-Alcoholic Steatohepatitis
  HT + DM            → Hypertension with Diabetes Mellitus
  k/c/o              → Known case of [condition follows]
  c/o                → Complains of
  h/o                → History of
  b/l                → Bilateral
  s/p                → Status post (after procedure)
  SOB                → Shortness of Breath
  CP                 → Chest Pain
  Dx                 → Diagnosis
  Rx / ℞             → Prescription

MEDICINE FREQUENCY CODES (include in medicines list as-is or expanded):
  OD                 → Once daily
  BD / BID           → Twice daily
  TDS / TID          → Thrice daily
  QID                → Four times daily
  HS                 → At bedtime
  SOS / PRN          → As needed
  AC                 → Before meals
  PC                 → After meals
  1-0-1 / 1-1-1 etc → Morning-Afternoon-Night dosing (keep numeric form)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2 — DOCTOR / PATHOLOGIST REGISTRATION FORMATS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Look for labels: "Reg. No:", "Regd. No:", "Regn. No:", "MCI No:", "SMC No:",
"Registration No:", "Lic. No:", or a number next to a doctor's name/stamp.

  State-council format:  XX/NNNNN/YYYY
    Karnataka     KA/45678/2015
    Maharashtra   MH/23456/2018
    Delhi         DL/34567/2016
    Tamil Nadu    TN/56789/2013
    Gujarat       GJ/56789/2014
    Andhra Pradesh AP/67890/2017
    Uttar Pradesh  UP/45678/2016
    West Bengal   WB/34567/2015
    Kerala        KL/78901/2012
    Telangana     TS/12345/2018
    Rajasthan     RJ/34567/2017
    Punjab        PB/23456/2016
    Haryana       HR/12345/2015
    Odisha        OD/34567/2016
    Bihar         BR/23456/2017

  Ayurveda (national):  AYUR/[STATE]/NNNNN/YYYY
    Example: AYUR/KL/2345/2019

  Homeopathy (national): HOM/[STATE]/NNNNN/YYYY

  Dental:               DCI/NNNNN or state format

  NMC (national):       NMC-NNNNN-YYYY

Capture the full registration string exactly as printed.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 3 — QUALITY FLAGS (populate "quality_flags" array)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Add each applicable flag string to the "quality_flags" array:

  "HANDWRITTEN"           — document is fully or partially handwritten
  "RUBBER_STAMP_PRESENT"  — ink rubber stamp visible (may obscure text beneath)
  "LOW_CONTRAST"          — image is faded, dark, overexposed, or very low quality
  "PARTIAL_DOCUMENT"      — page appears cut off, folded, or corner missing
  "MULTILINGUAL"          — non-English script present (Hindi, Tamil, Telugu, Kannada, etc.)
  "AMOUNT_CORRECTION"     — amounts appear crossed out and rewritten
  "DUPLICATE_STAMP"       — "DUPLICATE" watermark or multiple "ORIGINAL" stamps visible
  "DOCUMENT_ALTERATION"   — evidence of whiteout, erasure, paste-over, or overwriting on
                            any key field (patient name, date, amount, diagnosis)

IMPORTANT:
  - Set "document_alteration_detected": true  if DOCUMENT_ALTERATION is in quality_flags.
  - Set "duplicate_stamp_detected": true       if DUPLICATE_STAMP is in quality_flags.
  - A rubber stamp that does NOT obscure key text: add RUBBER_STAMP_PRESENT but do NOT
    set DOCUMENT_ALTERATION.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 4 — LANGUAGE HANDLING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  - Set "language_detected" to the primary language of the document
    ("English", "Hindi", "Tamil", "Telugu", "Kannada", "Marathi", "Bengali", "Mixed").
  - If a medicine name or diagnosis is in a regional script, attempt transliteration
    to English (e.g. "बुखार" → "Fever", "மருந்து" → "Medicine").
  - If a field is entirely in a script you cannot transliterate, set it null and
    add the field name (e.g. "diagnosis") to "unextracted_fields".
  - Regional language hospital/pharmacy names: transliterate to English if possible.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 5 — DOCUMENT-TYPE SPECIFIC GUIDANCE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▶ PRESCRIPTION
  - Look for letterhead with doctor name, degree, registration, clinic name.
  - "Rx" or "℞" symbol marks the medicine section.
  - Medicine format: "Tab/Cap/Syp/Inj/Oint [name] [dose]mg — [frequency] x [duration days]"
    Examples: "Tab Paracetamol 650mg — 1-1-1 x 5 days"
              "Inj Ceftriaxone 1g IV BD x 3 days"
              "Syp Amoxicillin 250mg/5ml — 5ml TDS x 7 days"
  - Include full string (name + dose + frequency + duration) in the "medicines" list.
  - Look for "Investigations:", "Lab:", "Ix:", "Advised:" for tests_ordered.
  - "chief_complaint": text after "C/O:", "Complaints:", "Presenting with:".
  - Diagnoses section may say "Dx:", "Diagnosis:", "Impression:", "Assessment:".
  - Pre-printed templates with handwritten fill-ins are common — read both.
  - Registration stamp may appear as circular ink stamp — read it carefully.
  - patient_age: look for "Age:", "Yrs", "Y/M/D" notation. Extract as string e.g. "39 years".
  - patient_gender: "M/F", "Male/Female", "Sex:".

▶ HOSPITAL_BILL / CLINIC_INVOICE
  - Header: hospital name, address, GSTIN (15-char: 29XXXXX1234X1ZX), phone, email.
  - Bill section: "Bill No:", "Receipt No:", "Invoice No:" — keep full identifier.
  - Itemised table columns: DESCRIPTION / PARTICULARS | QTY | RATE | AMOUNT
  - Line item types: Consultation Fee, OPD charges, Room charges, Procedure charges,
    Investigation charges, Medicine/Pharmacy, Nursing charges, OT charges.
  - If line items are vague (just "Medicines — ₹3,000"), still extract them.
  - "subtotal_amount": before GST/discount. "total_amount": final payable.
  - GST on medical services is typically 0%; non-medical items may have 5%/12%/18%.
  - "payment_mode": look for "Paid by:", "Mode:", or tick-marks on Cash/UPI/Card/Cheque/Insurance.
  - Cashier name / cashier stamp at bottom — not required in extraction.
  - Handwritten bills: extract whatever is readable; set HANDWRITTEN flag.
  - Amounts with strikethrough: use the final written value; set AMOUNT_CORRECTION flag.

▶ LAB_REPORT / DIAGNOSTIC_REPORT
  - "lab_name": full lab name from header (e.g. "Precision Diagnostics Pvt Ltd").
  - "lab_id": NABL accreditation ID or lab registration code if present.
  - "nabl_accredited": true if "NABL Accredited", "NABL Cert:", or NABL logo is visible.
  - "sample_date": date sample was collected. "report_date": date report was issued.
  - "sample_id": any barcode/sample ID (e.g. "PD-2024-18723").
  - "test_results": dict mapping test name → result string including units and flag.
    Examples:
      "Hemoglobin": "13.2 g/dL (Normal: 13.0–17.0)"
      "WBC Count": "9800 /μL (Normal: 4500–11000)"
      "Dengue NS1 Antigen": "NEGATIVE"
      "Blood Glucose (F)": "142 mg/dL HIGH (Normal: 70–100)"
    Include H (High), L (Low), * (Critical) flags if printed.
  - Pathologist: name at bottom, "Reported by:", "Verified by:", "Consultant Pathologist:".
  - Remarks / interpretation text: include as a "remarks" key in test_results if present.
  - For radiology/imaging (MRI, CT, X-Ray, USG): "test_results" key = scan name,
    value = impression text (e.g. "MRI Lumbar Spine": "L4-L5 disc herniation noted").

▶ PHARMACY_BILL
  - "pharmacy_name": shop name from header.
  - "drug_license_number": "Drug Lic. No:", "D.L. No:", "Lic. No:" — format KA-BLR-XXXX.
  - Each row in the medicine table → "medicine_details" array:
      name: drug name + strength (e.g. "Paracetamol 650mg")
      batch: batch number (e.g. "A2341")
      expiry: expiry date as printed (e.g. "03/26" or "Mar-2026")
      quantity: numeric quantity dispensed
      mrp: MRP per unit (numeric)
      amount: line total (numeric)
  - Also extract just the medicine names + dosages into "medicines" list for policy matching.
  - "subtotal_amount": before discount. "discount_amount": discount value.
  - "net_amount": final amount after discount (= subtotal − discount).
  - Pharmacist name at bottom — not required but extract as "pathologist_name" is unused here.

▶ DENTAL_REPORT
  - Tooth numbers: FDI notation (11–48) or Universal (1–32). Include in test_results.
  - Procedure names: Root Canal Treatment (RCT), Extraction, Scaling, Crown, Filling, etc.
  - X-ray findings if present.
  - Hospital/clinic name in hospital_name.
  - Line items: each procedure + amount.

▶ DISCHARGE_SUMMARY
  - "date": discharge date (not admission date).
  - "sample_date": admission date (reuse field).
  - Primary + secondary diagnoses → "diagnosis" (comma-separated).
  - Procedures performed → "tests_ordered" list.
  - Discharge medications → "medicines" list.
  - Follow-up instructions → can be added to test_results as "follow_up".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT JSON SCHEMA (return exactly this structure, all keys required)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{{
  "patient_name": null,
  "patient_age": null,
  "patient_gender": null,
  "date": null,

  "doctor_name": null,
  "doctor_specialization": null,
  "doctor_registration": null,
  "chief_complaint": null,
  "diagnosis": null,
  "medicines": [],
  "medicine_details": [],
  "tests_ordered": [],

  "hospital_name": null,
  "hospital_address": null,
  "gstin": null,
  "bill_number": null,
  "line_items": [],
  "subtotal_amount": null,
  "discount_amount": null,
  "total_amount": null,
  "payment_mode": null,

  "pharmacy_name": null,
  "drug_license_number": null,
  "net_amount": null,

  "lab_name": null,
  "lab_id": null,
  "nabl_accredited": null,
  "sample_date": null,
  "report_date": null,
  "sample_id": null,
  "pathologist_name": null,
  "pathologist_registration": null,
  "test_results": {{}},

  "language_detected": null,
  "quality_flags": [],
  "document_alteration_detected": false,
  "duplicate_stamp_detected": false,
  "unextracted_fields": []
}}

For "line_items":      [{{"description": "text", "amount": 0.0}}]
For "medicine_details": [{{"name": "text", "batch": null, "expiry": null, "quantity": null, "mrp": null, "amount": null}}]
"""

_TIMEOUT_SECONDS = 30

# ── Bounding-box prompt (on-demand only — never called by the pipeline) ───────
_BBOX_PROMPT = """\
You are a field-localization system for Indian medical documents.
Identify the location of every key field visible in this document image.

CRITICAL: Return ONLY valid JSON. No markdown fences, no explanation.

Bounding boxes use normalized integers 0–1000 where (0,0) is TOP-LEFT
and (1000,1000) is BOTTOM-RIGHT. Format: [y_min, x_min, y_max, x_max].
Make boxes tight around the text — do not pad excessively.

Document type: {doc_type}

Return exactly this structure:
{{
  "regions": [
    {{
      "field": "field_name",
      "value": "extracted text value",
      "bbox": [y_min, x_min, y_max, x_max],
      "category": "patient|doctor|clinical|financial|identifier|lab|date"
    }}
  ]
}}

FIELD NAMES and categories to detect:
  patient    : patient_name, patient_age, patient_gender
  doctor     : doctor_name, doctor_specialization, doctor_registration, pathologist_name, pathologist_registration
  clinical   : diagnosis, chief_complaint, medicine_1 … medicine_N (one per line), treatment
  financial  : total_amount, subtotal_amount, net_amount, discount_amount, line_item_1 … line_item_N (one per row)
  identifier : bill_number, drug_license_number, gstin, sample_id, lab_id
  lab        : lab_name, nabl_status, test_result_1 … test_result_N (one per test row)
  date       : date, sample_date, report_date

RULES:
- Only include fields that are CLEARLY VISIBLE with readable text.
- For multi-line medicine lists: create one region per medicine line (field = "medicine_1", "medicine_2", etc.)
- For bill line items: create one region per item row (field = "line_item_1", "line_item_2", etc.)
- For test results: create one region per result row (field = "test_result_1", "test_result_2", etc.)
- Include the header row of any table as a separate region with field = "table_header".
- The "value" string should be the verbatim text inside that bbox.
- Skip blank or completely unreadable regions.
"""


def _compute_confidence(data: dict, dtype: DocumentType, quality_flags: list[str]) -> float:
    """
    Per-document-type confidence based on how many type-specific core fields
    were successfully extracted, then penalised by detected quality issues.
    """
    core_fields = _CORE_FIELDS.get(dtype.value, _CORE_FIELDS["UNKNOWN"])
    filled = 0
    for f in core_fields:
        val = data.get(f)
        # test_results is a dict — non-empty counts as filled
        if isinstance(val, dict):
            filled += 1 if val else 0
        elif isinstance(val, list):
            filled += 1 if val else 0
        else:
            filled += 1 if val is not None else 0

    base = 0.60 + (0.07 * filled)   # 0.60–0.95 across 5 core fields
    base = min(base, 0.95)

    penalty = sum(_QUALITY_PENALTIES.get(f, 0.0) for f in quality_flags)
    return max(round(base - penalty, 3), 0.10)


def _build_extracted(file_id: str, dtype: DocumentType, data: dict,
                     confidence: float) -> ExtractedDoc:
    line_items = [
        LineItem(
            description=str(item.get("description", "")),
            amount=float(item.get("amount", 0.0)),
        )
        for item in (data.get("line_items") or [])
        if item.get("description")
    ]

    medicine_details = []
    for m in (data.get("medicine_details") or []):
        if not m.get("name"):
            continue
        try:
            medicine_details.append(MedicineDetail(
                name=str(m["name"]),
                batch=m.get("batch"),
                expiry=m.get("expiry"),
                quantity=int(m["quantity"]) if m.get("quantity") is not None else None,
                mrp=float(m["mrp"]) if m.get("mrp") is not None else None,
                amount=float(m["amount"]) if m.get("amount") is not None else None,
            ))
        except (TypeError, ValueError):
            pass

    quality_flags: list[str] = [str(f) for f in (data.get("quality_flags") or [])]
    flags: list[str] = list(quality_flags)
    if data.get("document_alteration_detected"):
        if "DOCUMENT_ALTERATION" not in flags:
            flags.append("DOCUMENT_ALTERATION")
    if data.get("duplicate_stamp_detected"):
        if "DUPLICATE_STAMP" not in flags:
            flags.append("DUPLICATE_STAMP")

    def _float_or_none(key: str) -> float | None:
        v = data.get(key)
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    return ExtractedDoc(
        file_id=file_id,
        document_type=dtype,
        # Shared
        patient_name=data.get("patient_name"),
        patient_age=data.get("patient_age"),
        patient_gender=data.get("patient_gender"),
        date=str(data["date"]) if data.get("date") else None,
        # Prescription
        doctor_name=data.get("doctor_name"),
        doctor_specialization=data.get("doctor_specialization"),
        doctor_registration=data.get("doctor_registration"),
        chief_complaint=data.get("chief_complaint"),
        diagnosis=data.get("diagnosis"),
        medicines=[m for m in (data.get("medicines") or []) if m],
        medicine_details=medicine_details,
        tests_ordered=[t for t in (data.get("tests_ordered") or []) if t],
        # Hospital bill
        hospital_name=data.get("hospital_name"),
        hospital_address=data.get("hospital_address"),
        gstin=data.get("gstin"),
        bill_number=data.get("bill_number"),
        line_items=line_items,
        subtotal_amount=_float_or_none("subtotal_amount"),
        discount_amount=_float_or_none("discount_amount"),
        total_amount=_float_or_none("total_amount"),
        payment_mode=data.get("payment_mode"),
        # Pharmacy
        pharmacy_name=data.get("pharmacy_name"),
        drug_license_number=data.get("drug_license_number"),
        net_amount=_float_or_none("net_amount"),
        # Lab / diagnostic
        lab_name=data.get("lab_name"),
        lab_id=data.get("lab_id"),
        nabl_accredited=data.get("nabl_accredited"),
        sample_date=str(data["sample_date"]) if data.get("sample_date") else None,
        report_date=str(data["report_date"]) if data.get("report_date") else None,
        sample_id=data.get("sample_id"),
        pathologist_name=data.get("pathologist_name"),
        pathologist_registration=data.get("pathologist_registration"),
        test_results=data.get("test_results") or {},
        # Quality
        language_detected=data.get("language_detected"),
        quality_flags=quality_flags,
        document_alteration_detected=bool(data.get("document_alteration_detected", False)),
        duplicate_stamp_detected=bool(data.get("duplicate_stamp_detected", False)),
        # Metadata
        extraction_method="gemini_vision",
        overall_confidence=confidence,
        unextracted_fields=data.get("unextracted_fields") or [],
        flags=flags,
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
                    model_name=settings.gemini_extractor_model,
                    generation_config={
                        "response_mime_type": "application/json",
                        "temperature": 0.1,
                    },
                )
                self._ready = True
                logger.info("GeminiVisionProvider ready (model=%s)", settings.gemini_extractor_model)
            except Exception as exc:
                logger.warning("GeminiVisionProvider init failed: %s", exc)

    def is_available(self) -> bool:
        return self._ready

    async def extract(self, file_id: str, dtype: DocumentType,
                      file_bytes: bytes, mime_type: str = "image/jpeg") -> ExtractedDoc:
        if not self._ready:
            logger.warning(
                "[GEMINI-VISION] SKIP  no API key — returning degraded stub  file_id=%s", file_id
            )
            return _degraded_stub(file_id, dtype, "no API key or init failed")
        try:
            return await asyncio.wait_for(
                self._call_gemini(file_id, dtype, file_bytes, mime_type),
                timeout=_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[GEMINI-VISION] TIMEOUT  file_id=%s  timeout=%ds", file_id, _TIMEOUT_SECONDS
            )
            return _degraded_stub(file_id, dtype, f"timeout after {_TIMEOUT_SECONDS}s")
        except Exception as exc:
            logger.error(
                "[GEMINI-VISION] ERROR  file_id=%s  error=%s", file_id, exc, exc_info=True
            )
            return _degraded_stub(file_id, dtype, str(exc))

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _call_gemini(self, file_id: str, dtype: DocumentType,
                           file_bytes: bytes, mime_type: str) -> ExtractedDoc:
        size_kb = len(file_bytes) / 1024
        logger.info(
            "[GEMINI-VISION] CALL  model=%s  task=extract  "
            "file_id=%s  doc_type=%s  size=%.1fKB  mime=%s",
            settings.gemini_extractor_model, file_id, dtype.value, size_kb, mime_type,
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

        # Strip markdown fences if model wraps despite mime_type setting
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)  # JSONDecodeError → retry via tenacity

        quality_flags: list[str] = [str(f) for f in (data.get("quality_flags") or [])]
        confidence = _compute_confidence(data, dtype, quality_flags)

        elapsed = time.time() - t0
        logger.info(
            "[GEMINI-VISION] DONE  file_id=%s  doc_type=%s  "
            "confidence=%.2f  duration=%.2fs  quality_flags=%s  "
            "patient=%s  diagnosis=%s  alteration=%s",
            file_id, dtype.value, confidence, elapsed,
            quality_flags or "none",
            data.get("patient_name", "(none)"),
            data.get("diagnosis", "(none)"),
            data.get("document_alteration_detected", False),
        )

        return _build_extracted(file_id, dtype, data, confidence)

    # ── On-demand bounding-box extraction ────────────────────────────────────
    # Completely separate from the claim pipeline. Called only when the user
    # clicks "View regions" in the UI — never invoked during claim processing.

    async def extract_with_bboxes(
        self, file_id: str, dtype: DocumentType,
        file_bytes: bytes, mime_type: str = "image/jpeg",
    ) -> list[dict]:
        """
        Return a list of field regions with bounding boxes for UI visualisation.

        Each entry: {"field": str, "value": str, "bbox": [y1,x1,y2,x2], "category": str}
        Coordinates are 0–1000 normalised integers (Gemini convention).

        Returns [] on any failure — the UI handles the empty state gracefully.
        NOT part of the claim pipeline; called only via GET /api/files/{id}/regions.
        """
        if not self._ready:
            logger.debug("[GEMINI-BBOX] provider not ready, returning []")
            return []
        try:
            return await asyncio.wait_for(
                self._call_gemini_bbox(file_id, dtype, file_bytes, mime_type),
                timeout=_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("[GEMINI-BBOX] timeout for file_id=%s", file_id)
            return []
        except Exception as exc:
            logger.warning("[GEMINI-BBOX] failed for file_id=%s: %s", file_id, exc)
            return []

    async def _call_gemini_bbox(
        self, file_id: str, dtype: DocumentType,
        file_bytes: bytes, mime_type: str,
    ) -> list[dict]:
        size_kb = len(file_bytes) / 1024
        logger.info(
            "[GEMINI-BBOX] CALL  model=%s  file_id=%s  doc_type=%s  size=%.1fKB",
            settings.gemini_extractor_model, file_id, dtype.value, size_kb,
        )
        t0 = time.time()

        prompt = _BBOX_PROMPT.format(doc_type=dtype.value)
        image_part = {"mime_type": mime_type, "data": file_bytes}

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._model.generate_content([prompt, image_part]),
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)
        regions = data.get("regions") or []

        # Sanitise: ensure every region has the expected keys and valid bbox
        clean: list[dict] = []
        for r in regions:
            bbox = r.get("bbox")
            if not (isinstance(bbox, list) and len(bbox) == 4):
                continue
            try:
                bbox = [max(0, min(1000, int(v))) for v in bbox]
            except (TypeError, ValueError):
                continue
            clean.append({
                "field":    str(r.get("field", "unknown")),
                "value":    str(r.get("value", "")),
                "bbox":     bbox,
                "category": str(r.get("category", "identifier")),
            })

        elapsed = time.time() - t0
        logger.info(
            "[GEMINI-BBOX] DONE  file_id=%s  regions=%d  duration=%.2fs",
            file_id, len(clean), elapsed,
        )
        return clean


# Module singleton — agents import this
gemini_vision = GeminiVisionProvider()
