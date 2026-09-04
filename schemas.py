from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TDSSection(str, Enum):
    SECTION_194C_INDIVIDUAL = "194C_IND"  # 1% TDS on Contractors (Individual/HUF)
    SECTION_194C_IND = "194C_IND"
    SECTION_194C_COMPANY = "194C_CORP"    # 2% TDS on Contractors (Company/Firm)
    SECTION_194C_CORP = "194C_CORP"
    SECTION_194J_TECH = "194J_TECH"       # 2% TDS on Technical Services
    SECTION_194J_PROF = "194J_PROF"       # 10% TDS on Professional Services
    SECTION_194Q_GOODS = "194Q"           # 0.1% on purchase of goods > ₹50 Lakhs
    SECTION_194Q = "194Q"
    SECTION_197_LOWER = "197_LOWER"       # Specific Lower Deduction Certificate
    NONE = "NONE"


class ApprovalTier(str, Enum):
    TIER_1_AP_OPS = "AP_OPS"
    TIER_2_DEPT_HEAD = "DEPT_HEAD"
    TIER_3_CONTROLLER = "FIN_CONTROLLER"
    TIER_4_CFO = "CFO"
    AUTO_APPROVED = "AUTO_APPROVED"


class JournalEntryType(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class InvoiceLineItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku: str
    description: str
    quantity: Decimal = Field(gt=Decimal("0"))
    unit_price: Decimal = Field(gt=Decimal("0"))
    line_total: Decimal = Field(gt=Decimal("0"))

    @field_validator("sku", mode="before")
    @classmethod
    def normalize_sku(cls, v: str) -> str:
        return str(v).strip().upper() if v else ""

    @model_validator(mode="after")
    def validate_line_total(self) -> "InvoiceLineItem":
        expected = (self.quantity * self.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if abs(self.line_total - expected) > Decimal("0.05"):
            raise ValueError(f"Line math mismatch: {self.quantity} * {self.unit_price} != {self.line_total} (Expected {expected})")
        return self


class ExtractedInvoicePayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    invoice_number: str = Field(min_length=1, max_length=50)
    vendor_pan: str = Field(min_length=10, max_length=10)
    vendor_gstin: Optional[str] = Field(default=None, min_length=15, max_length=15)
    invoice_date: str
    fiscal_year: str = Field(pattern=r"^\d{4}-\d{2}$")
    line_items: List[InvoiceLineItem] = Field(min_length=1)
    subtotal: Decimal = Field(gt=Decimal("0"))
    tax_amount: Decimal = Field(ge=Decimal("0"))
    total_amount: Decimal = Field(gt=Decimal("0"))
    ocr_confidence_score: float = Field(ge=0.0, le=1.0)

    @field_validator("vendor_pan", mode="before")
    @classmethod
    def normalize_pan(cls, v: str) -> str:
        return str(v).strip().upper() if v else ""

    @field_validator("vendor_gstin", mode="before")
    @classmethod
    def normalize_gstin(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        clean = str(v).strip().upper()
        return clean if clean else None

    @model_validator(mode="after")
    def validate_document_math(self) -> "ExtractedInvoicePayload":
        line_items_sum = sum(item.line_total for item in self.line_items)
        max_drift = max(Decimal("0.05"), Decimal(len(self.line_items)) * Decimal("0.01"))
        if abs(self.subtotal - line_items_sum) > max_drift:
            raise ValueError(
                f"Subtotal mismatch: Sum of lines ({line_items_sum}) differs "
                f"from extracted subtotal ({self.subtotal}) beyond drift {max_drift}"
            )

        expected_total = (self.subtotal + self.tax_amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if abs(self.total_amount - expected_total) > max_drift:
            raise ValueError(
                f"Gross total mismatch: Subtotal({self.subtotal}) + Tax({self.tax_amount}) = {expected_total} "
                f"differs from Total({self.total_amount}) beyond drift {max_drift}"
            )
        return self


class TaxFramework(str, Enum):
    INCOME_TAX_ACT_1961 = "INCOME_TAX_ACT_1961"
    INCOME_TAX_ACT_2025 = "INCOME_TAX_ACT_2025"


class CanonicalTDSRule(str, Enum):
    TDS_CONTRACTOR_INDIVIDUAL = "TDS_CONTRACTOR_INDIVIDUAL"
    TDS_CONTRACTOR_COMPANY = "TDS_CONTRACTOR_COMPANY"
    TDS_TECHNICAL_SERVICES = "TDS_TECHNICAL_SERVICES"
    TDS_PROFESSIONAL_SERVICES = "TDS_PROFESSIONAL_SERVICES"
    TDS_PURCHASE_OF_GOODS = "TDS_PURCHASE_OF_GOODS"
    TDS_LOWER_CERTIFICATE = "TDS_LOWER_CERTIFICATE"
    NONE = "NONE"


class PaymentState(str, Enum):
    PENDING = "PENDING"
    READY_FOR_EXECUTION = "READY_FOR_EXECUTION"
    BYPASSED_ZERO_PAYOUT = "BYPASSED_ZERO_PAYOUT"
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    RECONCILED = "RECONCILED"


class ExceptionDisposition(str, Enum):
    AUTOMATICALLY_ADJUSTED = "AUTOMATICALLY_ADJUSTED"
    ROUTED_TO_AP_CLERK_TIER_1 = "ROUTED_TO_AP_CLERK_TIER_1"
    ROUTED_TO_CONTROLLER_TIER_2 = "ROUTED_TO_CONTROLLER_TIER_2"
    ROUTED_TO_CFO_TIER_3 = "ROUTED_TO_CFO_TIER_3"
    HARD_FRAUD_LOCK = "HARD_FRAUD_LOCK"


class VendorBankSecurityStatus(BaseModel):
    model_config = ConfigDict(frozen=True)

    vendor_id: str
    bank_account_number: str
    ifsc_code: str
    risk_policy_id: str = "POL-TREASURY-BNK-MOD-48H"
    policy_type: str = "CONFIGURABLE_ENTERPRISE_RISK_POLICY"
    quarantine_duration_hours: int = 48
    change_count_in_rolling_7_days: int = 1
    is_under_cooling_period: bool = False
    cooling_period_expires_at: Optional[str] = None
    is_hard_locked_suspicious_velocity: bool = False
    lock_reason: Optional[str] = None
    enhanced_approval_required: bool = False
    verification_controls: List[str] = [
        "PENNY_DROP_NAME_MATCH_90PCT",
        "PAN_GSTIN_ENTITY_VALIDATION",
        "OUT_OF_BAND_CALLBACK",
        "MAKER_CHECKER_SEGREGATION",
        "COOLING_PERIOD_FREEZE"
    ]


class StatutoryRuleDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    internal_rule_id: str
    government_act: TaxFramework
    government_section: str
    government_table_item: str
    official_gazette_citation: str
    cbdt_circular_reference: Optional[str] = None
    official_source_uri: str
    effective_from: str
    effective_to: Optional[str] = None
    rule_version: str
    statutory_return_form: str
    statutory_return_field_code: str
    internal_reporting_code: str
    challan_281_code: str
    statutory_rate: Decimal
    statutory_threshold: Decimal = Decimal("0.00")


class TaxCalculationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    applied_section: TDSSection
    taxable_base: Decimal
    taxable_amount_subject_to_tds: Decimal
    tds_rate: Decimal
    tds_deducted: Decimal
    net_base_payable: Decimal
    gst_payable: Decimal
    final_disbursement: Decimal
    is_penal_rate_applied: bool = False
    # Explicit separation of statutory facts, government source, return fields, and internal IDs
    internal_rule_id: str = "RULE-TDS-393-7B"
    tax_framework: TaxFramework = TaxFramework.INCOME_TAX_ACT_2025
    canonical_rule_id: CanonicalTDSRule = CanonicalTDSRule.NONE
    statutory_provision: str = "Section 393(1)"
    government_section: str = "393(1)"
    government_table_item: str = "Table Item 7(b)"
    gazette_citation: str = "Income-tax Act, 2025 (Act No. 4 of 2025)"
    cbdt_circular_reference: Optional[str] = "CBDT Circular No. 23/2017"
    official_source_uri: str = "https://incometaxindia.gov.in/pages/acts/income-tax-act-2025.aspx"
    tax_rule_version: str = "v2025.1-ITA2025-Transition"
    statutory_return_form: str = "Form 26Q"
    statutory_return_field_code: str = "94J"
    form_26q_code: str = "94J"
    internal_reporting_code: str = "393-7B"
    challan_281_code: str = "94J"
    pan_26as_credit_tag: Optional[str] = None
    effective_date: Optional[str] = None
    calculation_version: str = "v2.0-DualAct-DateAware"


class LedgerPosting(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_name: str
    account_code: str
    entry_type: JournalEntryType
    amount: Decimal = Field(gt=Decimal("0"))


class DoubleEntryJournal(BaseModel):
    model_config = ConfigDict(frozen=True)

    transaction_id: str
    invoice_number: str
    timestamp: datetime
    postings: List[LedgerPosting]

    @model_validator(mode="after")
    def verify_ledger_balance(self) -> "DoubleEntryJournal":
        total_debits = sum(p.amount for p in self.postings if p.entry_type == JournalEntryType.DEBIT)
        total_credits = sum(p.amount for p in self.postings if p.entry_type == JournalEntryType.CREDIT)
        if abs(total_debits - total_credits) > Decimal("0.001"):
            raise ValueError(f"Double-entry imbalance: Debits ({total_debits}) != Credits ({total_credits})")
        return self


class Challan281Entry(BaseModel):
    model_config = ConfigDict(frozen=True)

    challan_type: str = "ITNS_281"
    tds_section: str
    nature_of_payment: str
    assessment_year: str
    financial_year: str
    minor_head: str = "200"
    vendor_pan: str
    taxable_amount: Decimal
    tds_amount: Decimal
    statutory_due_date: date


class OpenCreditRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    credit_note_id: str
    available_balance: Decimal = Field(gt=Decimal("0"))


class PaymentInstruction(BaseModel):
    model_config = ConfigDict(frozen=True)

    instruction_id: str
    invoice_number: str
    vendor_id: str
    vendor_pan: str
    fund_account_id: str
    gross_subtotal: Decimal
    tax_amount: Decimal
    tds_withheld: Decimal
    tds_section: TDSSection
    applied_credits_total: Decimal
    net_payout_amount: Decimal
    payout_paise: int
    idempotency_key: str
    requires_zero_payout_hold: bool
    status: PaymentState = PaymentState.PENDING


class KeyRegistryStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    REVOKED = "REVOKED"
    COMPROMISED = "COMPROMISED"
    PERMANENTLY_COMPROMISED = "PERMANENTLY_COMPROMISED"
    RESTORED_AFTER_INVESTIGATION = "RESTORED_AFTER_INVESTIGATION"


class KeyCompromiseOutcome(str, Enum):
    COMPROMISE_CONFIRMED = "COMPROMISE_CONFIRMED"
    COMPROMISE_NOT_SUBSTANTIATED = "COMPROMISE_NOT_SUBSTANTIATED"


class FinancialAdmissibility(str, Enum):
    ADMISSIBLE = "ADMISSIBLE"
    SUSPENDED = "SUSPENDED"
    INVALIDATED = "INVALIDATED"
    REMEDIATED = "REMEDIATED"


class AdjudicatingAuthoritySignature(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: str  # "CISO", "CFO", "EXTERNAL_AUDITOR"
    identity: str
    signing_algorithm: str = "Ed25519"
    public_key_hex: str
    signature_hex: str
    signed_at: str


class CompromiseAdjudicationCertificate(BaseModel):
    model_config = ConfigDict(frozen=True)

    adjudication_id: str
    key_id: str
    outcome: KeyCompromiseOutcome
    incident_reference: str
    compromise_detection_timestamp: str
    decision_effective_timestamp: str
    compromise_window_start: Optional[str] = None
    compromise_window_end: Optional[str] = None
    evidence_manifest_hash: str
    previous_key_registry_state_hash: str
    new_key_registry_state_hash: str
    adjudicating_authorities: List[AdjudicatingAuthoritySignature]
    remediated_with_key_id: Optional[str] = None
    audit_notes: str
    certificate_canonical_hash: str
    certificate_signature: str
    adjudicated_at: str


class OverallVerificationStatus(str, Enum):
    CRYPTOGRAPHICALLY_VALID_AND_ADMISSIBLE = "CRYPTOGRAPHICALLY_VALID_AND_ADMISSIBLE"
    CRYPTOGRAPHICALLY_VALID_BUT_FINANCIALLY_SUSPENDED = "CRYPTOGRAPHICALLY_VALID_BUT_FINANCIALLY_SUSPENDED"
    CRYPTOGRAPHICALLY_VALID_BUT_FINANCIALLY_INVALIDATED = "CRYPTOGRAPHICALLY_VALID_BUT_FINANCIALLY_INVALIDATED"
    CRYPTOGRAPHICALLY_INVALID = "CRYPTOGRAPHICALLY_INVALID"
    UNTRUSTED_SIGNING_KEY = "UNTRUSTED_SIGNING_KEY"
    EMBEDDED_PUBLIC_KEY_TAMPERED = "EMBEDDED_PUBLIC_KEY_TAMPERED"


class CryptographicVerificationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    overall_verification_status: OverallVerificationStatus
    cryptographic_signature_valid: bool
    financial_admissibility: FinancialAdmissibility
    trust_status: str
    adjudication_required: bool
    signing_key_id: str
    canonical_payload_sha256: str
    verifier_status: str
    adjudication_reference: Optional[str] = None
    # Explicitly derived convenience boolean for backwards compatibility
    verified: bool = False


class KeyRegistryEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    key_id: str
    algorithm: str = "Ed25519"
    public_key_hex: str
    status: KeyRegistryStatus = KeyRegistryStatus.ACTIVE
    valid_from: str
    valid_until: str
    revoked_at: Optional[str] = None
    compromise_suspected_at: Optional[str] = None
    adjudication_certificate: Optional[CompromiseAdjudicationCertificate] = None
    root_authority: str = "FinanceAgent-Enterprise-Trust-Anchor-v1"


class DecisionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_id: str
    invoice_number: str
    vendor_id: str
    vendor_pan: str
    fiscal_year: str
    source_document_hash: str
    source_document_uri: Optional[str] = None
    gst_irn: Optional[str] = None
    internal_rule_id: str = "RULE-TDS-393-7B"
    tax_framework: TaxFramework = TaxFramework.INCOME_TAX_ACT_2025
    canonical_rule_id: CanonicalTDSRule = CanonicalTDSRule.NONE
    statutory_provision: str = "Section 393(1)"
    government_section: str = "393(1)"
    government_table_item: str = "Table Item 7(b)"
    gazette_citation: str = "Income-tax Act, 2025 (Act No. 4 of 2025)"
    cbdt_circular_reference: Optional[str] = "CBDT Circular No. 23/2017"
    official_source_uri: str = "https://incometaxindia.gov.in/pages/acts/income-tax-act-2025.aspx"
    tax_rule_version: str = "v2025.1-ITA2025-Transition"
    statutory_return_form: str = "Form 26Q"
    statutory_return_field_code: str = "94J"
    form_26q_code: str = "94J"
    internal_reporting_code: str = "393-7B"
    challan_281_code: str = "94J"
    pan_26as_credit_tag: Optional[str] = None
    calculation_version: str = "v2.0-DualAct-DateAware"
    effective_date: Optional[str] = None
    previous_decision_digest: Optional[str] = None
    reconciliation_evidence: dict
    tds_calculation: dict
    credit_allocation_manifest: List[dict]
    general_ledger_tx_id: str
    payment_instruction: dict
    decision_timestamp: str
    # CFDS-v1 Canonical Financial Decision Serialization & Key Rotation Provenance
    serialization_spec: str = "CFDS-v1/RFC8785"
    canonical_payload_sha256: str = ""
    signature_algorithm: str = "Ed25519-KMS-HSM"
    signing_key_id: str = "kms://asia-south1/finance-decision-signer-ed25519-v1"
    signed_at: str = ""
    key_valid_from: str = "2026-01-01T00:00:00Z"
    key_valid_until: str = "2026-12-31T23:59:59Z"
    public_key_hex: str = ""
    cryptographic_signature: str = ""
    signed_decision_digest: str


# ==============================================================================
# 5 PILLARS: ENTERPRISE FINANCIAL DECISION & AUDIT TRAIL MODELS
# ==============================================================================

class RiskTier(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskAction(str, Enum):
    AUTO_EXECUTE = "AUTO_EXECUTE"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    HITL_APPROVAL_REQUIRED = "HITL_APPROVAL_REQUIRED"
    HARD_BLOCK = "HARD_BLOCK"


class RiskFactor(BaseModel):
    model_config = ConfigDict(frozen=True)

    factor_name: str
    severity: RiskTier
    description: str
    score_impact: int


class PaymentRiskAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    vendor_trust_score: int = Field(ge=0, le=100)
    payment_risk_score: int = Field(ge=0, le=100)
    risk_tier: RiskTier
    evaluated_risk_factors: List[RiskFactor]
    action_recommended: RiskAction
    assessed_at: str


class VendorPointInTimeSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    vendor_id: str
    vendor_name: str
    pan: str
    gstin: Optional[str] = None
    trust_score: int = 95
    bank_account_last4: str
    bank_account_age_hours: int
    bank_verified: bool = True
    contact_email: str
    historical_mean_invoice_amount: Decimal
    current_invoice_amount_multiplier: float
    invoices_in_last_7_days: int
    normal_invoicing_cadence: str = "MONTHLY"


class ContractComplianceStatus(str, Enum):
    MATCHED_COMPLIANT = "MATCHED_COMPLIANT"
    RATE_VARIANCE_BLOCKED = "RATE_VARIANCE_BLOCKED"
    QUANTITY_OVERBILLING_BLOCKED = "QUANTITY_OVERBILLING_BLOCKED"
    UNAUTHORIZED_PO_BLOCKED = "UNAUTHORIZED_PO_BLOCKED"


class ContractPOVerificationState(BaseModel):
    model_config = ConfigDict(frozen=True)

    contract_id: str
    po_number: str
    service_description: str
    contract_rate: Decimal
    po_authorized_quantity: Decimal
    grn_or_timesheet_id: str
    grn_accepted_quantity: Decimal
    billed_quantity: Decimal
    billed_unit_price: Decimal
    contractual_variance_amount: Decimal
    variance_percentage: float
    is_contractually_compliant: bool
    compliance_status: ContractComplianceStatus


class ReconciliationStatus(str, Enum):
    PENDING_EXECUTION = "PENDING_EXECUTION"
    MATCHED_AND_RECONCILED = "MATCHED_AND_RECONCILED"
    UNRECONCILED_EXCEPTION = "UNRECONCILED_EXCEPTION"
    MANUAL_RECONCILIATION_REQUIRED = "MANUAL_RECONCILIATION_REQUIRED"


class AutonomousReconciliationRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    reconciliation_id: str
    invoice_number: str
    payout_id: Optional[str] = None
    bank_utr: Optional[str] = None
    erp_reference_id: str
    journal_transaction_id: str
    disbursed_amount: Decimal
    reconciled_amount: Decimal
    status: ReconciliationStatus
    reconciled_at: Optional[str] = None
    audit_trail: List[str]


class AuditorEvidenceManifest(BaseModel):
    model_config = ConfigDict(frozen=True)

    manifest_id: str
    decision_id: str
    invoice_number: str
    vendor_id: str
    generated_at: str
    invoice_content_hash: str
    contract_hash: str
    po_hash: str
    grn_hash: str
    tax_statutory_provision: str
    gazette_citation: str
    cbdt_circular: Optional[str] = None
    official_source_uri: str
    vendor_trust_score: int
    payment_risk_score: int
    payment_risk_tier: RiskTier
    approval_tier: ApprovalTier
    approver_identity: str
    bank_account_verified: bool
    razorpay_payout_id: Optional[str] = None
    bank_utr: Optional[str] = None
    journal_transaction_id: str
    ledger_balanced: bool
    canonical_payload_sha256: str
    signing_key_id: str
    ed25519_signature: str
    overall_verification_status: OverallVerificationStatus
    replay_uri: str


class FinancialDecision(BaseModel):
    """
    THE MASTER ENTERPRISE FINANCIAL DECISION OBJECT
    A single immutable point-in-time state record unifying all 14 operational domains.
    """
    model_config = ConfigDict(frozen=True)

    # 1. Transaction Identity
    decision_id: str
    invoice_number: str
    vendor_id: str
    fiscal_year: str
    decision_timestamp: str

    # 2. Vendor Point-in-Time State
    vendor_state: VendorPointInTimeSnapshot

    # 3. Contract & PO Lineage State (4-Way Match)
    contract_po_state: ContractPOVerificationState

    # 4. Invoice Extracted State
    invoice_subtotal: Decimal
    invoice_gst: Decimal
    invoice_gross_total: Decimal
    ocr_confidence_score: float

    # 5. Statutory Tax Engine State
    tax_rule_id: str
    statutory_provision: str
    gazette_citation: str
    official_source_uri: str
    tds_rate: Decimal
    tds_deducted: Decimal

    # 6. Credit Conservation & Netting State
    available_credits_at_evaluation: Decimal
    applied_credits: Decimal
    net_payable_amount: Decimal
    unapplied_credits_preserved: Decimal

    # 7. Payment Risk Engine State
    risk_assessment: PaymentRiskAssessment

    # 8. Approval & Governance State
    approval_tier: ApprovalTier
    approval_policy: str = "POLICY-ENTERPRISE-AP-7.2"
    approver_identity: str = "AUTONOMOUS_POLICY_AGENT"

    # 9. Payment Execution State
    payment_state: PaymentState
    payout_id: Optional[str] = None
    idempotency_key: str

    # 10. Accounting & Double-Entry Ledger State
    journal_transaction_id: str
    ledger_balanced: bool = True
    challan_281_code: str = "94J"

    # 11. Autonomous Reconciliation State
    reconciliation: AutonomousReconciliationRecord

    # 12. Evidence & Audit References
    evidence_manifest: AuditorEvidenceManifest

    # 13. Policy & Rule Versions
    policy_version: str = "v2026.4-ENTERPRISE-CONTROL"
    tax_rule_version: str = "v2025.1-ITA2025-Transition"

    # 14. Cryptographic Provenance
    serialization_spec: str = "CFDS-v1/RFC8785"
    canonical_payload_sha256: str
    signing_key_id: str
    signature_algorithm: str = "Ed25519-KMS-HSM"
    ed25519_signature: str
    overall_verification_status: OverallVerificationStatus


# ==============================================================================
# FORENSIC CAUSAL GRAPH, BEHAVIORAL BASELINE & AUDITOR INTELLIGENCE MODELS
# ==============================================================================

class CausalNodeType(str, Enum):
    INVOICE_INGESTION = "INVOICE_INGESTION"
    EVIDENCE_EXTRACTION = "EVIDENCE_EXTRACTION"
    CONTRACT_CLAUSE_CHECK = "CONTRACT_CLAUSE_CHECK"
    STATUTORY_TAX_RULE = "STATUTORY_TAX_RULE"
    ADAPTIVE_RISK_EVALUATION = "ADAPTIVE_RISK_EVALUATION"
    POLICY_GOVERNANCE = "POLICY_GOVERNANCE"
    APPROVAL_GATE = "APPROVAL_GATE"
    DISBURSEMENT_EXECUTION = "DISBURSEMENT_EXECUTION"
    LEDGER_ACCOUNTING = "LEDGER_ACCOUNTING"
    BANK_RECONCILIATION = "BANK_RECONCILIATION"


class CausalGraphNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    node_type: CausalNodeType
    title: str
    description: str
    inputs: Dict[str, Any]
    rule_or_policy_applied: str
    output_fact: str
    status: str  # "PASSED", "BLOCKED", "ESCALATED", "EXECUTED"
    timestamp: str


class CausalGraphEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_node_id: str
    target_node_id: str
    causal_relationship: str  # e.g., "FEEDS_EVIDENCE_TO", "TRIGGERS_TAX_RULE", "ENFORCES_POLICY_GATE"


class CausalDecisionGraph(BaseModel):
    model_config = ConfigDict(frozen=True)

    graph_id: str
    invoice_number: str
    decision_id: str
    root_cause_narrative: str
    nodes: List[CausalGraphNode]
    edges: List[CausalGraphEdge]
    execution_duration_ms: int


class VendorBehavioralBaseline(BaseModel):
    model_config = ConfigDict(frozen=True)

    vendor_id: str
    normal_min_amount: Decimal
    normal_max_amount: Decimal
    historical_mean: Decimal
    historical_std_dev: Decimal
    normal_invoice_day_of_month: int
    day_of_month_tolerance_days: int
    is_amount_anomaly: bool
    is_cadence_anomaly: bool
    amount_z_score: float
    cadence_drift_days: int
    anomaly_explanation: str


class ContractClauseType(str, Enum):
    PAYMENT_ONLY_AFTER_ACCEPTANCE_SIGNOFF = "PAYMENT_ONLY_AFTER_ACCEPTANCE_SIGNOFF"
    FIXED_HOURLY_RATE_CAP = "FIXED_HOURLY_RATE_CAP"
    RETAINER_MONTHLY_CEILING = "RETAINER_MONTHLY_CEILING"
    MILESTONE_DELIVERABLE_PROOF = "MILESTONE_DELIVERABLE_PROOF"


class ContractClauseVerification(BaseModel):
    model_config = ConfigDict(frozen=True)

    clause_id: str
    clause_title: str
    clause_type: ContractClauseType
    contract_stipulation: str
    extracted_evidence: str
    is_satisfied: bool
    block_reason: Optional[str] = None


class ReconciliationExceptionDiagnostic(BaseModel):
    model_config = ConfigDict(frozen=True)

    exception_id: str
    invoice_number: str
    payout_id: str
    disbursed_amount: Decimal
    bank_utr: str
    bank_confirmation_timestamp: str
    erp_reference_id: str
    erp_sync_timestamp: Optional[str]
    root_cause_summary: str
    technical_diagnostic: str
    timeline_events: List[str]
    suggested_resolution: str
    automated_recovery_available: bool


class AuditProofItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    pillar_name: str
    is_verified: bool
    statutory_or_policy_citation: str
    authoritative_proof: str
    evidence_hash_or_ref: str


class AuditorExecutiveProofReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_id: str
    invoice_number: str
    vendor_name: str
    vendor_pan: str
    disbursed_amount: Decimal
    payment_date: str
    control_verification_header: str = "CONTROL VERIFICATION: ALL 9 PROGRAMMED INVARIANTS SATISFIED"
    overall_admissibility: str
    nine_pillars_proof: List[AuditProofItem]
    digital_signature_seal: str
    signing_key_authority: str
    verification_status: OverallVerificationStatus
    auditor_verification_url: str


# ==============================================================================
# EVIDENCE QUALITY SCORING & COUNTERFACTUAL REASONING SCHEMAS
# ==============================================================================

class EvidenceQualityGrade(str, Enum):
    GRADE_A_PLUS_FORENSIC = "GRADE_A_PLUS_FORENSIC"
    GRADE_B_STANDARD = "GRADE_B_STANDARD"
    GRADE_C_DEFICIENT = "GRADE_C_DEFICIENT"
    GRADE_F_UNTRUSTED = "GRADE_F_UNTRUSTED"


class EvidenceDrillDownLeaf(BaseModel):
    model_config = ConfigDict(frozen=True)

    check_name: str
    dimension: str  # "INTEGRITY", "COMPLETENESS", "FRESHNESS", "AUTHORITY"
    is_passed: bool
    score_weight: float
    technical_verification_proof: str
    evidence_pointer_or_hash: str


class EvidenceQualityScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    integrity_score: float = Field(ge=0.0, le=100.0)
    completeness_score: float = Field(ge=0.0, le=100.0)
    freshness_score: float = Field(ge=0.0, le=100.0)
    authority_score: float = Field(ge=0.0, le=100.0)
    composite_quality_score: float = Field(ge=0.0, le=100.0)
    quality_grade: EvidenceQualityGrade
    audit_assessment_summary: str
    drill_down_tree: Dict[str, List[EvidenceDrillDownLeaf]] = {}


class CounterfactualSimulationRequest(BaseModel):
    invoice_number: str
    mutated_inputs: Dict[str, Any]


class CounterfactualSimulationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    simulation_id: str
    invoice_number: str
    original_decision: str
    counterfactual_decision: str
    mutated_inputs: Dict[str, Any]
    downstream_causal_deltas: List[Dict[str, Any]]
    narrative_explanation: str


# ==============================================================================
# MULTI-VARIABLE SENSITIVITY & SCENARIO MATRIX SCHEMAS
# ==============================================================================

class ScenarioInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_name: str
    bank_account_age_hours: int = 720
    invoice_amount: Decimal = Decimal("100000.00")
    applied_credit: Decimal = Decimal("0.00")
    unit_price: Optional[Decimal] = None
    has_acceptance_signoff: bool = True


class ScenarioOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario_name: str
    risk_score: int
    risk_tier: str
    policy_gate: str
    decision_outcome: str
    net_payout_amount: Decimal
    governing_control_rule: str
    audit_explanation: str


class MultiVariableSensitivityRequest(BaseModel):
    invoice_number: str
    scenarios: List[ScenarioInput]


class MultiVariableSensitivityReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    matrix_simulation_id: str
    invoice_number: str
    baseline_scenario: str
    scenario_comparisons: List[ScenarioOutcome]
    sensitivity_summary: str


class SelfHealingReconciliationAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    exception_id: str
    action_type: str
    executed_successfully: bool
    reconciled_utr: str
    audit_trail_entry: str


# ==============================================================================
# FINANCIAL DECISION KNOWLEDGE GRAPH & CLOSED-LOOP LEARNING SCHEMAS
# ==============================================================================

class KnowledgeGraphNodeType(str, Enum):
    VENDOR = "VENDOR"
    CONTRACT = "CONTRACT"
    INVOICE = "INVOICE"
    RISK_SIGNALS = "RISK_SIGNALS"
    DECISION = "DECISION"
    HUMAN_OVERRIDE = "HUMAN_OVERRIDE"
    PAYMENT_DISBURSEMENT = "PAYMENT_DISBURSEMENT"
    BANK_OUTCOME = "BANK_OUTCOME"
    RECONCILIATION = "RECONCILIATION"
    AUDIT_OUTCOME = "AUDIT_OUTCOME"


class KnowledgeGraphEdgeType(str, Enum):
    CAUSAL = "CAUSAL"
    EVIDENTIARY = "EVIDENTIARY"
    STATUTORY = "STATUTORY"
    GOVERNANCE = "GOVERNANCE"
    TREASURY = "TREASURY"
    BANKING = "BANKING"
    ACCOUNTING = "ACCOUNTING"
    AUDIT = "AUDIT"
    FEEDBACK_LOOP = "FEEDBACK_LOOP"


class FinancialKnowledgeGraphNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    node_type: KnowledgeGraphNodeType
    title: str
    stage_index: int  # 1 to 10
    timestamp: str
    properties: Dict[str, Any]
    status: str  # "VERIFIED", "APPROVED", "SETTLED", "RECONCILED", "LEARNED"


class FinancialKnowledgeGraphEdge(BaseModel):
    model_config = ConfigDict(frozen=True)

    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: KnowledgeGraphEdgeType
    relationship: str
    is_feedback_learning_edge: bool = False
    weight: float = 1.0


class FinancialDecisionKnowledgeGraph(BaseModel):
    model_config = ConfigDict(frozen=True)

    graph_id: str
    invoice_number: str
    vendor_id: str
    created_at: str
    is_closed_loop_complete: bool
    nodes: List[FinancialKnowledgeGraphNode]
    edges: List[FinancialKnowledgeGraphEdge]
    knowledge_summary: str


class FeedbackOutcomeType(str, Enum):
    BANK_SETTLED_CONFIRMED = "BANK_SETTLED_CONFIRMED"
    BANK_FAILED_REVERSED = "BANK_FAILED_REVERSED"
    HUMAN_CONTROLLER_APPROVED = "HUMAN_CONTROLLER_APPROVED"
    HUMAN_CONTROLLER_REJECTED = "HUMAN_CONTROLLER_REJECTED"
    RECONCILIATION_BALANCED = "RECONCILIATION_BALANCED"
    AUDIT_INVARIANT_PASSED = "AUDIT_INVARIANT_PASSED"
    AUDIT_INVARIANT_FLAGGED = "AUDIT_INVARIANT_FLAGGED"


class ClosedLoopLearningFeedback(BaseModel):
    model_config = ConfigDict(frozen=True)

    feedback_id: str
    invoice_number: str
    vendor_id: str
    outcome_type: FeedbackOutcomeType
    settlement_latency_ms: int = 420
    bank_utr: Optional[str] = None
    controller_notes: Optional[str] = None
    audit_invariant_reference: Optional[str] = None
    timestamp: str


class LearnedVendorIntelligence(BaseModel):
    model_config = ConfigDict(frozen=True)

    vendor_id: str
    vendor_name: str
    vendor_pan: str
    lifetime_transactions_completed: int
    lifetime_disbursed_total: Decimal
    settlement_reliability_score_pct: float
    historical_dispute_rate_pct: float
    average_settlement_latency_ms: int
    adaptive_risk_discount_pct: float
    auto_approval_velocity_cap: Decimal
    last_learned_timestamp: str
    learned_feedback_events_count: int


# ==============================================================================
# ENTERPRISE STATUTORY, FRAUD & WORKING CAPITAL MODELS (STP + HITL)
# ==============================================================================

class GSTR2BStatus(str, Enum):
    MATCHED_IN_2B = "MATCHED_IN_2B"
    PENDING_SUPPLIER_FILING = "PENDING_SUPPLIER_FILING"
    ITC_INELIGIBLE = "ITC_INELIGIBLE"


class PaymentTermsType(str, Enum):
    NET_15 = "NET_15"
    NET_30 = "NET_30"
    NET_45 = "NET_45"
    NET_60 = "NET_60"
    DISCOUNT_2_10_NET_30 = "2/10_NET_30"


class PaymentTermsSchedule(BaseModel):
    terms_type: PaymentTermsType = PaymentTermsType.NET_30
    terms_description: str = "Net 30 Days Standard Commercial Credit"
    invoice_date: str
    due_date: str
    discount_deadline: Optional[str] = None
    discount_rate_pct: float = 0.0
    potential_discount_savings: Decimal = Decimal("0.00")
    annualized_treasury_yield_pct: float = 0.0
    is_early_discount_available: bool = False


class PennyDropStatus(str, Enum):
    VERIFIED_MATCH = "VERIFIED_MATCH"
    NAME_MISMATCH_SUSPECT = "NAME_MISMATCH_SUSPECT"
    PENDING_NPCI_ACK = "PENDING_NPCI_ACK"
    FAILED = "FAILED"


class PennyDropVerification(BaseModel):
    status: PennyDropStatus
    bank_account_number_last4: str
    ifsc: str
    npci_registered_account_name: str
    vendor_legal_name: str
    pan_name_match_score_pct: float
    transfer_reference_id: str
    verified_at: str


class LineItemPOMatch(BaseModel):
    sku: str
    description: str
    billed_quantity: Decimal
    po_authorized_quantity: Decimal
    billed_unit_price: Decimal
    po_authorized_rate: Decimal
    rate_variance_pct: float
    is_within_tolerance: bool
    is_quantity_compliant: bool
    short_pay_variance_amount: Decimal = Decimal("0.00")


class ExceptionType(str, Enum):
    PO_PRICE_VARIANCE = "PO_PRICE_VARIANCE"
    DUPLICATE_SUSPECT = "DUPLICATE_SUSPECT"
    BANK_COOLING_ACTIVE = "BANK_COOLING_ACTIVE"
    GSTR2B_PENDING_HOLD = "GSTR2B_PENDING_HOLD"
    TAX_PAN_MISMATCH = "TAX_PAN_MISMATCH"


class PolicyExceptionRecord(BaseModel):
    exception_type: ExceptionType
    severity: str = "HIGH"  # CRITICAL, HIGH, MEDIUM
    title: str
    explanation: str
    financial_impact_amount: Decimal
    remediation_options: List[str]  # e.g. ["OVERRIDE", "SHORT_PAY", "REJECT"]


class ERPJournalEntry(BaseModel):
    account_code: str
    account_name: str
    entry_type: JournalEntryType
    amount: Decimal
    currency: str = "INR"
    description: str


class ERPJournalVoucher(BaseModel):
    voucher_id: str
    transaction_ref: str
    posting_date: str
    standard: str = "Ind AS 1 / IFRS Presentation of Financial Statements"
    balanced: bool = True
    entries: List[ERPJournalEntry]
    export_csv_row: str






