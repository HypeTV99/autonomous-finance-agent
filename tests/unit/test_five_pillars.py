from decimal import Decimal
from datetime import datetime, timezone
from compliance_engine import (
    ContinuousVendorRiskEngine, ContractLineageVerificationEngine,
    AutonomousReconciliationEngine, DecisionReplayEngine, AuditorEvidencePackService,
    CanonicalFinancialDecisionSerializer
)
from schemas import (
    RiskTier, RiskAction, ContractComplianceStatus, ReconciliationStatus,
    ApprovalTier, PaymentState, OverallVerificationStatus, FinancialDecision,
    VendorPointInTimeSnapshot, ContractPOVerificationState, PaymentRiskAssessment,
    AutonomousReconciliationRecord, AuditorEvidenceManifest
)

# ------------------------------------------------------------------------------
# 1. TEST: DECISION REPLAY POINT-IN-TIME RECONSTRUCTION
# ------------------------------------------------------------------------------
def test_decision_replay_point_in_time_reconstruction():
    vendor_state = VendorPointInTimeSnapshot(
        vendor_id="VEND-ALPHA-01", vendor_name="Alpha Tech", pan="AAACA1234T",
        trust_score=91, bank_account_last4="4821", bank_account_age_hours=720,
        bank_verified=True, contact_email="bill@alpha.com",
        historical_mean_invoice_amount=Decimal("50000.00"),
        current_invoice_amount_multiplier=1.72, invoices_in_last_7_days=1
    )
    contract_state = ContractPOVerificationState(
        contract_id="CONT-01", po_number="PO-884", service_description="Consulting",
        contract_rate=Decimal("2000.00"), po_authorized_quantity=Decimal("50.00"),
        grn_or_timesheet_id="TS-01", grn_accepted_quantity=Decimal("50.00"),
        billed_quantity=Decimal("50.00"), billed_unit_price=Decimal("2000.00"),
        contractual_variance_amount=Decimal("0.00"), variance_percentage=0.0,
        is_contractually_compliant=True, compliance_status=ContractComplianceStatus.MATCHED_COMPLIANT
    )
    risk_state = PaymentRiskAssessment(
        vendor_trust_score=91, payment_risk_score=8, risk_tier=RiskTier.LOW,
        evaluated_risk_factors=[], action_recommended=RiskAction.AUTO_EXECUTE,
        assessed_at="2026-05-12T10:00:00Z"
    )
    recon = AutonomousReconciliationRecord(
        reconciliation_id="RECON-INV-884", invoice_number="INV-884",
        payout_id="pout_884", bank_utr="UTR-482100", erp_reference_id="ERP-19282",
        journal_transaction_id="GL-19282", disbursed_amount=Decimal("86000.00"),
        reconciled_amount=Decimal("86000.00"), status=ReconciliationStatus.MATCHED_AND_RECONCILED,
        reconciled_at="2026-05-12T10:05:00Z", audit_trail=["Reconciled"]
    )
    manifest = AuditorEvidenceManifest(
        manifest_id="EV-884", decision_id="DEC-884", invoice_number="INV-884",
        vendor_id="VEND-ALPHA-01", generated_at="2026-05-12T10:00:00Z",
        invoice_content_hash="h1", contract_hash="h2", po_hash="h3", grn_hash="h4",
        tax_statutory_provision="Section 393(1) Table Item 7(a)",
        gazette_citation="Income-tax Act, 2025", official_source_uri="https://incometaxindia.gov.in",
        vendor_trust_score=91, payment_risk_score=8, payment_risk_tier=RiskTier.LOW,
        approval_tier=ApprovalTier.AUTO_APPROVED, approver_identity="AUTO_AGENT",
        bank_account_verified=True, journal_transaction_id="GL-19282", ledger_balanced=True,
        canonical_payload_sha256="can_hash", signing_key_id="kms://asia-south1/key-v1",
        ed25519_signature="sig_hex", overall_verification_status=OverallVerificationStatus.CRYPTOGRAPHICALLY_VALID_AND_ADMISSIBLE,
        replay_uri="https://api/v1/decisions/INV-884/replay"
    )
    fd = FinancialDecision(
        decision_id="DEC-884", invoice_number="INV-884", vendor_id="VEND-ALPHA-01",
        fiscal_year="2026-27", decision_timestamp="2026-05-12T10:00:00Z",
        vendor_state=vendor_state, contract_po_state=contract_state,
        invoice_subtotal=Decimal("100000.00"), invoice_gst=Decimal("18000.00"),
        invoice_gross_total=Decimal("118000.00"), ocr_confidence_score=0.99,
        tax_rule_id="RULE-2026-04-17", statutory_provision="Section 393(1) Table Item 7(a)",
        gazette_citation="Income-tax Act, 2025", official_source_uri="https://incometaxindia.gov.in",
        tds_rate=Decimal("0.0200"), tds_deducted=Decimal("2000.00"),
        available_credits_at_evaluation=Decimal("30000.00"), applied_credits=Decimal("30000.00"),
        net_payable_amount=Decimal("86000.00"), unapplied_credits_preserved=Decimal("0.00"),
        risk_assessment=risk_state, approval_tier=ApprovalTier.AUTO_APPROVED,
        approval_policy="POLICY-7.2", approver_identity="AUTO_AGENT",
        payment_state=PaymentState.CONFIRMED, payout_id="pout_884", idempotency_key="idemp_884",
        journal_transaction_id="GL-19282", ledger_balanced=True, challan_281_code="94J",
        reconciliation=recon, evidence_manifest=manifest, canonical_payload_sha256="can_hash",
        signing_key_id="kms://asia-south1/key-v1", ed25519_signature="sig_hex",
        overall_verification_status=OverallVerificationStatus.CRYPTOGRAPHICALLY_VALID_AND_ADMISSIBLE
    )

    replay = DecisionReplayEngine.render_decision_replay(fd)
    assert replay["decision_replay_summary"]["invoice_number"] == "INV-884"
    assert replay["decision_replay_summary"]["final_disbursement"] == "₹86,000.00"
    assert replay["point_in_time_vendor_state"]["bank_account"] == "****4821"
    assert replay["point_in_time_risk_state"]["payment_risk_score"] == "8/100"
    assert replay["point_in_time_credit_state"]["applied_credits"] == "₹30,000.00"
    assert replay["point_in_time_governance_and_accounting"]["ledger_balanced"] == "BALANCED (Debits == Credits)"


# ------------------------------------------------------------------------------
# 2. TEST: CONTINUOUS VENDOR RISK ENGINE
# ------------------------------------------------------------------------------
def test_continuous_vendor_risk_engine_tiers():
    # Scenario A: Low Risk
    v_low = {"trust_score": 95, "bank_account_age_hours": 720, "historical_mean_invoice_amount": "100000.00", "invoices_in_last_7_days": 1}
    risk_low = ContinuousVendorRiskEngine.evaluate_payment_risk(v_low, Decimal("100000.00"))
    assert risk_low.risk_tier == RiskTier.LOW
    assert risk_low.action_recommended == RiskAction.AUTO_EXECUTE

    # Scenario B: High Risk (Bank changed 14h ago + 5.8x amount anomaly + 3rd invoice this week)
    v_high = {"trust_score": 91, "bank_account_age_hours": 14, "historical_mean_invoice_amount": "20000.00", "invoices_in_last_7_days": 3}
    risk_high = ContinuousVendorRiskEngine.evaluate_payment_risk(v_high, Decimal("116000.00"))
    assert risk_high.risk_tier in (RiskTier.HIGH, RiskTier.CRITICAL)
    assert risk_high.payment_risk_score >= 70
    assert len(risk_high.evaluated_risk_factors) >= 3


# ------------------------------------------------------------------------------
# 3. TEST: CONTRACT TO PO TO INVOICE VERIFICATION
# ------------------------------------------------------------------------------
def test_contract_po_variance_and_overbilling_blocks():
    contract = {"contract_id": "CONT-100", "approved_rate": "2000.00", "service_description": "Consulting"}
    po = {"po_number": "PO-100", "authorized_quantity": "100.00"}
    grn = {"grn_id": "TS-100", "accepted_quantity": "100.00"}

    # 1. Contractual Overbilling Variance (140 hours billed vs 100 hours contracted -> ₹80,000 variance)
    inv_overbill = [{"sku": "HOURS", "quantity": Decimal("140.00"), "unit_price": Decimal("2000.00")}]
    res_overbill = ContractLineageVerificationEngine.verify_contract_po_lineage(contract, po, grn, inv_overbill)
    assert res_overbill.is_contractually_compliant is False
    assert res_overbill.compliance_status == ContractComplianceStatus.QUANTITY_OVERBILLING_BLOCKED
    assert res_overbill.contractual_variance_amount == Decimal("80000.00")

    # 2. Rate Variance (₹2,500 billed vs ₹2,000 approved rate)
    inv_rate_var = [{"sku": "HOURS", "quantity": Decimal("100.00"), "unit_price": Decimal("2500.00")}]
    res_rate_var = ContractLineageVerificationEngine.verify_contract_po_lineage(contract, po, grn, inv_rate_var)
    assert res_rate_var.is_contractually_compliant is False
    assert res_rate_var.compliance_status == ContractComplianceStatus.RATE_VARIANCE_BLOCKED
    assert res_rate_var.contractual_variance_amount == Decimal("50000.00")


# ------------------------------------------------------------------------------
# 4. TEST: AUTONOMOUS RECONCILIATION
# ------------------------------------------------------------------------------
def test_autonomous_reconciliation_workflow():
    recon = AutonomousReconciliationEngine.create_reconciliation_record(
        invoice_number="INV-884", journal_transaction_id="GL-19282",
        disbursed_amount=Decimal("86000.00"), payout_id="pout_rzp_884", bank_utr="UTR-HDFC-998811"
    )
    assert recon.status == ReconciliationStatus.MATCHED_AND_RECONCILED
    assert recon.bank_utr == "UTR-HDFC-998811"
    assert recon.erp_reference_id == "ERP-GL-GL-19282"
    assert len(recon.audit_trail) >= 3


# ------------------------------------------------------------------------------
# 5. TEST: AUDITOR EVIDENCE PACK GENERATION
# ------------------------------------------------------------------------------
def test_auditor_evidence_pack_generation():
    manifest = AuditorEvidencePackService.generate_manifest(
        decision_id="DEC-884", invoice_number="INV-884", vendor_id="VEND-ALPHA-01",
        pdf_hash="sha256_pdf_hash", tax_provision="Section 393(1) Table Item 7(a)",
        gazette="Income-tax Act, 2025", source_uri="https://incometaxindia.gov.in",
        vendor_trust=91, payment_risk=8, risk_tier=RiskTier.LOW,
        app_tier=ApprovalTier.AUTO_APPROVED, approver="AUTO_AGENT",
        payout_id="pout_884", bank_utr="UTR-9911", gl_id="GL-19282",
        canonical_hash="sha256_canonical", signing_key_id="kms://asia-south1/key-v1",
        signature="sig_hex", overall_status=OverallVerificationStatus.CRYPTOGRAPHICALLY_VALID_AND_ADMISSIBLE
    )
    assert manifest.manifest_id.startswith("EVIDENCE-PACK-INV-884")
    assert manifest.tax_statutory_provision == "Section 393(1) Table Item 7(a)"
    assert manifest.ledger_balanced is True
    assert "replay" in manifest.replay_uri
