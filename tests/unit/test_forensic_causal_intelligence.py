from decimal import Decimal
from compliance_engine import (
    CausalDecisionGraphEngine, AdaptiveBehavioralRiskEngine,
    ContractClauseIntelligenceEngine, IntelligentReconciliationDiagnosticEngine,
    AuditorExecutiveReportRenderer
)
from schemas import (
    FinancialDecision, VendorPointInTimeSnapshot, ContractPOVerificationState,
    ContractComplianceStatus, PaymentRiskAssessment, RiskTier, RiskAction,
    AutonomousReconciliationRecord, ReconciliationStatus, AuditorEvidenceManifest,
    ApprovalTier, PaymentState, OverallVerificationStatus, ContractClauseType
)

def create_sample_decision():
    vendor_state = VendorPointInTimeSnapshot(
        vendor_id="VEND-ALPHA-01", vendor_name="Alpha Tech Labs Pvt Ltd", pan="AAACA1234T",
        trust_score=91, bank_account_last4="4821", bank_account_age_hours=720,
        bank_verified=True, contact_email="billing@alphatech.com",
        historical_mean_invoice_amount=Decimal("100000.00"), current_invoice_amount_multiplier=1.0,
        invoices_in_last_7_days=1
    )
    contract_po_state = ContractPOVerificationState(
        contract_id="CONT-2026-CLOUD-01", po_number="PO-2026-0884",
        service_description="Cloud Consulting", contract_rate=Decimal("2000.00"),
        po_authorized_quantity=Decimal("50.00"), grn_or_timesheet_id="TS-001",
        grn_accepted_quantity=Decimal("50.00"), billed_quantity=Decimal("50.00"),
        billed_unit_price=Decimal("2000.00"), contractual_variance_amount=Decimal("0.00"),
        variance_percentage=0.0, is_contractually_compliant=True,
        compliance_status=ContractComplianceStatus.MATCHED_COMPLIANT
    )
    risk_assessment = PaymentRiskAssessment(
        vendor_trust_score=91, payment_risk_score=8, risk_tier=RiskTier.LOW,
        evaluated_risk_factors=[], action_recommended=RiskAction.AUTO_EXECUTE,
        assessed_at="2026-05-12T10:00:00Z"
    )
    recon = AutonomousReconciliationRecord(
        reconciliation_id="RECON-INV-884-AUTO", invoice_number="INV-884",
        payout_id="pout_live_01", bank_utr="UTR-HDFC-992817263", erp_reference_id="ERP-GL-TXN-001",
        journal_transaction_id="TXN-001", disbursed_amount=Decimal("86000.00"),
        reconciled_amount=Decimal("86000.00"), status=ReconciliationStatus.MATCHED_AND_RECONCILED,
        reconciled_at="2026-05-12T10:00:00Z", audit_trail=["Reconciled"]
    )
    evidence_manifest = AuditorEvidenceManifest(
        manifest_id="EVIDENCE-PACK-INV-884", decision_id="DEC-INV-884",
        invoice_number="INV-884", vendor_id="VEND-ALPHA-01", generated_at="2026-05-12T10:00:00Z",
        invoice_content_hash="hash_pdf", contract_hash="h1", po_hash="h2", grn_hash="h3",
        tax_statutory_provision="Section 393(1) Table Item 7(a)",
        gazette_citation="Income-tax Act, 2025", official_source_uri="https://incometaxindia.gov.in",
        vendor_trust_score=91, payment_risk_score=8, payment_risk_tier=RiskTier.LOW,
        approval_tier=ApprovalTier.AUTO_APPROVED, approver_identity="AUTONOMOUS_POLICY_AGENT",
        bank_account_verified=True, journal_transaction_id="TXN-001", ledger_balanced=True,
        canonical_payload_sha256="canonical_hash", signing_key_id="kms://asia-south1/key-v1",
        ed25519_signature="sig_hex", overall_verification_status=OverallVerificationStatus.CRYPTOGRAPHICALLY_VALID_AND_ADMISSIBLE,
        replay_uri="https://api/v1/decisions/INV-884/replay"
    )
    return FinancialDecision(
        decision_id="DEC-INV-884", invoice_number="INV-884", vendor_id="VEND-ALPHA-01",
        fiscal_year="2026-27", decision_timestamp="2026-05-12T10:00:00Z",
        vendor_state=vendor_state, contract_po_state=contract_po_state,
        invoice_subtotal=Decimal("100000.00"), invoice_gst=Decimal("18000.00"),
        invoice_gross_total=Decimal("118000.00"), ocr_confidence_score=0.99,
        tax_rule_id="RULE-ITA2025-393-7A", statutory_provision="Section 393(1) Table Item 7(a)",
        gazette_citation="Income-tax Act, 2025 (Act No. 4 of 2025)",
        official_source_uri="https://incometaxindia.gov.in", tds_rate=Decimal("0.0200"),
        tds_deducted=Decimal("2000.00"), available_credits_at_evaluation=Decimal("30000.00"),
        applied_credits=Decimal("30000.00"), net_payable_amount=Decimal("86000.00"),
        unapplied_credits_preserved=Decimal("0.00"), risk_assessment=risk_assessment,
        approval_tier=ApprovalTier.AUTO_APPROVED, approval_policy="POLICY-ENTERPRISE-AP-7.2",
        approver_identity="AUTONOMOUS_POLICY_AGENT", payment_state=PaymentState.CONFIRMED,
        payout_id="pout_live_01", idempotency_key="idemp_key_01",
        journal_transaction_id="TXN-001", ledger_balanced=True, challan_281_code="94J",
        reconciliation=recon, evidence_manifest=evidence_manifest,
        canonical_payload_sha256="canonical_hash", signing_key_id="kms://asia-south1/key-v1",
        ed25519_signature="sig_hex", overall_verification_status=OverallVerificationStatus.CRYPTOGRAPHICALLY_VALID_AND_ADMISSIBLE
    )

def test_causal_decision_graph_dag_construction():
    decision = create_sample_decision()
    dag = CausalDecisionGraphEngine.build_causal_graph(decision)
    assert dag.graph_id == "GRAPH-INV-884"
    assert len(dag.nodes) == 9
    assert len(dag.edges) == 9
    assert "NODE-1-INGEST" in [n.node_id for n in dag.nodes]
    assert "NODE-9-RECON" in [n.node_id for n in dag.nodes]
    assert "Alpha Tech Labs Pvt Ltd" in dag.root_cause_narrative

def test_adaptive_behavioral_risk_engine_baselines():
    vendor_history = {
        "normal_min_amount": "80000.00",
        "normal_max_amount": "120000.00",
        "historical_mean": "100000.00",
        "historical_std_dev": "15000.00",
        "normal_invoice_day_of_month": 5,
        "day_of_month_tolerance_days": 2
    }
    # 1. Normal Transaction (₹1,05,000 on the 5th)
    baseline_normal = AdaptiveBehavioralRiskEngine.evaluate_behavioral_baseline("VEND-ALPHA-01", Decimal("105000.00"), "2026-05-05", vendor_history)
    assert baseline_normal.is_amount_anomaly is False
    assert baseline_normal.is_cadence_anomaly is False

    # 2. Anomaly: ₹8.4L on the 22nd (Amount Outlier + Cadence Drift)
    baseline_anom = AdaptiveBehavioralRiskEngine.evaluate_behavioral_baseline("VEND-ALPHA-01", Decimal("840000.00"), "2026-05-22", vendor_history)
    assert baseline_anom.is_amount_anomaly is True
    assert baseline_anom.is_cadence_anomaly is True
    assert baseline_anom.amount_z_score > 40.0
    assert baseline_anom.cadence_drift_days == 17
    assert "outside the normal baseline band" in baseline_anom.anomaly_explanation

def test_contract_clause_acceptance_and_rate_cap_enforcement():
    contract = {"approved_rate": "2000.00", "requires_acceptance_signoff": True}
    
    # 1. Missing Acceptance Signoff
    inv_missing_signoff = {"unit_price": Decimal("2000.00")}
    clauses_1 = ContractClauseIntelligenceEngine.evaluate_contract_clauses(contract, inv_missing_signoff, has_acceptance_signoff=False)
    assert clauses_1[0].is_satisfied is False
    assert "COMMERCIAL_BLOCK" in clauses_1[0].block_reason

    # 2. Billed Rate Exceeds Contract Cap (₹2,500 vs ₹2,000)
    inv_rate_breach = {"unit_price": Decimal("2500.00")}
    clauses_2 = ContractClauseIntelligenceEngine.evaluate_contract_clauses(contract, inv_rate_breach, has_acceptance_signoff=True)
    assert clauses_2[1].is_satisfied is False
    assert "RATE_VARIANCE_BLOCK" in clauses_2[1].block_reason

def test_intelligent_reconciliation_diagnostic():
    diag = IntelligentReconciliationDiagnosticEngine.diagnose_exception(
        invoice_number="INV-884", disbursed_amount=Decimal("86000.00"), payout_id="pout_884",
        bank_utr="UTR-9911", bank_confirmed_at="2026-05-12T14:03:00Z", erp_reference_id="ERP-GL-19282"
    )
    assert diag.exception_id.startswith("EXC-INV-884")
    assert "Bank UTR confirmed, but ERP transaction sync timed out" in diag.root_cause_summary
    assert "Retry ERP Ledger Sync" in diag.suggested_resolution
    assert diag.automated_recovery_available is True

def test_auditor_executive_proof_report_nine_pillars():
    decision = create_sample_decision()
    report = AuditorExecutiveReportRenderer.generate_executive_report(decision)
    assert report.report_id == "AUDIT-PROOF-INV-884"
    assert len(report.nine_pillars_proof) == 9
    assert all(p.is_verified for p in report.nine_pillars_proof)
    assert "CONTROL VERIFIED" in report.overall_admissibility
    assert "CONTROL VERIFICATION" in report.control_verification_header

def test_evidence_quality_scoring_engine():
    from compliance_engine import EvidenceQualityScoringEngine
    from schemas import EvidenceQualityGrade
    # 1. Full primary evidence
    q_full = EvidenceQualityScoringEngine.evaluate_evidence_quality(
        has_valid_contract=True, is_contract_active=True, has_purchase_order=True,
        has_acceptance_signoff=True, has_pan_registry_proof=True, has_bank_penny_drop=True,
        is_sec197_cert_valid=True
    )
    assert q_full.quality_grade == EvidenceQualityGrade.GRADE_A_PLUS_FORENSIC
    assert q_full.composite_quality_score >= 95.0
    assert q_full.integrity_score > 98.0

    # 2. Deficient evidence (missing acceptance & expired cert)
    q_def = EvidenceQualityScoringEngine.evaluate_evidence_quality(
        has_valid_contract=True, is_contract_active=False, has_purchase_order=True,
        has_acceptance_signoff=False, has_pan_registry_proof=True, has_bank_penny_drop=False,
        is_sec197_cert_valid=False
    )
    assert q_def.quality_grade in (EvidenceQualityGrade.GRADE_C_DEFICIENT, EvidenceQualityGrade.GRADE_F_UNTRUSTED)
    assert q_def.composite_quality_score < 70.0

def test_counterfactual_causal_simulation_engine():
    from compliance_engine import CounterfactualCausalSimulationEngine
    
    # 1. Counterfactual: Bank age 14h -> Cooling block
    sim_bank = CounterfactualCausalSimulationEngine.simulate_counterfactual(
        invoice_number="INV-884",
        mutated_inputs={"bank_account_age_hours": 14}
    )
    assert "CRITICAL_RISK_HOLD" in sim_bank.counterfactual_decision
    assert any(d["layer"] == "RISK_ENGINE" for d in sim_bank.downstream_causal_deltas)
    assert "cooling policy" in sim_bank.narrative_explanation

    # 2. Counterfactual: Rate breach ₹2,500 -> Rate variance block
    sim_rate = CounterfactualCausalSimulationEngine.simulate_counterfactual(
        invoice_number="INV-884",
        mutated_inputs={"unit_price": "2500.00"}
    )
    assert "RATE_VARIANCE_BLOCKED" in sim_rate.counterfactual_decision
    assert any(d["layer"] == "CONTRACT_ENGINE" for d in sim_rate.downstream_causal_deltas)

def test_autonomous_self_healing_reconciliation_service():
    from compliance_engine import AutonomousSelfHealingReconciliationService
    action = AutonomousSelfHealingReconciliationService.execute_self_healing_recovery(
        exception_id="EXC-884",
        bank_utr="UTR-HDFC-9911",
        erp_reference_id="ERP-GL-19282",
        is_safe_to_recover=True
    )
    assert action.executed_successfully is True
    assert action.action_type == "AUTO_RETRY_ERP_SYNC"
    assert "re-synchronized" in action.audit_trail_entry

def test_evidence_quality_drill_down_tree():
    from compliance_engine import EvidenceQualityScoringEngine
    q = EvidenceQualityScoringEngine.evaluate_evidence_quality()
    assert "INTEGRITY" in q.drill_down_tree
    assert "COMPLETENESS" in q.drill_down_tree
    assert "FRESHNESS" in q.drill_down_tree
    assert "AUTHORITY" in q.drill_down_tree
    
    # Drill into Integrity leaves
    integrity_leaves = q.drill_down_tree["INTEGRITY"]
    assert len(integrity_leaves) == 4
    assert any(l.check_name.startswith("SHA-256") and l.is_passed for l in integrity_leaves)
    assert any(l.check_name.startswith("RFC 8785") and l.is_passed for l in integrity_leaves)
    assert any(l.check_name.startswith("Ed25519") and l.is_passed for l in integrity_leaves)

def test_multi_variable_financial_control_sensitivity_matrix():
    from compliance_engine import FinancialControlSensitivityMatrixEngine
    from schemas import ScenarioInput
    from decimal import Decimal

    scenarios = [
        ScenarioInput(
            scenario_name="Scenario A (Bank Cooling Breach)",
            bank_account_age_hours=14,
            invoice_amount=Decimal("840000.00"),
            applied_credit=Decimal("30000.00"),
            has_acceptance_signoff=True
        ),
        ScenarioInput(
            scenario_name="Scenario B (Amount Anomaly - HITL Review)",
            bank_account_age_hours=720,
            invoice_amount=Decimal("840000.00"),
            applied_credit=Decimal("30000.00"),
            has_acceptance_signoff=True
        ),
        ScenarioInput(
            scenario_name="Scenario C (Standard Limit - Auto Approved)",
            bank_account_age_hours=720,
            invoice_amount=Decimal("105000.00"),
            applied_credit=Decimal("30000.00"),
            has_acceptance_signoff=True
        )
    ]

    report = FinancialControlSensitivityMatrixEngine.simulate_matrix_scenarios("INV-884", scenarios)
    assert report.matrix_simulation_id.startswith("MATRIX-SIM-INV-884")
    assert len(report.scenario_comparisons) == 3
    
    # Verify Scenario A -> BLOCKED under Cooling Policy
    sc_a = report.scenario_comparisons[0]
    assert "BLOCKED" in sc_a.decision_outcome
    assert sc_a.governing_control_rule == "POL-TREASURY-BNK-MOD-48H"

    # Verify Scenario B -> PENDING CONTROLLER REVIEW
    sc_b = report.scenario_comparisons[1]
    assert "CONTROLLER" in sc_b.decision_outcome
    assert sc_b.governing_control_rule == "POL-AMOUNT-ANOMALY-3X-MEAN"

    # Verify Scenario C -> AUTO APPROVED
    sc_c = report.scenario_comparisons[2]
    assert "AUTO_APPROVED" in sc_c.decision_outcome
    assert sc_c.net_payout_amount == Decimal("75000.00")


