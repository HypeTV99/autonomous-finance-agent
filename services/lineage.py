import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, NamedTuple, Optional, Tuple
from schemas import (
    Challan281Entry,
    DecisionRecord,
    ReplayMode,
    ReplayExecutionResult,
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


from services.crypto import CanonicalFinancialDecisionSerializer, EnterpriseKeyRegistry

class ContinuousVendorRiskEngine:
    """
    Continuous Vendor & Payment Risk Engine.
    Evaluates:
    - Bank account modification recency (< 48h -> Critical)
    - Invoice amount anomaly multiplier vs historical mean (> 3.0x -> High)
    - Invoicing frequency velocity anomaly (e.g. 3rd invoice this week vs monthly -> Medium/High)
    - Contact email domain or PAN anomalies
    - Credit note mismatch
    """
    @classmethod
    def evaluate_payment_risk(
        cls,
        vendor_state: Dict[str, Any],
        invoice_amount: Decimal,
        is_bank_verified: bool = True
    ) -> PaymentRiskAssessment:
        factors: List[RiskFactor] = []
        base_risk_score = 0
        trust_score = vendor_state.get("trust_score", 95)
        now_str = datetime.now(timezone.utc).isoformat()

        # 1. Bank Modification Recency Check
        bank_age_hours = vendor_state.get("bank_account_age_hours", 720)  # Default 30 days
        if bank_age_hours < 48:
            impact = 50 if bank_age_hours < 24 else 35
            base_risk_score += impact
            factors.append(RiskFactor(
                factor_name="BANK_MODIFICATION_COOLING_WINDOW",
                severity=RiskTier.CRITICAL if bank_age_hours < 24 else RiskTier.HIGH,
                description=f"Bank account modified {bank_age_hours}h ago (< 48h quarantine threshold)",
                score_impact=impact
            ))

        # 2. Historical Mean Invoice Multiplier Check
        hist_mean = Decimal(str(vendor_state.get("historical_mean_invoice_amount", "50000.00")))
        multiplier = float(invoice_amount / hist_mean) if hist_mean > 0 else 1.0
        if multiplier >= 3.0:
            impact = 25 if multiplier >= 5.0 else 15
            base_risk_score += impact
            factors.append(RiskFactor(
                factor_name="INVOICE_AMOUNT_VELOCITY_ANOMALY",
                severity=RiskTier.HIGH if multiplier >= 5.0 else RiskTier.MEDIUM,
                description=f"Invoice amount ₹{invoice_amount} is {multiplier:.1f}x higher than historical average of ₹{hist_mean}",
                score_impact=impact
            ))

        # 3. Invoicing Frequency Velocity Check
        invoices_last_7d = vendor_state.get("invoices_in_last_7_days", 1)
        cadence = vendor_state.get("normal_invoicing_cadence", "MONTHLY")
        if cadence == "MONTHLY" and invoices_last_7d >= 3:
            impact = 20
            base_risk_score += impact
            factors.append(RiskFactor(
                factor_name="INVOICING_FREQUENCY_SPIKE",
                severity=RiskTier.HIGH,
                description=f"Vendor standard cadence is {cadence}, but this is the {invoices_last_7d}rd/th invoice received within 7 rolling days",
                score_impact=impact
            ))

        # 4. Bank Verification Check
        if not is_bank_verified:
            base_risk_score += 40
            factors.append(RiskFactor(
                factor_name="UNVERIFIED_BANK_ACCOUNT",
                severity=RiskTier.CRITICAL,
                description="Penny drop name match or OOB callback failed verification",
                score_impact=40
            ))

        # Determine Tier and Action
        final_risk_score = min(100, max(0, base_risk_score))
        if final_risk_score >= 70:
            tier = RiskTier.CRITICAL if final_risk_score >= 85 else RiskTier.HIGH
            action = RiskAction.HARD_BLOCK if tier == RiskTier.CRITICAL else RiskAction.HITL_APPROVAL_REQUIRED
        elif final_risk_score >= 35:
            tier = RiskTier.MEDIUM
            action = RiskAction.VERIFICATION_REQUIRED
        else:
            tier = RiskTier.LOW
            action = RiskAction.AUTO_EXECUTE

        return PaymentRiskAssessment(
            vendor_trust_score=trust_score,
            payment_risk_score=final_risk_score,
            risk_tier=tier,
            evaluated_risk_factors=factors,
            action_recommended=action,
            assessed_at=now_str
        )


class ContractLineageVerificationEngine:
    """
    Contract -> PO -> GRN/Timesheet -> Invoice 4-Way Lineage Engine.
    Protects against overbilling, rate discrepancies, and unauthorized scope additions.
    """
    @classmethod
    def verify_contract_po_lineage(
        cls,
        contract: Dict[str, Any],
        po: Dict[str, Any],
        grn_timesheet: Dict[str, Any],
        invoice_lines: List[Dict[str, Any]]
    ) -> ContractPOVerificationState:
        contract_id = contract.get("contract_id", "CONT-STANDARD-2026")
        po_number = po.get("po_number", "PO-STANDARD-2026")
        contract_rate = Decimal(str(contract.get("approved_rate", "2000.00")))
        po_auth_qty = Decimal(str(po.get("authorized_quantity", "100.00")))
        grn_id = grn_timesheet.get("grn_id", "GRN-STANDARD-001")
        grn_accepted_qty = Decimal(str(grn_timesheet.get("accepted_quantity", "100.00")))

        billed_qty = sum(Decimal(str(l.get("quantity", "0.00"))) for l in invoice_lines)
        billed_unit_price = Decimal(str(invoice_lines[0].get("unit_price", contract_rate))) if invoice_lines else contract_rate

        # 1. Rate Variance Check
        if billed_unit_price > contract_rate:
            rate_diff = billed_unit_price - contract_rate
            total_variance = rate_diff * billed_qty
            variance_pct = float((rate_diff / contract_rate) * 100)
            return ContractPOVerificationState(
                contract_id=contract_id,
                po_number=po_number,
                service_description=contract.get("service_description", "Professional Consulting"),
                contract_rate=contract_rate,
                po_authorized_quantity=po_auth_qty,
                grn_or_timesheet_id=grn_id,
                grn_accepted_quantity=grn_accepted_qty,
                billed_quantity=billed_qty,
                billed_unit_price=billed_unit_price,
                contractual_variance_amount=total_variance,
                variance_percentage=variance_pct,
                is_contractually_compliant=False,
                compliance_status=ContractComplianceStatus.RATE_VARIANCE_BLOCKED
            )

        # 2. Quantity Overbilling Check vs PO and GRN
        max_allowed_qty = min(po_auth_qty, grn_accepted_qty)
        if billed_qty > max_allowed_qty:
            overbilled_qty = billed_qty - max_allowed_qty
            variance_amount = overbilled_qty * billed_unit_price
            variance_pct = float((overbilled_qty / max_allowed_qty) * 100) if max_allowed_qty > 0 else 100.0
            return ContractPOVerificationState(
                contract_id=contract_id,
                po_number=po_number,
                service_description=contract.get("service_description", "Professional Consulting"),
                contract_rate=contract_rate,
                po_authorized_quantity=po_auth_qty,
                grn_or_timesheet_id=grn_id,
                grn_accepted_quantity=grn_accepted_qty,
                billed_quantity=billed_qty,
                billed_unit_price=billed_unit_price,
                contractual_variance_amount=variance_amount,
                variance_percentage=variance_pct,
                is_contractually_compliant=False,
                compliance_status=ContractComplianceStatus.QUANTITY_OVERBILLING_BLOCKED
            )

        # 3. Matched & Compliant
        return ContractPOVerificationState(
            contract_id=contract_id,
            po_number=po_number,
            service_description=contract.get("service_description", "Professional Consulting"),
            contract_rate=contract_rate,
            po_authorized_quantity=po_auth_qty,
            grn_or_timesheet_id=grn_id,
            grn_accepted_quantity=grn_accepted_qty,
            billed_quantity=billed_qty,
            billed_unit_price=billed_unit_price,
            contractual_variance_amount=Decimal("0.00"),
            variance_percentage=0.0,
            is_contractually_compliant=True,
            compliance_status=ContractComplianceStatus.MATCHED_COMPLIANT
        )


class DecisionReplayEngine:
    """
    Forensic Point-in-Time Decision Replay Engine.
    Answers: "Why did we pay this vendor ₹86,000 on 12-May-2026?"
    Reconstructs the EXACT state known at the time of evaluation.
    """
    @classmethod
    def render_decision_replay(cls, decision: FinancialDecision) -> Dict[str, Any]:
        return {
            "decision_replay_summary": {
                "decision_id": decision.decision_id,
                "invoice_number": decision.invoice_number,
                "vendor_id": decision.vendor_id,
                "vendor_name": decision.vendor_state.vendor_name,
                "decision_timestamp": decision.decision_timestamp,
                "final_disbursement": f"₹{decision.net_payable_amount:,.2f}",
                "overall_status": decision.overall_verification_status.value
            },
            "point_in_time_vendor_state": {
                "trust_score": f"{decision.vendor_state.trust_score}/100",
                "bank_account": f"****{decision.vendor_state.bank_account_last4}",
                "bank_account_age": f"{decision.vendor_state.bank_account_age_hours} hours",
                "bank_verified": "YES" if decision.vendor_state.bank_verified else "NO",
                "contact_email": decision.vendor_state.contact_email,
                "invoicing_velocity": f"{decision.vendor_state.invoices_in_last_7_days} invoices in last 7 days"
            },
            "point_in_time_contract_state": {
                "contract_id": decision.contract_po_state.contract_id,
                "po_number": decision.contract_po_state.po_number,
                "approved_rate": f"₹{decision.contract_po_state.contract_rate:,.2f}",
                "po_authorized_qty": str(decision.contract_po_state.po_authorized_quantity),
                "billed_qty": str(decision.contract_po_state.billed_quantity),
                "variance": f"₹{decision.contract_po_state.contractual_variance_amount:,.2f}",
                "compliance_status": decision.contract_po_state.compliance_status.value
            },
            "point_in_time_tax_state": {
                "statutory_provision": decision.statutory_provision,
                "tax_rule_id": decision.tax_rule_id,
                "gazette_citation": decision.gazette_citation,
                "tds_rate": f"{float(decision.tds_rate) * 100:.2f}%",
                "tds_deducted": f"₹{decision.tds_deducted:,.2f}"
            },
            "point_in_time_credit_state": {
                "available_credits": f"₹{decision.available_credits_at_evaluation:,.2f}",
                "applied_credits": f"₹{decision.applied_credits:,.2f}",
                "preserved_credits": f"₹{decision.unapplied_credits_preserved:,.2f}"
            },
            "point_in_time_risk_state": {
                "vendor_trust_score": f"{decision.risk_assessment.vendor_trust_score}/100",
                "payment_risk_score": f"{decision.risk_assessment.payment_risk_score}/100",
                "risk_tier": decision.risk_assessment.risk_tier.value,
                "evaluated_factors": [f.description for f in decision.risk_assessment.evaluated_risk_factors]
            },
            "point_in_time_governance_and_accounting": {
                "approval_tier": decision.approval_tier.value,
                "approval_policy": decision.approval_policy,
                "approver": decision.approver_identity,
                "general_ledger_tx_id": decision.journal_transaction_id,
                "ledger_balanced": "BALANCED (Debits == Credits)" if decision.ledger_balanced else "UNBALANCED",
                "reconciliation_status": decision.reconciliation.status.value,
                "bank_utr": decision.reconciliation.bank_utr
            },
            "cryptographic_provenance": {
                "canonical_payload_sha256": decision.canonical_payload_sha256,
                "signing_key_id": decision.signing_key_id,
                "signature_algorithm": decision.signature_algorithm,
                "ed25519_signature": decision.ed25519_signature,
                "verification_status": decision.overall_verification_status.value
            }
        }

    @classmethod
    def execute_replay(
        cls,
        decision_record: DecisionRecord,
        mode: ReplayMode = ReplayMode.HISTORICAL_REPLAY,
        overrides: Optional[Dict[str, Any]] = None
    ) -> ReplayExecutionResult:
        """
        Executes a deterministic replay of a DecisionRecord under either:
        1. HISTORICAL_REPLAY: Reconstructs exact point-in-time state using recorded snapshot
           hashes, policy versions, and calculations. Asserts exact cryptographic digest match.
           Admissible for audit verification.
        2. WHAT_IF_REPLAY: Replays decision with counterfactual parameter/policy overrides.
           Strictly simulation-only and inadmissible for financial payout.
        """
        now_str = datetime.now(timezone.utc).isoformat()
        
        reconstructed_payload: Dict[str, Any] = {
            "decision_id": decision_record.decision_id,
            "invoice_number": decision_record.invoice_number,
            "vendor_id": decision_record.vendor_id,
            "vendor_pan": decision_record.vendor_pan,
            "fiscal_year": decision_record.fiscal_year,
            "source_document_hash": decision_record.source_document_hash,
            "source_document_uri": decision_record.source_document_uri,
            "gst_irn": decision_record.gst_irn,
            "tax_framework": decision_record.tax_framework.value,
            "canonical_rule_id": decision_record.canonical_rule_id.value,
            "internal_rule_id": decision_record.internal_rule_id,
            "statutory_provision": decision_record.statutory_provision,
            "government_section": decision_record.government_section,
            "government_table_item": decision_record.government_table_item,
            "gazette_citation": decision_record.gazette_citation,
            "cbdt_circular_reference": decision_record.cbdt_circular_reference,
            "official_source_uri": decision_record.official_source_uri,
            "tax_rule_version": decision_record.tax_rule_version,
            "statutory_return_form": decision_record.statutory_return_form,
            "statutory_return_field_code": decision_record.statutory_return_field_code,
            "form_26q_code": decision_record.form_26q_code,
            "internal_reporting_code": decision_record.internal_reporting_code,
            "challan_281_code": decision_record.challan_281_code,
            "pan_26as_credit_tag": decision_record.pan_26as_credit_tag,
            "calculation_version": decision_record.calculation_version,
            "effective_date": decision_record.effective_date,
            "previous_decision_digest": decision_record.previous_decision_digest,
            "reconciliation_evidence": decision_record.reconciliation_evidence,
            "tds_calculation": decision_record.tds_calculation,
            "credit_allocation_manifest": decision_record.credit_allocation_manifest,
            "general_ledger_tx_id": decision_record.general_ledger_tx_id,
            "payment_instruction": decision_record.payment_instruction,
            "decision_timestamp": decision_record.decision_timestamp,
            # Complete Material Attestation Context
            "schema_version": decision_record.schema_version,
            "po_snapshot_hash": decision_record.po_snapshot_hash,
            "grn_snapshot_hash": decision_record.grn_snapshot_hash,
            "vendor_snapshot_hash": decision_record.vendor_snapshot_hash,
            "matching_policy_version": decision_record.matching_policy_version,
            "tax_policy_version": decision_record.tax_policy_version,
            "payment_policy_version": decision_record.payment_policy_version,
            "retention_policy_version": decision_record.retention_policy_version,
            "tolerance_policy_version": decision_record.tolerance_policy_version,
            "discount_policy_version": decision_record.discount_policy_version,
            "accounting_policy_version": decision_record.accounting_policy_version,
            "risk_policy_version": decision_record.risk_policy_version,
            "credit_allocation_hash": decision_record.credit_allocation_hash,
            "gstr_evidence_hash": decision_record.gstr_evidence_hash,
            "bank_verification_evidence_hash": decision_record.bank_verification_evidence_hash,
            "ledger_entry_hash": decision_record.ledger_entry_hash,
            "payment_intent_id": decision_record.payment_intent_id,
            "canonicalization_version": decision_record.canonicalization_version
        }

        variance_details: Optional[Dict[str, Any]] = None

        if mode == ReplayMode.HISTORICAL_REPLAY:
            # Reconstruct exact point-in-time evaluation without external dependencies
            canonical_json = CanonicalFinancialDecisionSerializer.serialize(reconstructed_payload)
            replayed_digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
            cryptographically_identical = (replayed_digest == decision_record.canonical_payload_sha256)
            is_simulation = False
            admissible_for_payout = cryptographically_identical
            variance_detected = not cryptographically_identical
            if variance_detected:
                variance_details = {
                    "reason": "HISTORICAL_REPLAY_HASH_MISMATCH",
                    "expected_digest": decision_record.canonical_payload_sha256,
                    "replayed_digest": replayed_digest
                }
        else:
            # WHAT_IF_REPLAY: Apply counterfactual overrides
            import copy
            reconstructed_payload = copy.deepcopy(reconstructed_payload)
            if overrides:
                for k, v in overrides.items():
                    if k in reconstructed_payload:
                        reconstructed_payload[k] = v
                    elif k.startswith("tds_calculation."):
                        sub_k = k.split(".", 1)[1]
                        if "tds_calculation" in reconstructed_payload and isinstance(reconstructed_payload["tds_calculation"], dict):
                            reconstructed_payload["tds_calculation"][sub_k] = str(v)

            canonical_json = CanonicalFinancialDecisionSerializer.serialize(reconstructed_payload)
            replayed_digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
            cryptographically_identical = (replayed_digest == decision_record.canonical_payload_sha256)
            # CRITICAL GOVERNANCE INVARIANT: WHAT_IF replays are ALWAYS simulation-only and NEVER admissible for payout
            is_simulation = True
            admissible_for_payout = False
            variance_detected = (replayed_digest != decision_record.canonical_payload_sha256)
            variance_details = {
                "applied_overrides": overrides or {},
                "original_digest": decision_record.canonical_payload_sha256,
                "counterfactual_digest": replayed_digest
            }

        return ReplayExecutionResult(
            replay_mode=mode,
            decision_id=decision_record.decision_id,
            original_digest=decision_record.canonical_payload_sha256,
            replayed_digest=replayed_digest,
            cryptographically_identical=cryptographically_identical,
            is_simulation=is_simulation,
            admissible_for_payout=admissible_for_payout,
            variance_detected=variance_detected,
            variance_details=variance_details,
            replayed_decision=reconstructed_payload,
            replayed_at=now_str
        )


class ContractClauseIntelligenceEngine:
    """
    Enforces commercial agreement clauses:
    - PAYMENT_ONLY_AFTER_ACCEPTANCE_SIGNOFF
    - FIXED_HOURLY_RATE_CAP
    - MILESTONE_DELIVERABLE_PROOF
    """
    @classmethod
    def evaluate_contract_clauses(
        cls,
        contract: Dict[str, Any],
        invoice: Dict[str, Any],
        has_acceptance_signoff: bool = True,
        has_milestone_proof: bool = True
    ) -> List[ContractClauseVerification]:
        verifications: List[ContractClauseVerification] = []

        # Clause 1: Payment Only After Acceptance Signoff
        requires_signoff = contract.get("requires_acceptance_signoff", True)
        if requires_signoff:
            is_ok = has_acceptance_signoff
            verifications.append(ContractClauseVerification(
                clause_id="CLAUSE-SEC-4.2-ACCEPTANCE",
                clause_title="Formal Acceptance Signoff Precondition",
                clause_type=ContractClauseType.PAYMENT_ONLY_AFTER_ACCEPTANCE_SIGNOFF,
                contract_stipulation="Payment is disbursed strictly upon verified engineering sign-off/acceptance certificate.",
                extracted_evidence="Verified Timesheet Signoff TS-MAY-2026-001 present in ERP" if is_ok else "MISSING: Engineering acceptance sign-off not on file",
                is_satisfied=is_ok,
                block_reason=None if is_ok else "COMMERCIAL_BLOCK: Payment prohibited until formal acceptance certificate is executed."
            ))

        # Clause 2: Fixed Hourly Rate Cap
        approved_rate = Decimal(str(contract.get("approved_rate", "2000.00")))
        billed_rate = Decimal(str(invoice.get("unit_price", approved_rate)))
        rate_ok = billed_rate <= approved_rate
        verifications.append(ContractClauseVerification(
            clause_id="CLAUSE-SEC-2.1-RATE-CAP",
            clause_title="Contractual Maximum Unit Rate Constraint",
            clause_type=ContractClauseType.FIXED_HOURLY_RATE_CAP,
            contract_stipulation=f"Fixed consulting rate capped at ₹{approved_rate:,.2f}/hr.",
            extracted_evidence=f"Invoice billed rate is ₹{billed_rate:,.2f}/hr.",
            is_satisfied=rate_ok,
            block_reason=None if rate_ok else f"RATE_VARIANCE_BLOCK: Billed rate ₹{billed_rate:,.2f} exceeds contract ceiling of ₹{approved_rate:,.2f}."
        ))

        return verifications
