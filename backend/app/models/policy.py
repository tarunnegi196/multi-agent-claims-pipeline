from typing import Optional
from pydantic import BaseModel


class FamilyFloater(BaseModel):
    enabled: bool
    combined_limit: float
    covered_relationships: list[str]


class Coverage(BaseModel):
    sum_insured_per_employee: float
    annual_opd_limit: float
    per_claim_limit: float
    family_floater: FamilyFloater


class OpdCategory(BaseModel):
    sub_limit: float
    copay_percent: float
    network_discount_percent: float = 0.0
    requires_prescription: bool = False
    requires_pre_auth: bool = False
    pre_auth_threshold: Optional[float] = None
    high_value_tests_requiring_pre_auth: list[str] = []
    covered: bool = True
    branded_drug_copay_percent: Optional[float] = None
    generic_mandatory: bool = False
    covered_procedures: list[str] = []
    excluded_procedures: list[str] = []
    covered_items: list[str] = []
    excluded_items: list[str] = []
    covered_systems: list[str] = []
    max_sessions_per_year: Optional[int] = None
    requires_registered_practitioner: bool = False
    requires_dental_report: bool = False


class WaitingPeriods(BaseModel):
    initial_waiting_period_days: int
    pre_existing_conditions_days: int
    specific_conditions: dict[str, int]


class Exclusions(BaseModel):
    conditions: list[str]
    dental_exclusions: list[str] = []
    vision_exclusions: list[str] = []


class PreAuthorization(BaseModel):
    required_for: list[str]
    validity_days: int


class SubmissionRules(BaseModel):
    deadline_days_from_treatment: int
    minimum_claim_amount: float
    currency: str


class DocumentRequirement(BaseModel):
    required: list[str]
    optional: list[str]


class FraudThresholds(BaseModel):
    same_day_claims_limit: int
    monthly_claims_limit: int
    high_value_claim_threshold: float
    auto_manual_review_above: float
    fraud_score_manual_review_threshold: float


class Member(BaseModel):
    member_id: str
    name: str
    date_of_birth: str
    gender: str
    relationship: str
    join_date: Optional[str] = None
    dependents: list[str] = []
    primary_member_id: Optional[str] = None


class PolicyHolder(BaseModel):
    company_name: str
    employee_count: int
    policy_start_date: str
    policy_end_date: str
    renewal_status: str


class PolicyTerms(BaseModel):
    policy_id: str
    policy_name: str
    insurer: str
    policy_holder: PolicyHolder
    coverage: Coverage
    opd_categories: dict[str, OpdCategory]
    waiting_periods: WaitingPeriods
    exclusions: Exclusions
    pre_authorization: PreAuthorization
    network_hospitals: list[str]
    submission_rules: SubmissionRules
    document_requirements: dict[str, DocumentRequirement]
    fraud_thresholds: FraudThresholds
    members: list[Member]

    def get_member(self, member_id: str) -> Optional[Member]:
        return next((m for m in self.members if m.member_id == member_id), None)

    def get_category(self, category: str) -> Optional[OpdCategory]:
        return self.opd_categories.get(category.lower())

    def is_network_hospital(self, hospital_name: str) -> bool:
        if not hospital_name:
            return False
        name_lower = hospital_name.lower()
        return any(h.lower() in name_lower or name_lower in h.lower()
                   for h in self.network_hospitals)
