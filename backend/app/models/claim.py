from enum import Enum
from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


class ClaimCategory(str, Enum):
    CONSULTATION = "CONSULTATION"
    DIAGNOSTIC = "DIAGNOSTIC"
    PHARMACY = "PHARMACY"
    DENTAL = "DENTAL"
    VISION = "VISION"
    ALTERNATIVE_MEDICINE = "ALTERNATIVE_MEDICINE"


class DocumentRef(BaseModel):
    file_id: str
    file_name: str
    file_path: Optional[str] = None
    content_type: Optional[str] = None
    # Stub fields used by test cases and the document-type classifier
    actual_type: Optional[str] = None
    content: Optional[dict] = None
    quality: Optional[str] = None
    patient_name_on_doc: Optional[str] = None


class ClaimHistory(BaseModel):
    claim_id: str
    date: date
    amount: float
    provider: Optional[str] = None


class ClaimSubmission(BaseModel):
    member_id: str
    policy_id: str
    claim_category: ClaimCategory
    treatment_date: date
    claimed_amount: float = Field(gt=0)
    hospital_name: Optional[str] = None
    ytd_claims_amount: float = 0.0
    claims_history: list[ClaimHistory] = []
    simulate_component_failure: bool = False
    documents: list[DocumentRef] = Field(min_length=1)
