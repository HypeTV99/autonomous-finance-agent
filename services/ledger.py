import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, NamedTuple, Optional, Tuple
from schemas import (
    Challan281Entry,
    DecisionRecord,
    DoubleEntryJournal,
    ExtractedInvoicePayload,
    JournalEntryType,
    LedgerPosting,
    OpenCreditRecord,
    PaymentInstruction,
    TaxCalculationResult,
    TDSSection,
    PaymentRiskAssessment,
    RiskTier,
    RiskAction,
    RiskFactor,
    ContractPOVerificationState,
    ContractComplianceStatus,
    AutonomousReconciliationRecord,
    ReconciliationStatus,
    AuditorEvidenceManifest,
    FinancialDecision,
    VendorPointInTimeSnapshot,
    ApprovalTier,
    OverallVerificationStatus,
    CausalNodeType,
    CausalGraphNode,
    CausalGraphEdge,
    CausalDecisionGraph,
    VendorBehavioralBaseline,
    ContractClauseType,
    ContractClauseVerification,
    ReconciliationExceptionDiagnostic,
    AuditProofItem,
    AuditorExecutiveProofReport,
    PaymentState,
    EvidenceQualityGrade,
    EvidenceQualityScore,
    EvidenceDrillDownLeaf,
    CounterfactualSimulationRequest,
    CounterfactualSimulationResult,
    ScenarioInput,
    ScenarioOutcome,
    MultiVariableSensitivityReport,
    SelfHealingReconciliationAction,
    KnowledgeGraphNodeType,
    KnowledgeGraphEdgeType,
    FinancialKnowledgeGraphNode,
    FinancialKnowledgeGraphEdge,
    FinancialDecisionKnowledgeGraph,
    FeedbackOutcomeType,
    ClosedLoopLearningFeedback,
    LearnedVendorIntelligence
)
from tax_engine import StatutoryComplianceTaxEngine as ComplianceTaxEngine



class NettingResult(NamedTuple):
    original_subtotal: Decimal
    applied_credit_total: Decimal
    net_taxable_subtotal: Decimal
    consumed_credit_ids: List[str]
    remaining_unapplied_credits: Decimal
    requires_zero_payout_hold: bool
    updated_open_credit_records: List[OpenCreditRecord] = []
    credit_allocation_audit: List[Dict[str, Any]] = []


class LedgerNettingEngine:
    @staticmethod
    def apply_credits_and_advances(
        post_tax_payable: Decimal,
        open_credits: List[OpenCreditRecord]
    ) -> NettingResult:
        remaining_payable = post_tax_payable
        total_applied_credit = Decimal("0.00")
        consumed_ids: List[str] = []
        updated_records: List[OpenCreditRecord] = []
        audit_trail: List[Dict[str, Any]] = []

        # Sort Largest-First for priority netting
        for credit in sorted(open_credits, key=lambda c: c.available_balance, reverse=True):
            if credit.available_balance <= Decimal("0.00"):
                continue

            if remaining_payable <= Decimal("0.00"):
                # Untouched credit note: preserve original credit note ID and balance
                updated_records.append(credit)
                audit_trail.append({
                    "credit_note_id": credit.credit_note_id,
                    "original_balance": str(credit.available_balance),
                    "applied_amount": "0.00",
                    "remaining_balance": str(credit.available_balance),
                    "status": "UNTOUCHED"
                })
                continue

            if credit.available_balance <= remaining_payable:
                # Fully consumed credit note
                applied_amount = credit.available_balance
                total_applied_credit += applied_amount
                remaining_payable -= applied_amount
                consumed_ids.append(f"{credit.credit_note_id} (Rs.{applied_amount})")
                audit_trail.append({
                    "credit_note_id": credit.credit_note_id,
                    "original_balance": str(credit.available_balance),
                    "applied_amount": str(applied_amount),
                    "remaining_balance": "0.00",
                    "status": "FULLY_CONSUMED"
                })
            else:
                # Partially consumed credit note: PRESERVE EXACT ORIGINAL CREDIT NOTE ID
                applied_amount = remaining_payable
                remainder_balance = credit.available_balance - applied_amount
                total_applied_credit += applied_amount
                remaining_payable = Decimal("0.00")
                consumed_ids.append(f"{credit.credit_note_id} (Rs.{applied_amount})")
                updated_records.append(OpenCreditRecord(credit_note_id=credit.credit_note_id, available_balance=remainder_balance))
                audit_trail.append({
                    "credit_note_id": credit.credit_note_id,
                    "original_balance": str(credit.available_balance),
                    "applied_amount": str(applied_amount),
                    "remaining_balance": str(remainder_balance),
                    "status": "PARTIALLY_CONSUMED"
                })

        total_unapplied = sum(r.available_balance for r in updated_records)

        return NettingResult(
            original_subtotal=post_tax_payable,
            applied_credit_total=total_applied_credit,
            net_taxable_subtotal=remaining_payable,  # Represents net final payout after credit offset
            consumed_credit_ids=consumed_ids,
            remaining_unapplied_credits=total_unapplied,
            requires_zero_payout_hold=(remaining_payable == Decimal("0.00")),
            updated_open_credit_records=updated_records,
            credit_allocation_audit=audit_trail
        )


class HardenedStatutoryLedgerEngine:
    @staticmethod
    def get_challan_due_date(transaction_date: date) -> date:
        year = transaction_date.year
        month = transaction_date.month
        return date(year, 4, 30) if month == 3 else date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 7)

    @classmethod
    def generate_accounting_records(
        cls,
        invoice_number: str,
        vendor_pan: str,
        fiscal_year: str,
        gross_subtotal: Decimal,
        applied_credits: Decimal,
        tax_result: TaxCalculationResult,
        gst_amount: Decimal,
        execution_timestamp: Optional[datetime] = None
    ) -> Tuple[DoubleEntryJournal, Challan281Entry]:
        now = execution_timestamp or datetime.now(timezone.utc)
        txn_id = f"TXN-GL-{int(now.timestamp())}"

        final_payout_after_credits = (tax_result.final_disbursement - applied_credits).quantize(Decimal("0.01"))
        
        postings: List[LedgerPosting] = [
            LedgerPosting(account_name="Vendor Operating Expense", account_code="EXP-5001", entry_type=JournalEntryType.DEBIT, amount=gross_subtotal)
        ]
        if gst_amount > Decimal("0.00"):
            postings.append(LedgerPosting(account_name="Input GST Tax Receivable", account_code="AST-1402", entry_type=JournalEntryType.DEBIT, amount=gst_amount))

        if final_payout_after_credits > Decimal("0.00"):
            postings.append(LedgerPosting(account_name="RazorpayX Payout Clearing", account_code="LIAB-2100", entry_type=JournalEntryType.CREDIT, amount=final_payout_after_credits))

        if applied_credits > Decimal("0.00"):
            postings.append(LedgerPosting(account_name="Vendor Open Credit Balance Offset", account_code="AST-1409", entry_type=JournalEntryType.CREDIT, amount=applied_credits))

        if tax_result.tds_deducted > Decimal("0.00"):
            postings.append(LedgerPosting(account_name="TDS Statutory Withholding Payable", account_code="LIAB-2200", entry_type=JournalEntryType.CREDIT, amount=tax_result.tds_deducted))

        journal = DoubleEntryJournal(transaction_id=txn_id, invoice_number=invoice_number, timestamp=now, postings=postings)
        
        # Robust fiscal year parsing
        import re
        fy_match = re.search(r"(\d{4})", fiscal_year)
        start_yr = int(fy_match.group(1)) if fy_match else (now.year if now.month >= 4 else now.year - 1)
        assessment_year = f"{start_yr + 1}-{str(start_yr + 2)[-2:]}"

        challan = Challan281Entry(
            tds_section=tax_result.applied_section.value,
            nature_of_payment=tax_result.applied_section.name,
            assessment_year=assessment_year,
            financial_year=fiscal_year,
            vendor_pan=vendor_pan,
            taxable_amount=tax_result.taxable_amount_subject_to_tds,
            tds_amount=tax_result.tds_deducted,
            statutory_due_date=cls.get_challan_due_date(now.date())
        )
        return journal, challan

    @classmethod
    def generate_reversal_records(cls, original_journal: DoubleEntryJournal) -> DoubleEntryJournal:
        now = datetime.now(timezone.utc)
        reversal_postings = [
            LedgerPosting(
                account_name=f"REVERSAL - {p.account_name}",
                account_code=p.account_code,
                entry_type=JournalEntryType.CREDIT if p.entry_type == JournalEntryType.DEBIT else JournalEntryType.DEBIT,
                amount=p.amount
            )
            for p in original_journal.postings
        ]
        return DoubleEntryJournal(
            transaction_id=f"REV-{original_journal.transaction_id}",
            invoice_number=original_journal.invoice_number,
            timestamp=now,
            postings=reversal_postings
        )
