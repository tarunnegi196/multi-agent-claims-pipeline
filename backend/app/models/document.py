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
    # Shared
    patient_name: Optional[str] = None
    date: Optional[str] = None
    # Prescription
    doctor_name: Optional[str] = None
    doctor_registration: Optional[str] = None
    diagnosis: Optional[str] = None
    medicines: list[str] = []
    tests_ordered: list[str] = []
    # Bill
    hospital_name: Optional[str] = None
    bill_number: Optional[str] = None
    line_items: list[LineItem] = []
    total_amount: Optional[float] = None
    # Lab report
    lab_name: Optional[str] = None
    test_results: dict[str, str] = {}
    # Extraction metadata
    extraction_method: str = "gemini_vision"
    overall_confidence: float = 1.0
    field_confidence: dict[str, float] = {}
    unextracted_fields: list[str] = []
    # Fraud-relevant signals from the document itself
    flags: list[str] = []


class FusedDoc(BaseModel):
    """
    Cross-checked result after comparing VLM and OCR extractions.
    Where they agree the field is high-confidence; disagreement or VLM timeout
    marks the field LOW and reduces overall_confidence.
    """
    file_id: str
    document_type: DocumentType
    patient_name: Optional[str] = None
    date: Optional[str] = None
    doctor_name: Optional[str] = None
    doctor_registration: Optional[str] = None
    diagnosis: Optional[str] = None
    medicines: list[str] = []
    tests_ordered: list[str] = []
    hospital_name: Optional[str] = None
    line_items: list[LineItem] = []
    total_amount: Optional[float] = None
    lab_name: Optional[str] = None
    test_results: dict[str, str] = {}
    # Fusion metadata
    overall_confidence: float = 1.0
    field_confidence: dict[str, float] = {}
    low_confidence_fields: list[str] = []
    flags: list[str] = []
