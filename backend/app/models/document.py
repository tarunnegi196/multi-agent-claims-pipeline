from enum import Enum
from typing import Optional
from pydantic import BaseModel


class DocumentType(str, Enum):
    PRESCRIPTION = "PRESCRIPTION"
    HOSPITAL_BILL = "HOSPITAL_BILL"
    LAB_REPORT = "LAB_REPORT"
    PHARMACY_BILL = "PHARMACY_BILL"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    DENTAL_REPORT = "DENTAL_REPORT"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    UNKNOWN = "UNKNOWN"


class DocumentQuality(str, Enum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    UNREADABLE = "UNREADABLE"


class LineItem(BaseModel):
    description: str
    amount: float


class MedicineDetail(BaseModel):
    """Structured per-medicine row from pharmacy bills."""
    name: str
    batch: Optional[str] = None
    expiry: Optional[str] = None
    quantity: Optional[int] = None
    mrp: Optional[float] = None
    amount: Optional[float] = None


class ClassifiedDoc(BaseModel):
    """Output of DocumentClassifierAgent — one entry per uploaded file."""
    file_id: str
    file_name: str
    document_type: DocumentType
    confidence: float
    quality: DocumentQuality = DocumentQuality.GOOD


class ExtractedDoc(BaseModel):
    """
    Structured fields pulled from a single document by the extraction provider.
    Fields absent from the document are None; fields attempted but unreadable are
    listed in unextracted_fields with overall_confidence reduced accordingly.
    """
    file_id: str
    document_type: DocumentType

    # ── Shared ────────────────────────────────────────────────────────────────
    patient_name: Optional[str] = None
    patient_age: Optional[str] = None
    patient_gender: Optional[str] = None
    date: Optional[str] = None

    # ── Prescription ──────────────────────────────────────────────────────────
    doctor_name: Optional[str] = None
    doctor_specialization: Optional[str] = None
    doctor_registration: Optional[str] = None
    chief_complaint: Optional[str] = None
    diagnosis: Optional[str] = None
    medicines: list[str] = []
    medicine_details: list[MedicineDetail] = []
    tests_ordered: list[str] = []

    # ── Hospital bill / clinic invoice ────────────────────────────────────────
    hospital_name: Optional[str] = None
    hospital_address: Optional[str] = None
    gstin: Optional[str] = None
    bill_number: Optional[str] = None
    line_items: list[LineItem] = []
    subtotal_amount: Optional[float] = None
    discount_amount: Optional[float] = None
    total_amount: Optional[float] = None
    payment_mode: Optional[str] = None

    # ── Pharmacy bill ─────────────────────────────────────────────────────────
    pharmacy_name: Optional[str] = None
    drug_license_number: Optional[str] = None
    net_amount: Optional[float] = None

    # ── Lab / diagnostic report ───────────────────────────────────────────────
    lab_name: Optional[str] = None
    lab_id: Optional[str] = None
    nabl_accredited: Optional[bool] = None
    sample_date: Optional[str] = None
    report_date: Optional[str] = None
    sample_id: Optional[str] = None
    pathologist_name: Optional[str] = None
    pathologist_registration: Optional[str] = None
    test_results: dict[str, str] = {}

    # ── Document quality signals ──────────────────────────────────────────────
    language_detected: Optional[str] = None
    quality_flags: list[str] = []
    document_alteration_detected: bool = False
    duplicate_stamp_detected: bool = False

    # ── Extraction metadata ───────────────────────────────────────────────────
    extraction_method: str = "gemini_vision"
    overall_confidence: float = 1.0
    field_confidence: dict[str, float] = {}
    unextracted_fields: list[str] = []
    flags: list[str] = []


class FusedDoc(BaseModel):
    """
    Cross-checked result after comparing VLM and OCR extractions.
    Where they agree the field is high-confidence; disagreement or VLM timeout
    marks the field LOW and reduces overall_confidence.
    """
    file_id: str
    document_type: DocumentType

    # ── Shared ────────────────────────────────────────────────────────────────
    patient_name: Optional[str] = None
    patient_age: Optional[str] = None
    patient_gender: Optional[str] = None
    date: Optional[str] = None

    # ── Prescription ──────────────────────────────────────────────────────────
    doctor_name: Optional[str] = None
    doctor_specialization: Optional[str] = None
    doctor_registration: Optional[str] = None
    chief_complaint: Optional[str] = None
    diagnosis: Optional[str] = None
    medicines: list[str] = []
    medicine_details: list[MedicineDetail] = []
    tests_ordered: list[str] = []

    # ── Hospital bill ─────────────────────────────────────────────────────────
    hospital_name: Optional[str] = None
    hospital_address: Optional[str] = None
    gstin: Optional[str] = None
    bill_number: Optional[str] = None
    line_items: list[LineItem] = []
    subtotal_amount: Optional[float] = None
    discount_amount: Optional[float] = None
    total_amount: Optional[float] = None
    payment_mode: Optional[str] = None

    # ── Pharmacy ──────────────────────────────────────────────────────────────
    pharmacy_name: Optional[str] = None
    drug_license_number: Optional[str] = None
    net_amount: Optional[float] = None

    # ── Lab / diagnostic ──────────────────────────────────────────────────────
    lab_name: Optional[str] = None
    lab_id: Optional[str] = None
    nabl_accredited: Optional[bool] = None
    sample_date: Optional[str] = None
    report_date: Optional[str] = None
    sample_id: Optional[str] = None
    pathologist_name: Optional[str] = None
    pathologist_registration: Optional[str] = None
    test_results: dict[str, str] = {}

    # ── Quality signals ───────────────────────────────────────────────────────
    language_detected: Optional[str] = None
    quality_flags: list[str] = []
    document_alteration_detected: bool = False
    duplicate_stamp_detected: bool = False

    # ── Fusion metadata ───────────────────────────────────────────────────────
    overall_confidence: float = 1.0
    field_confidence: dict[str, float] = {}
    low_confidence_fields: list[str] = []
    flags: list[str] = []
