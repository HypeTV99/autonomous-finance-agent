# Graph Report - autonomous-finance-agent  (2026-08-25)

## Corpus Check
- 217 files · ~159,345 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 735 nodes · 2375 edges · 92 communities (87 shown, 5 thin omitted)
- Extraction: 83% EXTRACTED · 17% INFERRED · 0% AMBIGUOUS · INFERRED: 403 edges (avg confidence: 0.93)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Auditor Evidence & Executive Reporting
- Causal Graph & Learning Flywheel
- Invariant & Compliance Engines
- Canonical Decision Serialization & Key Registry
- Tax Framework & TDS Statutory Rules
- Benchmark Suite & Monte-Carlo Simulation
- Counterfactual Causal & Sensitivity Matrix
- Firestore State & Lock Management
- RazorpayX Banking & Treasury Client
- Slack Action & Security Alert Dispatcher
- Intelligent Reconciliation Diagnostics
- Frontend & UI Layout Suite
- Demo Invoice Generator
- Batch Invoice Generation
- Screen Polishing & Master Fixes
- Module & Script Group 15
- Module & Script Group 16
- Module & Script Group 17
- Module & Script Group 18
- Module & Script Group 19
- Module & Script Group 20
- Module & Script Group 21
- Module & Script Group 22
- Module & Script Group 23
- Module & Script Group 24
- Module & Script Group 25
- Module & Script Group 26
- Module & Script Group 27
- Module & Script Group 28
- Module & Script Group 32

## God Nodes (most connected - your core abstractions)
1. `TDSSection` - 49 edges
2. `StatutoryComplianceTaxEngine` - 44 edges
3. `FinancialDecision` - 38 edges
4. `ApprovalTier` - 32 edges
5. `PaymentState` - 31 edges
6. `OpenCreditRecord` - 31 edges
7. `RiskTier` - 31 edges
8. `ExtractedInvoicePayload` - 30 edges
9. `OverallVerificationStatus` - 30 edges
10. `hk()` - 30 edges

## Surprising Connections (you probably didn't know these)
- `BenchmarkTransaction` --uses--> `TDSSection`  [INFERRED]
  benchmark_suite.py → schemas.py
- `FinancialControlBenchmarkEngine` --uses--> `TDSSection`  [INFERRED]
  benchmark_suite.py → schemas.py
- `get_benchmark_executive_summary()` --uses--> `FinancialControlBenchmarkEngine`  [INFERRED]
  main.py → benchmark_suite.py
- `run_financial_control_benchmark()` --uses--> `FinancialControlBenchmarkEngine`  [INFERRED]
  main.py → benchmark_suite.py
- `NettingResult` --uses--> `OpenCreditRecord`  [INFERRED]
  compliance_engine.py → schemas.py

## Import Cycles
- None detected.

## Communities (92 total, 5 thin omitted)

### Community 0 - "Auditor Evidence & Executive Reporting"
Cohesion: 0.08
Nodes (85): BaseModel, AutonomousLearningFlywheelService, FinancialDecisionKnowledgeGraphEngine, date, datetime, Constructs the 10-Stage Financial Decision Knowledge Graph: Vendor -> Contract…, Maintains and evolves learned vendor intelligence, behavioral baselines, and…, ingest_closed_loop_feedback() (+77 more)

### Community 1 - "Causal Graph & Learning Flywheel"
Cohesion: 0.08
Nodes (69): AuditorEvidencePackService, AuditorExecutiveReportRenderer, AutonomousReconciliationEngine, CausalDecisionGraphEngine, ContinuousVendorRiskEngine, ContractLineageVerificationEngine, create_sample_decision(), DecisionReplayEngine (+61 more)

### Community 2 - "Invariant & Compliance Engines"
Cohesion: 0.06
Nodes (60): DecisionEngine, HardenedStatutoryLedgerEngine, LedgerNettingEngine, handle_slack_callback_atomic(), Any, Treasury Reconciliation: Polls gateway by reference_id or idempotency_key…, RazorpayXBankingClient, CanonicalTDSRule (+52 more)

### Community 3 - "Canonical Decision Serialization & Key Registry"
Cohesion: 0.05
Nodes (44): Ab(), ak(), Am(), Ay(), Az(), Bh(), Cy(), dk() (+36 more)

### Community 4 - "Tax Framework & TDS Statutory Rules"
Cohesion: 0.11
Nodes (8): FirestoreStateStore, Any, Decimal, Check if invoice business key (PAN_INV_FY) or raw PDF content hash was already…, sanitize_for_firestore(), Asserts stale worker cannot delete active lock held by another lease., test_fenced_lease_release(), test_pubsub_at_least_once_deduplication()

### Community 5 - "Benchmark Suite & Monte-Carlo Simulation"
Cohesion: 0.11
Nodes (26): extract_invoice_number(), extract_subtotal(), extract_vendor_from_text_or_filename(), get_auditor_evidence_pack(), get_benchmark_executive_summary(), get_decision_evidence_quality(), get_decision_knowledge_graph(), get_decision_record() (+18 more)

### Community 6 - "Counterfactual Causal & Sensitivity Matrix"
Cohesion: 0.20
Nodes (24): _A(), b(), F(), m(), N(), P(), R(), A() (+16 more)

### Community 7 - "Firestore State & Lock Management"
Cohesion: 0.15
Nodes (24): bm(), CB(), cz(), Eb(), Em(), hk(), Hx(), hz() (+16 more)

### Community 8 - "RazorpayX Banking & Treasury Client"
Cohesion: 0.14
Nodes (21): cfo_ai_copilot_chat(), execute_self_healing_reconciliation(), handle_gcs_pubsub_event(), handle_razorpayx_webhook(), public_auditor_verification(), COUNTERFACTUAL CAUSAL ENGINE: Simulates what happens if one input changes (e.g.…, AUTONOMOUS SELF-HEALING RECONCILIATION: Auto-recovers safe exceptions (Bank…, MULTI-VARIABLE FINANCIAL CONTROL SENSITIVITY MATRIX: Evaluates combinatorial… (+13 more)

### Community 9 - "Slack Action & Security Alert Dispatcher"
Cohesion: 0.14
Nodes (20): bl(), c(), cd(), d(), Dz(), g(), h(), jz() (+12 more)

### Community 10 - "Intelligent Reconciliation Diagnostics"
Cohesion: 0.19
Nodes (13): BenchmarkExecutionMetrics, BenchmarkTransaction, BenchmarkVectorType, FinancialControlBenchmarkEngine, Enum, str, Autonomous Enterprise Financial Control Benchmark Suite Evaluates a 1,000…, High-Throughput Vectorized Benchmark Simulator. Generates and evaluates a 1,000… (+5 more)

### Community 11 - "Frontend & UI Layout Suite"
Cohesion: 0.23
Nodes (16): Bb(), Db(), Fb(), jb(), Lb(), Mb(), Ob(), Pb() (+8 more)

### Community 12 - "Demo Invoice Generator"
Cohesion: 0.18
Nodes (11): Root-of-Trust Auditor Signature Verifier: Decouples Mathematical Cryptographic…, verify_external_auditor_signature(), KEY ROTATION AUDIT TEST: Verifies historical signatures pass if signed within…, ROOT-OF-TRUST TEST: Verifies that if an attacker embeds a rogue public key, the…, LIFECYCLE & REVOCATION TEST: Pre-revocation signatures are preserved, post-…, test_historical_key_rotation_validity_window(), test_revocation_lifecycle_and_compromise_semantics(), test_root_of_trust_key_tamper_rejection() (+3 more)

### Community 13 - "Batch Invoice Generation"
Cohesion: 0.26
Nodes (13): benchmark_matrix_view(), callflow_view(), dashboard_view(), dropzone_view(), evidence_tree_view(), graph_tree_view(), graph_view(), legacy_calculator_view() (+5 more)

### Community 14 - "Screen Polishing & Master Fixes"
Cohesion: 0.21
Nodes (8): CanonicalFinancialDecisionSerializer, Canonical Financial Decision Serialization Profile v1 (CFDS-v1) Component…, CFDS-v1 SPEC TEST: Verifies cross-platform byte-level determinism with…, test_cfds_v1_deterministic_canonicalization(), test_concurrent_canonical_serialization_race_free(), test_cfds_cross_platform_determinism(), test_cfds_fixed_scale_and_mutation_detection(), test_cfds_golden_vector_reproducibility()

### Community 15 - "Module & Script Group 15"
Cohesion: 0.24
Nodes (5): CanonicalFinancialDecisionSerializer, EnterpriseKeyRegistry, Any, Canonical Financial Decision Serialization Profile v1 (CFDS-v1) Component…, Independent Root-of-Trust and Time-Bound Key Registry. Tracks active, retired,…

### Community 16 - "Module & Script Group 16"
Cohesion: 0.25
Nodes (6): AdaptiveBehavioralRiskEngine, NettingResult, Decimal, NamedTuple, Learns vendor-specific behavioral baselines: - Normal amount band (e.g. ₹80,000…, test_adaptive_behavioral_risk_engine_baselines()

### Community 17 - "Module & Script Group 17"
Cohesion: 0.36
Nodes (3): EnterpriseKeyRegistry, Any, Independent Root-of-Trust and Time-Bound Key Registry. Tracks active, retired,…

### Community 18 - "Module & Script Group 18"
Cohesion: 0.25
Nodes (6): AdaptiveBehavioralRiskEngine, CounterfactualCausalSimulationEngine, Any, Decimal, Demonstrates genuine causal reasoning: Mutates one input (e.g. Bank Account…, Learns vendor-specific behavioral baselines: - Normal amount band (e.g. ₹80,000…

### Community 20 - "Module & Script Group 20"
Cohesion: 0.29
Nodes (5): HardenedReconciliationEngine, PILLAR 2: Bank Account Change triggers mandatory quarantine cooling-off and…, PILLAR 2 EDGE CASE: Rapid multiple bank changes in rolling 7 days triggers hard…, test_vendor_bank_account_fraud_protection(), test_vendor_bank_account_velocity_lock()

### Community 21 - "Module & Script Group 21"
Cohesion: 0.52
Nodes (6): AdjudicatingAuthoritySignature, CompromiseAdjudicationCertificate, KeyCompromiseOutcome, CARM SPEC TEST: Verifies the full lifecycle of compromise investigation, dual-…, test_compromise_adjudication_state_machine(), test_compromise_boundary_matrix()

### Community 22 - "Module & Script Group 22"
Cohesion: 0.33
Nodes (5): IntelligentReconciliationDiagnosticEngine, Explains every reconciliation exception with causal root attribution and…, get_reconciliation_exceptions(), 4. INTELLIGENT RECONCILIATION EXCEPTION DIAGNOSTIC: Explains every unreconciled…, test_intelligent_reconciliation_diagnostic()

### Community 24 - "Module & Script Group 24"
Cohesion: 0.50
Nodes (3): ContractClauseIntelligenceEngine, Enforces commercial agreement clauses: - PAYMENT_ONLY_AFTER_ACCEPTANCE_SIGNOFF…, test_contract_clause_acceptance_and_rate_cap_enforcement()

### Community 25 - "Module & Script Group 25"
Cohesion: 0.50
Nodes (3): CounterfactualCausalSimulationEngine, Demonstrates genuine causal reasoning: Mutates one input (e.g. Bank Account…, test_counterfactual_causal_simulation_engine()

### Community 28 - "Module & Script Group 28"
Cohesion: 0.67
Nodes (3): FinancialControlSensitivityMatrixEngine, Evaluates combinatorial multi-variable scenario spaces for CFOs & Controllers:…, test_multi_variable_financial_control_sensitivity_matrix()

## Knowledge Gaps
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `FirestoreStateStore` connect `Tax Framework & TDS Statutory Rules` to `Auditor Evidence & Executive Reporting`, `Invariant & Compliance Engines`, `Benchmark Suite & Monte-Carlo Simulation`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Why does `TDSSection` connect `Invariant & Compliance Engines` to `Auditor Evidence & Executive Reporting`, `Causal Graph & Learning Flywheel`, `Benchmark Suite & Monte-Carlo Simulation`, `RazorpayX Banking & Treasury Client`, `Intelligent Reconciliation Diagnostics`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Why does `OpenCreditRecord` connect `Auditor Evidence & Executive Reporting` to `Invariant & Compliance Engines`, `Tax Framework & TDS Statutory Rules`, `Benchmark Suite & Monte-Carlo Simulation`, `RazorpayX Banking & Treasury Client`, `Module & Script Group 16`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Are the 25 inferred relationships involving `TDSSection` (e.g. with `BenchmarkTransaction` and `FinancialControlBenchmarkEngine`) actually correct?**
  _`TDSSection` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Are the 23 inferred relationships involving `StatutoryComplianceTaxEngine` (e.g. with `handle_slack_callback_atomic()` and `CanonicalTDSRule`) actually correct?**
  _`StatutoryComplianceTaxEngine` has 23 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `FinancialDecision` (e.g. with `AuditorExecutiveReportRenderer` and `CausalDecisionGraphEngine`) actually correct?**
  _`FinancialDecision` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `ApprovalTier` (e.g. with `AuditorEvidencePackService` and `create_sample_decision()`) actually correct?**
  _`ApprovalTier` has 12 INFERRED edges - model-reasoned connections that need verification._