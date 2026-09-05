from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
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

    @field_validator("quantity", "unit_price", "line_total", mode="before")
    @classmethod
    def reject_binary_float_ingress(cls, v: Any) -> Any:
        if isinstance(v, float):
            raise TypeError(f"Binary float ingress rejected in financial path: {v}. Use Decimal or string.")
        return v

    @field_validator("sku", mode="before")
    @classmethod
    def normalize_sku(cls, v: str) -> str:
        return str(v).strip().upper() if v else ""

    @model_validator(mode="after")
    def validate_line_total(self) -> "InvoiceLineItem":
        expected = (self.quantity * self.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if abs(self.line_total - expected) > Decimal("0.01"):
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

    @field_validator("subtotal", "tax_amount", "total_amount", mode="before")
    @classmethod
    def reject_payload_float_ingress(cls, v: Any) -> Any:
        if isinstance(v, float):
            raise TypeError(f"Binary float ingress rejected in financial payload: {v}. Use Decimal or string.")
        return v

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
    # Existing states (preserved)
    PENDING = "PENDING"
    READY_FOR_EXECUTION = "READY_FOR_EXECUTION"
    BYPASSED_ZERO_PAYOUT = "BYPASSED_ZERO_PAYOUT"
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    RECONCILED = "RECONCILED"

    # Prompt 4 Conceptual States
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    READY_FOR_SUBMISSION = "READY_FOR_SUBMISSION"
    SUBMISSION_PENDING = "SUBMISSION_PENDING"
    PROVIDER_ACKNOWLEDGED = "PROVIDER_ACKNOWLEDGED"
    SETTLEMENT_PENDING = "SETTLEMENT_PENDING"
    SETTLED = "SETTLED"
    AMBIGUOUS = "AMBIGUOUS"
    CANCELLED = "CANCELLED"


class SystemEnvironment(str, Enum):
    PRODUCTION = "PRODUCTION"
    SANDBOX = "SANDBOX"
    TEST = "TEST"
    SIMULATION = "SIMULATION"


def normalize_environment(env: Optional[Any]) -> str:
    """
    Fail-safe environment resolver (Prompt 11 Rule 8).
    Missing or invalid environment must NEVER default to PRODUCTION;
    must fail safe to TEST/SANDBOX. Only explicit 'PRODUCTION' (case-insensitive) is accepted.
    """
    if not env:
        return SystemEnvironment.SANDBOX.value
    clean = str(getattr(env, "value", env)).strip().upper()
    if clean == SystemEnvironment.PRODUCTION.value:
        return SystemEnvironment.PRODUCTION.value
    if clean == SystemEnvironment.SIMULATION.value:
        return SystemEnvironment.SIMULATION.value
    if clean == SystemEnvironment.TEST.value:
        return SystemEnvironment.TEST.value
    if clean == SystemEnvironment.SANDBOX.value:
        return SystemEnvironment.SANDBOX.value
    # Any unrecognized or invalid environment fails safe to SANDBOX
    return SystemEnvironment.SANDBOX.value


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
    policy_version: str = "2026.1"
    rule_version: str = "2026.1"
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
        if total_debits != total_credits:
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


class CreditType(str, Enum):
    GST_CREDIT_NOTE = "GST_CREDIT_NOTE"
    COMMERCIAL_REBATE = "COMMERCIAL_REBATE"
    ADVANCE = "ADVANCE"
    OVERPAYMENT = "OVERPAYMENT"
    SLA_PENALTY = "SLA_PENALTY"
    RETURN_OF_GOODS = "RETURN_OF_GOODS"
    SETTLEMENT_ADJUSTMENT = "SETTLEMENT_ADJUSTMENT"


class CreditReservationState(str, Enum):
    RESERVED = "RESERVED"
    CONSUMED = "CONSUMED"
    RELEASED = "RELEASED"


class CreditAllocationItem(BaseModel):
    model_config = ConfigDict(frozen=False)

    credit_note_id: str
    credit_type: CreditType = CreditType.GST_CREDIT_NOTE
    allocated_amount: Decimal = Field(ge=Decimal("0.00"))


class CreditReservation(BaseModel):
    model_config = ConfigDict(frozen=False)

    reservation_id: str
    invoice_number: str
    vendor_id: str
    requested_amount: Decimal
    reserved_amount: Decimal
    state: CreditReservationState = CreditReservationState.RESERVED
    allocations: List[CreditAllocationItem] = []
    financial_snapshot_hash: str = ""
    version: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class OpenCreditRecord(BaseModel):
    model_config = ConfigDict(frozen=False)

    credit_note_id: str
    original_amount: Optional[Decimal] = None
    available_amount: Optional[Decimal] = None
    reserved_amount: Decimal = Decimal("0.00")
    consumed_amount: Decimal = Decimal("0.00")
    credit_type: CreditType = CreditType.GST_CREDIT_NOTE
    version: int = 1
    vendor_id: Optional[str] = None
    currency: str = "INR"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    # Legacy compatibility input field
    available_balance: Optional[Decimal] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_credit_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            avail = data.get("available_balance")
            orig = data.get("original_amount")
            cur_avail = data.get("available_amount")
            if avail is not None and cur_avail is None:
                avail_dec = Decimal(str(avail))
                data["available_amount"] = avail_dec
                if orig is None:
                    data["original_amount"] = avail_dec
            elif cur_avail is not None and orig is None:
                data["original_amount"] = Decimal(str(cur_avail))
            elif orig is not None and cur_avail is None:
                res = Decimal(str(data.get("reserved_amount", "0.00")))
                cons = Decimal(str(data.get("consumed_amount", "0.00")))
                data["available_amount"] = Decimal(str(orig)) - res - cons
        return data

    @model_validator(mode="after")
    def _verify_credit_conservation(self) -> "OpenCreditRecord":
        if self.original_amount is None:
            if self.available_balance is not None:
                self.original_amount = self.available_balance
                self.available_amount = self.available_balance
            else:
                self.original_amount = Decimal("0.00")
                self.available_amount = Decimal("0.00")
        if self.available_amount is None:
            self.available_amount = self.original_amount - self.reserved_amount - self.consumed_amount
        
        # Enforce Conservation Invariant
        if self.consumed_amount > self.original_amount:
            raise ValueError(
                f"Credit conservation violated for '{self.credit_note_id}': "
                f"consumed ({self.consumed_amount}) > original ({self.original_amount})"
            )
        if (self.reserved_amount + self.consumed_amount) > self.original_amount:
            raise ValueError(
                f"Credit conservation violated for '{self.credit_note_id}': "
                f"reserved ({self.reserved_amount}) + consumed ({self.consumed_amount}) > original ({self.original_amount})"
            )
        return self

    @property
    def current_balance(self) -> Decimal:
        return self.available_amount if self.available_amount is not None else Decimal("0.00")

    def model_post_init(self, __context: Any) -> None:
        self.available_balance = self.available_amount


# Semantic Alias
CreditInstrument = OpenCreditRecord


class PaymentInstruction(BaseModel):
    model_config = ConfigDict(frozen=False)

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
    provider_idempotency_key: Optional[str] = None
    requires_zero_payout_hold: bool
    status: PaymentState = PaymentState.PENDING

    # Prompt 4 Hardened Fields with backward-compatible defaults
    currency: str = "INR"
    financial_snapshot_hash: str = ""
    provider: str = "RAZORPAYX"
    provider_reference: Optional[str] = None
    utr: Optional[str] = None
    version: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_error: Optional[str] = None
    attempt_count: int = 0

    # Prompt 11 Explicit Financial Time Semantics (UTC)
    occurred_at: Optional[str] = None
    received_at: Optional[str] = None
    submitted_at: Optional[str] = None
    settled_at: Optional[str] = None

    # Prompt 7 Trust & Environment Fields
    environment: str = "SANDBOX"
    bank_verification_trust: Optional[str] = None
    manual_override: Optional[Dict[str, Any]] = None

    # Immutable Provider Request Body & Canonical Hash
    provider_request_body: Optional[Dict[str, Any]] = None
    provider_request_hash: Optional[str] = None
    payment_policy_version: str = "2026.1"
    canonicalization_version: str = "CFDS-v1"

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_payment_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # 1. Map gross amount aliases
            if "gross_subtotal" not in data:
                if "gross_amount" in data:
                    data["gross_subtotal"] = Decimal(str(data["gross_amount"]))
                elif "net_payout_amount" in data:
                    data["gross_subtotal"] = Decimal(str(data["net_payout_amount"]))
                elif "settlement_amount" in data:
                    data["gross_subtotal"] = Decimal(str(data["settlement_amount"]))
                else:
                    data["gross_subtotal"] = Decimal("0.00")

            # 2. Map net payout aliases
            if "net_payout_amount" not in data:
                if "settlement_amount" in data:
                    data["net_payout_amount"] = Decimal(str(data["settlement_amount"]))
                elif "approved_amount" in data:
                    data["net_payout_amount"] = Decimal(str(data["approved_amount"]))
                elif "gross_subtotal" in data:
                    data["net_payout_amount"] = Decimal(str(data["gross_subtotal"]))
                else:
                    data["net_payout_amount"] = Decimal("0.00")

            # 3. Derive payout paise
            if "payout_paise" not in data:
                amt = Decimal(str(data["net_payout_amount"]))
                data["payout_paise"] = int((amt * Decimal("100")).quantize(Decimal("1")))

            # 4. Zero payout hold flag
            if "requires_zero_payout_hold" not in data:
                data["requires_zero_payout_hold"] = (data["payout_paise"] < 100)

            # 5. Safe defaults for legacy records
            if "fund_account_id" not in data:
                data["fund_account_id"] = f"fa_legacy_{data.get('vendor_id', 'unspecified')}"
            if "vendor_pan" not in data:
                data["vendor_pan"] = "PANNOTPROVIDED"
            if "tds_section" not in data:
                data["tds_section"] = TDSSection.NONE
            if "tds_withheld" not in data:
                data["tds_withheld"] = Decimal("0.00")
            if "applied_credits_total" not in data:
                data["applied_credits_total"] = Decimal("0.00")
            if "tax_amount" not in data:
                data["tax_amount"] = Decimal("0.00")
            if "idempotency_key" not in data:
                data["idempotency_key"] = f"idemp_legacy_{data.get('instruction_id', 'unknown')}"

            # 6. Fail-safe environment normalization (Prompt 11 Rule 8)
            data["environment"] = normalize_environment(data.get("environment"))

            # 7. Provider idempotency key normalization (RazorpayX 4-36 character contract)
            if not data.get("provider_idempotency_key"):
                raw_idemp = str(data.get("idempotency_key", "")).strip()
                if 4 <= len(raw_idemp) <= 36:
                    data["provider_idempotency_key"] = raw_idemp
                elif len(raw_idemp) > 36:
                    try:
                        data["provider_idempotency_key"] = str(uuid.UUID(hex=raw_idemp[:32]))
                    except Exception:
                        data["provider_idempotency_key"] = raw_idemp[:36]
                else:
                    data["provider_idempotency_key"] = str(uuid.uuid4())
        return data

    # Semantic compatibility properties for Prompt 4 terminology
    @property
    def payment_intent_id(self) -> str:
        return self.instruction_id

    @property
    def invoice_id(self) -> str:
        return self.invoice_number

    @property
    def beneficiary_reference(self) -> str:
        return self.fund_account_id

    @property
    def approved_amount(self) -> Decimal:
        return self.net_payout_amount

    @property
    def state(self) -> PaymentState:
        return self.status


class OutboxEventStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    AMBIGUOUS = "AMBIGUOUS"


class OutboxWorkItem(BaseModel):
    model_config = ConfigDict(frozen=False)

    event_id: str
    event_type: str = "PAYMENT_SUBMISSION"
    aggregate_id: str
    aggregate_version: int = 1
    payload: Dict[str, Any]
    created_at: str
    processing_state: OutboxEventStatus = OutboxEventStatus.PENDING
    attempt_count: int = 0
    idempotency_identity: str
    last_error: Optional[str] = None
    next_attempt_at: Optional[str] = None
    provider_reference: Optional[str] = None
    updated_at: Optional[str] = None


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


class ExtractionMethod(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    OCR_CLOUD_VISION = "OCR_CLOUD_VISION"
    OCR_DOCUMENT_AI = "OCR_DOCUMENT_AI"
    LLM_GEMINI = "LLM_GEMINI"
    HUMAN_CORRECTION = "HUMAN_CORRECTION"


class FieldProvenanceRecord(BaseModel):
    field_name: str
    source_document_hash: str
    page_number: Optional[int] = 1
    bounding_box: Optional[List[float]] = None
    extraction_method: ExtractionMethod = ExtractionMethod.OCR_DOCUMENT_AI
    confidence_score: Optional[float] = 1.0
    raw_extracted_value: Any
    normalized_value: Any
    is_human_corrected: bool = False
    original_extracted_value: Optional[Any] = None
    correction_timestamp: Optional[str] = None
    correction_actor: Optional[str] = None
    correction_reason: Optional[str] = None

    def record_correction(self, corrected_value: Any, actor: str, reason: str, timestamp_iso: Optional[str] = None) -> None:
        """
        Applies a human correction while strictly preserving the original raw extracted value and audit trail.
        """
        if not self.is_human_corrected:
            self.original_extracted_value = self.raw_extracted_value
        self.is_human_corrected = True
        self.normalized_value = corrected_value
        self.correction_actor = actor
        self.correction_reason = reason
        self.correction_timestamp = timestamp_iso or datetime.now(timezone.utc).isoformat()
        self.extraction_method = ExtractionMethod.HUMAN_CORRECTION


class InvoiceDocumentLineage(BaseModel):
    document_hash: str
    document_uri: Optional[str] = None
    ocr_engine: str = "GoogleCloudDocumentAI-v1"
    fields_provenance: Dict[str, FieldProvenanceRecord] = {}

    def add_field(self, record: FieldProvenanceRecord) -> None:
        self.fields_provenance[record.field_name] = record

    def correct_field(self, field_name: str, corrected_value: Any, actor: str, reason: str) -> None:
        if field_name in self.fields_provenance:
            self.fields_provenance[field_name].record_correction(corrected_value, actor, reason)
        else:
            rec = FieldProvenanceRecord(
                field_name=field_name,
                source_document_hash=self.document_hash,
                raw_extracted_value=None,
                normalized_value=corrected_value,
                is_human_corrected=True,
                original_extracted_value=None,
                correction_actor=actor,
                correction_reason=reason,
                correction_timestamp=datetime.now(timezone.utc).isoformat(),
                extraction_method=ExtractionMethod.HUMAN_CORRECTION
            )
            self.fields_provenance[field_name] = rec


class ReplayMode(str, Enum):
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    WHAT_IF_REPLAY = "WHAT_IF_REPLAY"


class ReplayExecutionResult(BaseModel):
    replay_mode: ReplayMode
    decision_id: str
    original_digest: str
    replayed_digest: str
    cryptographically_identical: bool
    is_simulation: bool
    admissible_for_payout: bool
    variance_detected: bool = False
    variance_details: Optional[Dict[str, Any]] = None
    replayed_decision: Dict[str, Any]
    replayed_at: str


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
    reconciliation_evidence: dict = Field(default_factory=dict)
    tds_calculation: dict = Field(default_factory=dict)
    credit_allocation_manifest: List[dict] = Field(default_factory=list)
    general_ledger_tx_id: str = ""
    payment_instruction: dict = Field(default_factory=dict)
    decision_timestamp: str = ""
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
    signed_decision_digest: str = ""
    # Complete Decision Attestation Context & Immutability Envelopes
    schema_version: str = "2026.1"
    po_snapshot_hash: Optional[str] = None
    grn_snapshot_hash: Optional[str] = None
    vendor_snapshot_hash: Optional[str] = None
    matching_policy_version: str = "LEGACY_UNVERSIONED"
    tax_policy_version: str = "LEGACY_UNVERSIONED"
    payment_policy_version: str = "LEGACY_UNVERSIONED"
    retention_policy_version: str = "LEGACY_UNVERSIONED"
    tolerance_policy_version: str = "LEGACY_UNVERSIONED"
    discount_policy_version: str = "LEGACY_UNVERSIONED"
    accounting_policy_version: str = "LEGACY_UNVERSIONED"
    risk_policy_version: str = "LEGACY_UNVERSIONED"
    credit_allocation_hash: Optional[str] = None
    gstr_evidence_hash: Optional[str] = None
    bank_verification_evidence_hash: Optional[str] = None
    ledger_entry_hash: Optional[str] = None
    payment_intent_id: Optional[str] = None
    canonicalization_version: str = "CFDS-v1"


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

# SystemEnvironment is defined above in the core models section
# SystemEnvironment = SystemEnvironment


class GSTR2BStatus(str, Enum):
    # Canonical reconciliation states
    MATCHED = "MATCHED"
    PENDING = "PENDING"
    NOT_FILED = "NOT_FILED"
    PARTIALLY_MATCHED = "PARTIALLY_MATCHED"
    TAX_AMOUNT_MISMATCH = "TAX_AMOUNT_MISMATCH"
    TAXABLE_VALUE_MISMATCH = "TAXABLE_VALUE_MISMATCH"
    GSTIN_MISMATCH = "GSTIN_MISMATCH"
    INVOICE_REFERENCE_MISMATCH = "INVOICE_REFERENCE_MISMATCH"
    AMENDED = "AMENDED"
    CREDIT_NOTE_APPLIED = "CREDIT_NOTE_APPLIED"
    DISPUTED = "DISPUTED"
    TIMEOUT = "TIMEOUT"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    ITC_INELIGIBLE = "ITC_INELIGIBLE"

    # Backward-compatible aliases
    MATCHED_IN_2B = "MATCHED_IN_2B"
    PENDING_SUPPLIER_FILING = "PENDING_SUPPLIER_FILING"


class RetentionLifecycleState(str, Enum):
    CREATED = "CREATED"
    AWAITING_EVIDENCE = "AWAITING_EVIDENCE"
    MATCHED = "MATCHED"
    RELEASE_AUTHORIZED = "RELEASE_AUTHORIZED"
    RELEASED = "RELEASED"
    DISPUTED = "DISPUTED"
    PARTIAL_RELEASE = "PARTIAL_RELEASE"
    EXPIRED = "EXPIRED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    RESOLVED = "RESOLVED"


class FinancialPosition(BaseModel):
    """
    Mathematical Financial Position Domain Separation (Prompt 7).
    Explicitly separates:
      - Commercial Obligation: gross_invoice_amount, base_amount
      - Statutory Tax: gst_amount, tds_amount
      - Netting: credit_amount
      - Retention Escrow: contractual_retention_amount
      - Settlement Policy: immediate_payment_amount
    Strictly enforces:
      immediate_payment_amount + tds_amount + credit_amount + contractual_retention_amount == gross_invoice_amount
    """
    model_config = ConfigDict(frozen=True)

    gross_invoice_amount: Decimal
    base_amount: Decimal
    gst_amount: Decimal
    tds_amount: Decimal
    credit_amount: Decimal = Decimal("0.00")
    contractual_retention_amount: Decimal = Decimal("0.00")
    immediate_payment_amount: Decimal

    @model_validator(mode="after")
    def verify_financial_conservation(self) -> "FinancialPosition":
        total_accounted = (
            self.immediate_payment_amount +
            self.tds_amount +
            self.credit_amount +
            self.contractual_retention_amount
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        expected_gross = self.gross_invoice_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if abs(total_accounted - expected_gross) > Decimal("0.01"):
            raise ValueError(
                f"Financial position conservation violated: "
                f"Immediate ({self.immediate_payment_amount}) + TDS ({self.tds_amount}) + "
                f"Credit ({self.credit_amount}) + Retention ({self.contractual_retention_amount}) = {total_accounted} != Gross ({expected_gross})"
            )
        return self


class RetentionRecord(BaseModel):
    model_config = ConfigDict(frozen=False)

    retention_id: str
    invoice_number: str
    vendor_id: str
    policy_id: str = "POL-GST-RETENTION-CGST16"
    policy_version: str = "2026.1"
    retained_amount: Decimal
    released_amount: Decimal = Decimal("0.00")
    remaining_amount: Decimal
    reason: str
    release_condition: str
    state: RetentionLifecycleState = RetentionLifecycleState.CREATED
    release_history: List[Dict[str, Any]] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


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

    # Prompt 8 Explainable Dynamic Discounting Fields
    simple_annualized_return_pct: float = 0.0
    effective_annualized_return_pct: float = 0.0
    cost_of_capital_pct: Optional[float] = None
    liquidity_cost_pct: Optional[float] = None
    net_economic_benefit: Decimal = Decimal("0.00")
    recommendation: str = "NO_DISCOUNT"
    explanation: str = ""


class PennyDropStatus(str, Enum):
    VERIFIED_MATCH = "VERIFIED_MATCH"
    NAME_MISMATCH_SUSPECT = "NAME_MISMATCH_SUSPECT"
    PENDING_NPCI_ACK = "PENDING_NPCI_ACK"
    FAILED = "FAILED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class PennyDropVerification(BaseModel):
    status: PennyDropStatus
    bank_account_number_last4: str
    ifsc: str
    npci_registered_account_name: str
    vendor_legal_name: str
    pan_name_match_score_pct: float
    transfer_reference_id: str
    verified_at: str

    # Prompt 7 Provenance, Environment, and Multi-Signal Identity Proof
    verification_source: str = "NPCI_PENNY_DROP"
    environment: str = "SANDBOX"
    provider: str = "RAZORPAYX_NPCI"
    trust_level: str = "SANDBOX_TRUST"
    outcome: str = "AUTO_APPROVE"
    manual_override: Optional[Dict[str, Any]] = None
    verification_timestamp: Optional[str] = None

    @property
    def provider_reference(self) -> str:
        return self.transfer_reference_id


class ProcurementAllocationState(str, Enum):
    RESERVED = "RESERVED"
    COMMITTED = "COMMITTED"
    RELEASED = "RELEASED"


class ProcurementAllocationItem(BaseModel):
    model_config = ConfigDict(frozen=False)

    sku: str
    po_line_id: str
    allocated_quantity: Decimal
    unit_price: Decimal
    allocated_amount: Decimal
    po_authorized_quantity: Decimal
    grn_accepted_quantity: Decimal


class ProcurementAllocationRecord(BaseModel):
    model_config = ConfigDict(frozen=False)

    allocation_id: str
    invoice_number: str
    po_number: str
    po_version: int = 1
    grn_number: Optional[str] = None
    grn_version: int = 1
    vendor_id: str
    items: List[ProcurementAllocationItem] = []
    state: ProcurementAllocationState = ProcurementAllocationState.RESERVED
    version: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


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

    # Prompt 6 Cumulative & GRN Fields
    cumulative_allocated_quantity: Decimal = Decimal("0.00")
    grn_authorized_quantity: Optional[Decimal] = None
    cumulative_grn_allocated: Decimal = Decimal("0.00")
    is_po_quantity_compliant: bool = True
    is_grn_quantity_compliant: bool = True


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

    # Prompt 8 Lineage and Posting State
    policy_version: str = "2026.1"
    tax_decision_hash: Optional[str] = None
    credit_allocation_id: Optional[str] = None
    retention_id: Optional[str] = None
    payment_intent_id: Optional[str] = None
    original_entry_id: Optional[str] = None
    reversal_entry_id: Optional[str] = None
    replacement_entry_id: Optional[str] = None
    posting_state: str = "POSTED"

    @property
    def total_debits(self) -> Decimal:
        return sum(
            (e.amount for e in self.entries if e.entry_type == JournalEntryType.DEBIT),
            Decimal("0.00")
        )

    @property
    def total_credits(self) -> Decimal:
        return sum(
            (e.amount for e in self.entries if e.entry_type == JournalEntryType.CREDIT),
            Decimal("0.00")
        )

    @property
    def journal_entries(self) -> List[ERPJournalEntry]:
        return self.entries


# =====================================================================
# PROMPT 10 CONTROL DOMAIN SCHEMAS
# =====================================================================

class DuplicateDisposition(str, Enum):
    BLOCK = "BLOCK"
    REVIEW = "REVIEW"
    ALLOW = "ALLOW"


class DuplicateCheckResult(BaseModel):
    disposition: DuplicateDisposition
    matched_signal: Optional[str] = None  # DOCUMENT_HASH, EXACT_BUSINESS_KEY, NORMALIZED_INVOICE_NUMBER, ECONOMIC_SIMILARITY, NONE
    matched_invoice_number: Optional[str] = None
    matched_vendor_id: Optional[str] = None
    similarity_score: Decimal = Decimal("0.00")
    reason: Optional[str] = None
    is_blocked: bool = False
    requires_review: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StateTransitionRecord(BaseModel):
    transition_id: str
    idempotency_key: str
    from_state: str
    to_state: str
    expected_version: Optional[int] = None
    resulting_version: int
    actor_id: str
    actor_type: str = "SYSTEM"  # SYSTEM, OPERATOR, CONTROLLER, WEBHOOK
    reason_code: Optional[str] = None
    reason_text: Optional[str] = None
    policy_version: str = "2026.1"
    timestamp: str


class WebhookEventRecord(BaseModel):
    event_id: str
    provider: str = "RAZORPAYX"
    event_type: str
    raw_payload_sha256: str
    signature_verified: bool
    processing_status: str  # PROCESSED, DUPLICATE_IGNORED, REJECTED, REVIEW_REQUIRED
    received_at: str
    processed_at: Optional[str] = None
    error_details: Optional[str] = None


class OverrideScope(str, Enum):
    BANK_COOLING_PERIOD = "BANK_COOLING_PERIOD"
    PENNY_DROP_NAME_MISMATCH = "PENNY_DROP_NAME_MISMATCH"
    TOLERANCE_VARIANCE = "TOLERANCE_VARIANCE"
    EARLY_PAYMENT_SCHEDULE = "EARLY_PAYMENT_SCHEDULE"
    DUPLICATE_REVIEW = "DUPLICATE_REVIEW"
    TAX_SECTION_SELECTION = "TAX_SECTION_SELECTION"
    GENERAL_POLICY = "GENERAL_POLICY"


class ManualOverrideRecord(BaseModel):
    override_id: str
    reason: str
    evidence: str
    maker: str
    checker: str
    approval_timestamp: str
    scope: OverrideScope
    expiry: Optional[str] = None
    risk_classification: str = "MEDIUM"  # LOW, MEDIUM, HIGH, CRITICAL
    is_active: bool = True
    target_entity_id: Optional[str] = None
    notes: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_override_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "maker" not in data and "maker_id" in data:
                data["maker"] = data["maker_id"]
            if "checker" not in data and "checker_id" in data:
                data["checker"] = data["checker_id"]
            if "reason" not in data and "justification" in data:
                data["reason"] = data["justification"]
            if "evidence" not in data:
                data["evidence"] = "DOC-MANUAL-OVERRIDE-ATTACHMENT"
            if "approval_timestamp" not in data:
                data["approval_timestamp"] = data.get("created_at") or datetime.now(timezone.utc).isoformat()
        return data

    @property
    def maker_id(self) -> str:
        return self.maker

    @property
    def checker_id(self) -> str:
        return self.checker

    @property
    def justification(self) -> str:
        return self.reason

    def validate_maker_checker(self) -> None:
        """Enforces dual-control rule: maker and checker cannot be the same persona."""
        if not self.maker or not self.checker:
            raise ValueError("Manual override requires both maker and checker identities.")
        if self.maker.strip().lower() == self.checker.strip().lower():
            raise ValueError(
                f"Dual-control violation: Maker '{self.maker}' and checker '{self.checker}' cannot be identical."
            )

    def is_expired(self, current_time: Optional[datetime] = None) -> bool:
        if not self.expiry:
            return False
        now = current_time or datetime.now(timezone.utc)
        try:
            exp_dt = datetime.fromisoformat(self.expiry.replace("Z", "+00:00"))
            return now > exp_dt
        except Exception:
            return False
