import hashlib
import json
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


from services.crypto import CanonicalFinancialDecisionSerializer, EnterpriseKeyRegistry, verify_external_auditor_signature, _ED25519_PRIV, ED25519_PUBLIC_KEY_HEX
from services.ledger import HardenedStatutoryLedgerEngine, LedgerNettingEngine, NettingResult
from services.reconciliation import HardenedReconciliationEngine

class DecisionEngine:
    @classmethod
    def build_immutable_decision_record(
        cls,
        invoice: ExtractedInvoicePayload,
        vendor_id: str,
        tax_result: TaxCalculationResult,
        netting_result: NettingResult,
        journal: DoubleEntryJournal,
        source_document_hash: str,
        reconciliation_evidence: Dict[str, Any],
        fund_account_id: str,
        idempotency_key: str,
        source_document_uri: Optional[str] = None,
        gst_irn: Optional[str] = None,
        previous_decision_digest: Optional[str] = None
    ) -> Tuple[DecisionRecord, PaymentInstruction]:
        import uuid
        from decimal import ROUND_HALF_UP

        now_str = datetime.now(timezone.utc).isoformat()
        decision_id = f"DEC-{invoice.invoice_number}-{uuid.uuid4().hex[:8]}"

        final_payout_amount = netting_result.net_taxable_subtotal
        payout_paise = int((final_payout_amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        is_zero_payout = (payout_paise == 0)

        payment_instruction = PaymentInstruction(
            instruction_id=f"PAY-INST-{uuid.uuid4().hex[:10]}",
            invoice_number=invoice.invoice_number,
            vendor_id=vendor_id,
            vendor_pan=invoice.vendor_pan,
            fund_account_id=fund_account_id,
            gross_subtotal=invoice.subtotal,
            tax_amount=invoice.tax_amount,
            tds_withheld=tax_result.tds_deducted,
            tds_section=tax_result.applied_section,
            applied_credits_total=netting_result.applied_credit_total,
            net_payout_amount=final_payout_amount,
            payout_paise=payout_paise,
            idempotency_key=idempotency_key,
            requires_zero_payout_hold=is_zero_payout,
            status="BYPASSED_ZERO_PAYOUT" if is_zero_payout else "READY_FOR_EXECUTION"
        )

        decision_payload = {
            "decision_id": decision_id,
            "invoice_number": invoice.invoice_number,
            "vendor_id": vendor_id,
            "vendor_pan": invoice.vendor_pan,
            "fiscal_year": invoice.fiscal_year,
            "source_document_hash": source_document_hash,
            "source_document_uri": source_document_uri,
            "gst_irn": gst_irn,
            "tax_framework": tax_result.tax_framework.value,
            "canonical_rule_id": tax_result.canonical_rule_id.value,
            "internal_rule_id": tax_result.internal_rule_id,
            "statutory_provision": tax_result.statutory_provision,
            "government_section": tax_result.government_section,
            "government_table_item": tax_result.government_table_item,
            "gazette_citation": tax_result.gazette_citation,
            "cbdt_circular_reference": tax_result.cbdt_circular_reference,
            "official_source_uri": tax_result.official_source_uri,
            "tax_rule_version": tax_result.tax_rule_version,
            "statutory_return_form": tax_result.statutory_return_form,
            "statutory_return_field_code": tax_result.statutory_return_field_code,
            "form_26q_code": tax_result.form_26q_code,
            "internal_reporting_code": tax_result.internal_reporting_code,
            "challan_281_code": tax_result.challan_281_code,
            "pan_26as_credit_tag": tax_result.pan_26as_credit_tag,
            "calculation_version": tax_result.calculation_version,
            "effective_date": tax_result.effective_date or str(invoice.invoice_date),
            "previous_decision_digest": previous_decision_digest,
            "reconciliation_evidence": reconciliation_evidence,
            "tds_calculation": {
                "section": tax_result.applied_section.value,
                "canonical_rule": tax_result.canonical_rule_id.value,
                "statutory_provision": tax_result.statutory_provision,
                "subtotal_pre_gst": str(invoice.subtotal),
                "tds_rate": str(tax_result.tds_rate),
                "tds_withheld": str(tax_result.tds_deducted),
                "gst_amount": str(invoice.tax_amount),
                "post_tax_payable": str(tax_result.final_disbursement)
            },
            "credit_allocation_manifest": netting_result.credit_allocation_audit,
            "general_ledger_tx_id": journal.transaction_id,
            "payment_instruction": payment_instruction.model_dump(mode="json"),
            "decision_timestamp": now_str
        }

        # CFDS-v1 Canonical Serialization & Deterministic SHA-256 Digest
        canonical_json = CanonicalFinancialDecisionSerializer.serialize(decision_payload)
        canonical_payload_sha256 = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        
        # Asymmetric Ed25519 KMS/HSM Signature
        signature_bytes = _ED25519_PRIV.sign(canonical_payload_sha256.encode("utf-8"))
        cryptographic_signature = signature_bytes.hex()
        
        key_metadata = EnterpriseKeyRegistry.get_key(EnterpriseKeyRegistry.ACTIVE_KEY_ID) or {
            "key_id": EnterpriseKeyRegistry.ACTIVE_KEY_ID,
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_until": "2026-12-31T23:59:59Z"
        }

        decision_record = DecisionRecord(
            decision_id=decision_id,
            invoice_number=invoice.invoice_number,
            vendor_id=vendor_id,
            vendor_pan=invoice.vendor_pan,
            fiscal_year=invoice.fiscal_year,
            source_document_hash=source_document_hash,
            source_document_uri=source_document_uri,
            gst_irn=gst_irn,
            internal_rule_id=tax_result.internal_rule_id,
            tax_framework=tax_result.tax_framework,
            canonical_rule_id=tax_result.canonical_rule_id,
            statutory_provision=tax_result.statutory_provision,
            government_section=tax_result.government_section,
            government_table_item=tax_result.government_table_item,
            gazette_citation=tax_result.gazette_citation,
            cbdt_circular_reference=tax_result.cbdt_circular_reference,
            official_source_uri=tax_result.official_source_uri,
            tax_rule_version=tax_result.tax_rule_version,
            statutory_return_form=tax_result.statutory_return_form,
            statutory_return_field_code=tax_result.statutory_return_field_code,
            form_26q_code=tax_result.form_26q_code,
            internal_reporting_code=tax_result.internal_reporting_code,
            challan_281_code=tax_result.challan_281_code,
            pan_26as_credit_tag=tax_result.pan_26as_credit_tag,
            calculation_version=tax_result.calculation_version,
            effective_date=tax_result.effective_date or str(invoice.invoice_date),
            previous_decision_digest=previous_decision_digest,
            reconciliation_evidence=reconciliation_evidence,
            tds_calculation=decision_payload["tds_calculation"],
            credit_allocation_manifest=netting_result.credit_allocation_audit,
            general_ledger_tx_id=journal.transaction_id,
            payment_instruction=payment_instruction.model_dump(mode="json"),
            decision_timestamp=now_str,
            serialization_spec="CFDS-v1/RFC8785",
            canonical_payload_sha256=canonical_payload_sha256,
            signature_algorithm="Ed25519-KMS-HSM",
            signing_key_id=key_metadata["key_id"],
            signed_at=now_str,
            key_valid_from=key_metadata["valid_from"],
            key_valid_until=key_metadata["valid_until"],
            public_key_hex=ED25519_PUBLIC_KEY_HEX,
            cryptographic_signature=cryptographic_signature,
            signed_decision_digest=canonical_payload_sha256
        )

        return decision_record, payment_instruction
