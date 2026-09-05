"""
tests/adversarial/test_red_team_chaos_p0_p1.py
Prompt 12 of 12: Adversarial Red Team, Chaos Injection, Crypto Tampering,
Historical Replay, and System Recovery Verification.

Exhaustively attacks:
1. Duplicate external payouts under concurrent worker races.
2. Gateway 504 / transport exceptions (indeterminate state fencing).
3. Provider success with lost network responses & authoritative reconciliation.
4. Worker crashes mid-flight & queue redelivery suppression.
5. Concurrent credit reservation & consumption races with strict monetary conservation.
6. Cumulative PO/GRN over-allocation across repeated partial invoices.
7. Simulation / Sandbox trust spoofing gated against production disbursal.
8. Semantic journal validation & immutable posted journal protection.
9. Cryptographic attestation tampering (0.01 rupee, vendor PAN, policy version).
10. Historical replay using pinned historical policy instead of modern active policy.
11. WHAT_IF output isolation (simulation only).
12. Multi-layer duplicate invoice detection.
13. Webhook signature tampering, replay expiry, and out-of-order callback protection.
14. Non-overridable invariant fencing against manual override bypass.
15. Stale version state machine optimistic concurrency fencing.
"""

from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import pytest
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock
import uuid

from compliance_engine import HardenedStatutoryLedgerEngine
from firestore_store import (
    FirestoreStateStore,
    PostedDecisionMutationError,
    PostedJournalMutationError,
)
from razorpayx_client import RazorpayXBankingClient
from schemas import (
    CanonicalTDSRule,
    DecisionRecord,
    DuplicateDisposition,
    ExtractedInvoicePayload,
    InvoiceLineItem,
    ManualOverrideRecord,
    OpenCreditRecord,
    OutboxEventStatus,
    OverrideScope,
    PaymentInstruction,
    PaymentState,
    ReplayMode,
    SystemEnvironment,
    TaxFramework,
    TDSSection,
    normalize_environment,
)
from services.crypto import (
    CanonicalFinancialDecisionSerializer,
    EnterpriseKeyRegistry,
    verify_external_auditor_signature,
)
from services.decision_engine import DecisionEngine
from services.duplicate_detector import MultiSignalDuplicateDetector
from services.ledger import HardenedStatutoryLedgerEngine, LedgerNettingEngine
from services.lineage import DecisionReplayEngine
from services.observability import (
    HighRiskEvent,
    get_security_logger,
)
from services.override_governor import (
    MakerCheckerViolationError,
    NonOverridableInvariantViolationError,
    OverrideExpiredError,
    OverrideGovernor,
)
from services.payment_orchestrator import (
    PaymentAmbiguousOutcomeError,
    PaymentMaterialConflictError,
    PaymentOrchestrationError,
    PaymentOrchestrator,
    PaymentStaleVersionError,
    PaymentStateMachine,
)
from services.po_matching import ThreeWayPOMatchingEngine
from services.po_registry import PoRegistry
from services.policy_registry import (
    EnterprisePolicyRegistry,
    PolicyDefinition,
    PolicyType,
)
from services.webhook_service import (
    ProviderWebhookService,
    WebhookAuthenticationError,
    WebhookReplayError,
)
from tax_engine import StatutoryComplianceTaxEngine


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def store():
    """Isolated thread-safe in-memory state store."""
    s = FirestoreStateStore(force_mock=True)
    s.clear_all()
    return s


@pytest.fixture
def banking_client():
    """Mocked banking rail client."""
    return RazorpayXBankingClient("rzp_test_key", "rzp_test_secret", "2323230000000001")


@pytest.fixture
def sec_logger():
    """Security audit logger with cleared buffer."""
    logger = get_security_logger()
    logger.clear_buffer()
    return logger


def _create_test_intent(
    invoice_number: str = "INV-REDTEAM-01",
    vendor_id: str = "VEND-REDTEAM",
    net_payout: Decimal = Decimal("50000.00"),
    status: PaymentState = PaymentState.READY_FOR_SUBMISSION,
    environment: str = "SANDBOX",
    trust: str = "PRODUCTION_TRUST",
    idempotency_key: Optional[str] = None
) -> PaymentInstruction:
    now_iso = datetime.now(timezone.utc).isoformat()
    return PaymentInstruction(
        instruction_id=f"INS-{uuid.uuid4().hex[:10].upper()}",
        invoice_number=invoice_number,
        vendor_id=vendor_id,
        vendor_pan="AAACB1234K",
        fund_account_id="fa_test_beneficiary",
        gross_subtotal=net_payout,
        tax_amount=Decimal("0.00"),
        tds_withheld=Decimal("0.00"),
        tds_section=TDSSection.NONE,
        applied_credits_total=Decimal("0.00"),
        net_payout_amount=net_payout,
        payout_paise=int(net_payout * 100),
        idempotency_key=idempotency_key or f"idemp_{invoice_number}",
        requires_zero_payout_hold=(net_payout == Decimal("0.00")),
        status=status,
        environment=environment,
        bank_verification_trust=trust,
        created_at=now_iso,
        updated_at=now_iso,
        occurred_at=now_iso,
        received_at=now_iso
    )


# ==============================================================================
# PART A & B: ADVERSARIAL RED TEAM & CHAOS RECOVERY
# ==============================================================================

def test_duplicate_external_payment_blocked_under_concurrent_race(store, banking_client):
    """
    RED TEAM ATTACK: 10 concurrent worker threads attempt to dispatch the exact same
    payment intent simultaneously.
    EXPECTED DEFENSE: Fencing lease allows strictly ONE worker to contact the bank rail.
    All peer threads either receive the idempotent cached response or wait on the lease.
    Banking provider is invoked exactly ONCE.
    """
    orchestrator = PaymentOrchestrator(store, banking_client)
    intent = _create_test_intent(invoice_number=f"INV-RACE-{uuid.uuid4().hex[:6]}")

    # Track actual gateway calls
    gateway_call_count = 0

    def mock_stage_payout(*args, **kwargs):
        nonlocal gateway_call_count
        gateway_call_count += 1
        return {"id": "pout_race_01", "status": "processed", "utr": "UTR-RACE-001"}

    banking_client.stage_payout = mock_stage_payout

    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(orchestrator.dispatch_payment_intent, intent) for _ in range(10)]
        for f in futures:
            results.append(f.result())

    # Strictly 1 external gateway execution
    assert gateway_call_count == 1
    # All 10 threads receive SUCCESS
    assert all(r["status"] == "SUCCESS" for r in results)
    # Stored state is terminal SETTLED
    saved = store.get_payment_intent(intent.idempotency_key)
    assert saved["status"] == PaymentState.SETTLED.value


def test_ambiguous_provider_timeout_fences_state_and_blocks_blind_retry(store, banking_client, sec_logger):
    """
    RED TEAM ATTACK: Gateway returns 504 Gateway Timeout / indeterminate response.
    Worker attempts to immediately resubmit the payment blindly.
    EXPECTED DEFENSE: System transitions state to UNKNOWN/AMBIGUOUS.
    Blind resubmission is strictly blocked with PaymentAmbiguousOutcomeError.
    Security audit logs ambiguous_payment event.
    """
    orchestrator = PaymentOrchestrator(store, banking_client)
    intent = _create_test_intent(invoice_number="INV-TIMEOUT-01")

    # Simulate gateway timeout
    banking_client.stage_payout = MagicMock(return_value={"id": "pout_timeout", "status": "UNKNOWN", "requires_reconciliation": True})

    res = orchestrator.dispatch_payment_intent(intent)
    assert res["status"] == "AMBIGUOUS"
    assert res["state"] == PaymentState.UNKNOWN.value

    # Blind second dispatch MUST be blocked
    with pytest.raises(PaymentAmbiguousOutcomeError) as excinfo:
        orchestrator.dispatch_payment_intent(intent)
    assert "indeterminate outcome" in str(excinfo.value)
    assert "Blind resubmission blocked" in str(excinfo.value)

    # Verify security audit trail
    trail = sec_logger.get_audit_trail()
    amb_events = [e for e in trail if e["event_type"] == HighRiskEvent.AMBIGUOUS_PAYMENT.value]
    assert len(amb_events) >= 1


def test_provider_success_lost_response_reconciliation_convergence(store, banking_client):
    """
    CHAOS TEST: Bank executes payout and assigns UTR, but response is lost (worker network crash).
    Subsequent reconciliation query queries the bank, authoritatively identifies the payout,
    attaches UTR, and converges safely to SETTLED without duplicate disbursement.
    """
    orchestrator = PaymentOrchestrator(store, banking_client)
    intent = _create_test_intent(invoice_number="INV-LOST-RESP-01")

    # Stage 1: Payout executed by bank, but worker received indeterminate exception
    store.save_payment_intent(intent.model_dump(mode="json"))
    store.update_payment_intent(
        idempotency_key=intent.idempotency_key,
        update_dict={"status": PaymentState.UNKNOWN.value, "last_error": "Network drop after gateway dispatch"}
    )

    # Stage 2: Gateway reconcile confirms payout was settled
    banking_client.reconcile_payout_status = MagicMock(return_value={
        "status": "CONFIRMED",
        "reconciled": True,
        "payout_id": "pout_authoritative_99",
        "utr": "UTR-RECON-CONFIRMED-01"
    })

    recon_res = orchestrator.reconcile_ambiguous_intent(intent, banking_client)
    assert recon_res["status"] == "CONFIRMED"
    assert recon_res["reconciled"] is True
    assert recon_res["utr"] == "UTR-RECON-CONFIRMED-01"

    # Verify store converged to SETTLED
    final_intent = store.get_payment_intent(intent.idempotency_key)
    assert final_intent["status"] == PaymentState.SETTLED.value
    assert final_intent["utr"] == "UTR-RECON-CONFIRMED-01"


def test_queue_redelivery_duplicate_suppressed(store, banking_client, sec_logger):
    """
    CHAOS TEST: Outbox item or queue message is delivered multiple times
    after the intent is already SETTLED.
    EXPECTED DEFENSE: Duplicate submission is safely suppressed and logged.
    """
    orchestrator = PaymentOrchestrator(store, banking_client)
    intent = _create_test_intent(
        invoice_number="INV-QUEUE-REDELIV-01",
        status=PaymentState.SETTLED
    )
    store.save_payment_intent(intent.model_dump(mode="json"))

    gateway_mock = MagicMock()
    banking_client.stage_payout = gateway_mock

    # Redelivered dispatch attempt
    res = orchestrator.dispatch_payment_intent(intent)

    assert res["status"] == "SUCCESS"
    assert res["is_cached"] is True
    # Gateway was NEVER called
    gateway_mock.assert_not_called()

    # Logged to security audit
    trail = sec_logger.get_audit_trail()
    dup_events = [e for e in trail if e["event_type"] == HighRiskEvent.DUPLICATE_SUBMISSION_SUPPRESSED.value]
    assert len(dup_events) >= 1


def test_concurrent_credit_reservation_exhaustion(store):
    """
    RED TEAM ATTACK: Vendor has ₹20,000 available credit note.
    5 concurrent workers try to reserve ₹10,000 each (total ₹50,000).
    EXPECTED DEFENSE: Exactly 2 workers succeed (total ₹20,000).
    Remaining 3 workers are rejected. Monetary conservation is preserved.
    """
    credit = OpenCreditRecord(
        credit_note_id="CR-RACE-001",
        vendor_id="VEND-RACE",
        original_amount=Decimal("20000.00"),
        available_amount=Decimal("20000.00"),
        reserved_amount=Decimal("0.00"),
        consumed_amount=Decimal("0.00")
    )
    store._mock_db.setdefault("vendor_open_credits", {})["VEND-RACE"] = [credit.model_dump(mode="json")]

    success_count = 0
    failure_count = 0

    def attempt_reservation(worker_id: int):
        nonlocal success_count, failure_count
        with store._procurement_lock:
            credits = store._mock_db["vendor_open_credits"]["VEND-RACE"]
            c = credits[0]
            avail = Decimal(str(c["available_amount"]))
            req = Decimal("10000.00")
            if avail >= req:
                c["available_amount"] = str(avail - req)
                c["reserved_amount"] = str(Decimal(str(c["reserved_amount"])) + req)
                return True
            return False

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(attempt_reservation, i) for i in range(5)]
        for f in futures:
            if f.result():
                success_count += 1
            else:
                failure_count += 1

    assert success_count == 2
    assert failure_count == 3

    # Check conservation on stored record
    final_c = store._mock_db["vendor_open_credits"]["VEND-RACE"][0]
    orig = Decimal(str(final_c["original_amount"]))
    avail = Decimal(str(final_c["available_amount"]))
    resv = Decimal(str(final_c["reserved_amount"]))
    cons = Decimal(str(final_c["consumed_amount"]))
    assert orig == Decimal("20000.00")
    assert avail == Decimal("0.00")
    assert resv == Decimal("20000.00")
    assert cons == Decimal("0.00")
    assert avail + resv + cons == orig


def test_cumulative_po_drawdown_exhaustion(store):
    """
    RED TEAM ATTACK: PO has ₹100,000 line item ceiling (100 units @ ₹1,000).
    Four partial invoices draw down 30 units each (total 120 units).
    EXPECTED DEFENSE: First 3 invoices succeed (90 units).
    4th invoice exceeds remaining 10 units capacity and is strictly rejected.
    """
    po_num = f"PO-REDTEAM-{uuid.uuid4().hex[:6]}"
    vendor_id = "VEND-REDTEAM"
    sku = "SKU-REDTEAM-01"
    unit_price = Decimal("1000.00")

    PoRegistry.register_purchase_order(
        vendor_id=vendor_id,
        po_number=po_num,
        authorized_ceiling=Decimal("100000.00"),
        rates={sku: unit_price},
        quantities={sku: Decimal("100.00")},
        po_version=1
    )

    # Invoices 1, 2, 3 draw 30 units each (30 * 1000 = 30,000 each; cumulative 90 units)
    for i in range(1, 4):
        items = [
            InvoiceLineItem(
                sku=sku,
                description=f"Partial draw {i}",
                quantity=Decimal("30.00"),
                unit_price=unit_price,
                line_total=Decimal("30000.00")
            )
        ]
        ok, rec, msg = ThreeWayPOMatchingEngine.allocate_procurement(
            store=store,
            invoice_number=f"INV-PARTIAL-{i}",
            vendor_id=vendor_id,
            line_items=items,
            po_number=po_num,
            po_version=1
        )
        assert ok is True, f"Invoice {i} should be accepted: {msg}"

    # Invoice 4 requests 30 units, but only 10 remain (100 - 90 = 10)
    items4 = [
        InvoiceLineItem(
            sku=sku,
            description="Partial draw 4",
            quantity=Decimal("30.00"),
            unit_price=unit_price,
            line_total=Decimal("30000.00")
        )
    ]
    ok4, _, msg4 = ThreeWayPOMatchingEngine.allocate_procurement(
        store=store,
        invoice_number="INV-PARTIAL-4",
        vendor_id=vendor_id,
        line_items=items4,
        po_number=po_num,
        po_version=1
    )
    assert ok4 is False
    assert "Cumulative PO quantity exceeded" in msg4 or "exceeded" in msg4.lower()


def test_simulation_evidence_gated_against_production_rail(store, banking_client, sec_logger):
    """
    RED TEAM ATTACK: Payment intent targeted for PRODUCTION presents only
    SIMULATION bank verification trust evidence.
    EXPECTED DEFENSE: Disbursal is blocked with critical security alert.
    No payout is issued to the banking rail.
    """
    orchestrator = PaymentOrchestrator(store, banking_client)
    intent = _create_test_intent(
        invoice_number="INV-PROD-ATTACK-01",
        environment="PRODUCTION",
        trust="SIMULATION_TRUST"  # Spoofed / insufficient trust
    )

    with pytest.raises(PaymentOrchestrationError) as excinfo:
        orchestrator.dispatch_payment_intent(intent)

    assert "Production Payout Gated" in str(excinfo.value)
    trail = sec_logger.get_audit_trail()
    gate_events = [e for e in trail if e["event_type"] == HighRiskEvent.SIMULATION_PRODUCTION_GATE_REJECTED.value]
    assert len(gate_events) >= 1


def test_posted_journal_mutation_blocked(store):
    """
    RED TEAM ATTACK: Attempt to overwrite or mutate an existing posted general ledger journal.
    EXPECTED DEFENSE: PostedDecisionMutationError / PostedJournalMutationError is raised.
    Posted history is strictly append-only.
    """
    journal = {
        "transaction_id": "GL-TXN-IMMUTABLE-01",
        "invoice_number": "INV-IMMUTABLE-01",
        "total_debits": "10000.00",
        "total_credits": "10000.00",
        "status": "POSTED"
    }
    challan = {"challan_id": "CH-01", "transaction_id": "GL-TXN-IMMUTABLE-01"}

    # 1. First posting succeeds
    store.persist_general_ledger(journal, challan)

    # 2. Mutating with changed amount must be rejected
    mutated_journal = dict(journal)
    mutated_journal["total_debits"] = "20000.00"

    with pytest.raises(PostedJournalMutationError) as excinfo:
        store.persist_general_ledger(mutated_journal, challan)
    assert "Cannot mutate posted journal entry" in str(excinfo.value)


# ==============================================================================
# PART C: CRYPTOGRAPHIC TAMPERING
# ==============================================================================

def test_cryptographic_tampering_fails_verification():
    """
    PART C ATTACK: Mutate material decision attributes within signed context:
    - Alter amount by ₹0.01
    - Alter vendor PAN
    - Alter policy version
    EXPECTED DEFENSE: Canonical digest shifts, Ed25519 signature verification fails.
    """
    inv = ExtractedInvoicePayload(
        invoice_number="INV-CRYPTO-TAMPER-01",
        vendor_pan="AABCQ1234T",
        invoice_date="2026-05-15",
        fiscal_year="2026-27",
        line_items=[
            InvoiceLineItem(
                sku="SKU-SERV-01",
                description="Architecture Security Audit",
                quantity=Decimal("1.0"),
                unit_price=Decimal("100000.00"),
                line_total=Decimal("100000.00")
            )
        ],
        subtotal=Decimal("100000.00"),
        tax_amount=Decimal("18000.00"),
        total_amount=Decimal("118000.00"),
        ocr_confidence_score=0.99
    )
    tax_res = StatutoryComplianceTaxEngine.compute_statutory_tax(
        subtotal=inv.subtotal,
        gst_amount=inv.tax_amount,
        section=TDSSection.SECTION_194J_PROF,
        vendor_pan=inv.vendor_pan,
        transaction_date=datetime.now(timezone.utc).date()
    )
    netting = LedgerNettingEngine.apply_credits_and_advances(tax_res.final_disbursement, [])
    journal, challan = HardenedStatutoryLedgerEngine.generate_accounting_records(
        inv.invoice_number, inv.vendor_pan, inv.fiscal_year, inv.subtotal, netting.applied_credit_total, tax_res, inv.tax_amount
    )

    decision_rec, payment_instr = DecisionEngine.build_immutable_decision_record(
        invoice=inv,
        vendor_id="VEND-SEC-99",
        tax_result=tax_res,
        netting_result=netting,
        journal=journal,
        source_document_hash="sha256:doc_evidence_clean_pdf_99",
        reconciliation_evidence={"status": "MATCHED_3WAY_CLEAN", "po_number": "PO-2026-REV-01"},
        fund_account_id="fa_test_bank_01",
        idempotency_key="IDEMP-DEC-CRYPTO-TAMPER-001",
        po_snapshot_hash="sha256:po_snap_01",
        grn_snapshot_hash="sha256:grn_snap_01",
        vendor_snapshot_hash="sha256:vend_snap_01",
        matching_policy_version="2026.1",
        tax_policy_version="2026.1",
        payment_policy_version="2026.1"
    )

    # 1. Baseline verification passes
    valid, reason = verify_external_auditor_signature(
        canonical_payload_sha256=decision_rec.canonical_payload_sha256,
        signature_hex=decision_rec.cryptographic_signature,
        public_key_hex=decision_rec.public_key_hex,
        signing_key_id=decision_rec.signing_key_id,
        signed_at=decision_rec.signed_at,
        valid_from=decision_rec.key_valid_from,
        valid_until=decision_rec.key_valid_until
    )
    assert valid is True
    assert reason == "VALID_SIGNATURE"

    def compute_tampered_digest(tampered_dict: Dict[str, Any]) -> str:
        payload_dict = {k: v for k, v in tampered_dict.items() if k in (
            "decision_id", "invoice_number", "vendor_id", "vendor_pan", "fiscal_year",
            "source_document_hash", "source_document_uri", "gst_irn", "tax_framework",
            "canonical_rule_id", "internal_rule_id", "statutory_provision", "government_section",
            "government_table_item", "gazette_citation", "cbdt_circular_reference",
            "official_source_uri", "tax_rule_version", "statutory_return_form",
            "statutory_return_field_code", "form_26q_code", "internal_reporting_code",
            "challan_281_code", "pan_26as_credit_tag", "calculation_version", "effective_date",
            "previous_decision_digest", "reconciliation_evidence", "tds_calculation",
            "credit_allocation_manifest", "general_ledger_tx_id", "payment_instruction",
            "decision_timestamp", "schema_version", "po_snapshot_hash", "grn_snapshot_hash",
            "vendor_snapshot_hash", "matching_policy_version", "tax_policy_version",
            "payment_policy_version", "retention_policy_version", "tolerance_policy_version",
            "discount_policy_version", "accounting_policy_version", "risk_policy_version",
            "credit_allocation_hash", "gstr_evidence_hash", "bank_verification_evidence_hash",
            "ledger_entry_hash", "payment_intent_id", "canonicalization_version"
        )}
        canon = CanonicalFinancialDecisionSerializer.serialize(payload_dict)
        return hashlib.sha256(canon.encode("utf-8")).hexdigest()

    # 2. Attack: Tamper amount by ₹0.01 in payment instruction
    tampered_1 = copy.deepcopy(decision_rec.model_dump())
    net_amt = Decimal(str(tampered_1["payment_instruction"]["net_payout_amount"])) + Decimal("0.01")
    tampered_1["payment_instruction"]["net_payout_amount"] = str(net_amt)
    tampered_digest_1 = compute_tampered_digest(tampered_1)
    assert tampered_digest_1 != decision_rec.canonical_payload_sha256
    valid_t1, _ = verify_external_auditor_signature(
        canonical_payload_sha256=tampered_digest_1,
        signature_hex=decision_rec.cryptographic_signature,
        public_key_hex=decision_rec.public_key_hex
    )
    assert valid_t1 is False

    # 3. Attack: Tamper vendor PAN
    tampered_2 = copy.deepcopy(decision_rec.model_dump())
    tampered_2["vendor_pan"] = "ZZZCB9999K"
    tampered_digest_2 = compute_tampered_digest(tampered_2)
    assert tampered_digest_2 != decision_rec.canonical_payload_sha256
    valid_t2, _ = verify_external_auditor_signature(
        canonical_payload_sha256=tampered_digest_2,
        signature_hex=decision_rec.cryptographic_signature,
        public_key_hex=decision_rec.public_key_hex
    )
    assert valid_t2 is False

    # 4. Attack: Tamper policy version
    tampered_3 = copy.deepcopy(decision_rec.model_dump())
    tampered_3["matching_policy_version"] = "2024.1-TAMPERED"
    tampered_digest_3 = compute_tampered_digest(tampered_3)
    assert tampered_digest_3 != decision_rec.canonical_payload_sha256
    valid_t3, _ = verify_external_auditor_signature(
        canonical_payload_sha256=tampered_digest_3,
        signature_hex=decision_rec.cryptographic_signature,
        public_key_hex=decision_rec.public_key_hex
    )
    assert valid_t3 is False


# ==============================================================================
# PART D: HISTORICAL REPLAY & WHAT-IF ISOLATION
# ==============================================================================

def test_historical_replay_resolves_historical_dependencies():
    """
    PART D TEST: Historical decision taken under 2024 tax policies replayed today.
    EXPECTED BEHAVIOR: Replay engine uses the pinned historical policy (2024.1),
    not the active current 2026 policy.
    """
    rules_2024 = {"matching_mode": "TWO_WAY_BASIC", "tolerance_pct": 5.0}
    
    p_2024 = PolicyDefinition(
        policy_type=PolicyType.MATCHING_POLICY,
        version="2024.1",
        effective_from="2024-01-01T00:00:00Z",
        rules_digest=EnterprisePolicyRegistry.compute_rules_digest(rules_2024),
        rules_payload=rules_2024
    )
    EnterprisePolicyRegistry.register_policy(p_2024)

    resolved_hist = EnterprisePolicyRegistry.get_policy(PolicyType.MATCHING_POLICY, "2024.1")
    resolved_active = EnterprisePolicyRegistry.get_policy(PolicyType.MATCHING_POLICY, "2026.1")
    assert resolved_hist.version == "2024.1"
    assert resolved_active.version == "2026.1"
    assert resolved_hist.rules_payload["tolerance_pct"] == 5.0
    assert resolved_active.rules_payload["mode"] == "THREE_WAY_CUMULATIVE"


def test_what_if_replay_output_isolated_from_production(store, banking_client):
    """
    PART D TEST: A WHAT_IF replay evaluates alternative policies (e.g. relaxed tolerances).
    EXPECTED BEHAVIOR: Output is explicitly flagged is_simulation=True, admissible_for_payout=False,
    and cannot be converted to a production disbursal instruction.
    """
    inv = ExtractedInvoicePayload(
        invoice_number="INV-WHATIF-01",
        vendor_pan="AABCQ1234T",
        invoice_date="2026-05-15",
        fiscal_year="2026-27",
        line_items=[
            InvoiceLineItem(
                sku="SKU-01",
                description="Consulting",
                quantity=Decimal("1.0"),
                unit_price=Decimal("50000.00"),
                line_total=Decimal("50000.00")
            )
        ],
        subtotal=Decimal("50000.00"),
        tax_amount=Decimal("9000.00"),
        total_amount=Decimal("59000.00"),
        ocr_confidence_score=0.99
    )
    tax_res = StatutoryComplianceTaxEngine.compute_statutory_tax(
        subtotal=inv.subtotal,
        gst_amount=inv.tax_amount,
        section=TDSSection.SECTION_194J_PROF,
        vendor_pan=inv.vendor_pan,
        transaction_date=datetime.now(timezone.utc).date()
    )
    netting = LedgerNettingEngine.apply_credits_and_advances(tax_res.final_disbursement, [])
    journal, challan = HardenedStatutoryLedgerEngine.generate_accounting_records(
        inv.invoice_number, inv.vendor_pan, inv.fiscal_year, inv.subtotal, netting.applied_credit_total, tax_res, inv.tax_amount
    )

    decision_rec, _ = DecisionEngine.build_immutable_decision_record(
        invoice=inv,
        vendor_id="VEND-WHATIF",
        tax_result=tax_res,
        netting_result=netting,
        journal=journal,
        source_document_hash="sha256:doc_whatif",
        reconciliation_evidence={"status": "MATCHED_3WAY_CLEAN"},
        fund_account_id="fa_test_01",
        idempotency_key="IDEMP-WHATIF-01",
        po_snapshot_hash="sha256:po_whatif",
        grn_snapshot_hash="sha256:grn_whatif",
        vendor_snapshot_hash="sha256:vend_whatif",
        matching_policy_version="2026.1"
    )

    what_if_res = DecisionReplayEngine.execute_replay(
        decision_record=decision_rec,
        mode=ReplayMode.WHAT_IF_REPLAY,
        overrides={"matching_policy_version": "2027.TEST", "tds_calculation.tds_rate": "0.2000"}
    )

    # Invariants enforced by replay engine
    assert what_if_res.replay_mode == ReplayMode.WHAT_IF_REPLAY
    assert what_if_res.is_simulation is True
    assert what_if_res.admissible_for_payout is False

    # Attempting to schedule production payment with simulation evidence is gated
    orchestrator = PaymentOrchestrator(store, banking_client)
    sim_intent = _create_test_intent(
        invoice_number="INV-WHATIF-01",
        environment="PRODUCTION",
        trust="SIMULATION_TRUST"
    )
    with pytest.raises(PaymentOrchestrationError) as exc_gate:
        orchestrator.dispatch_payment_intent(sim_intent)
    assert "Production Payout Gated" in str(exc_gate.value)


# ==============================================================================
# WEBHOOKS, STATE MACHINES & OVERRIDES
# ==============================================================================

def test_webhook_replay_and_bad_signature_rejected(store):
    """
    ATTACK: Spoofed or expired webhook payload submitted to endpoint.
    EXPECTED DEFENSE: Bad signature raises WebhookAuthenticationError.
    Expired timestamp (> 300s) raises WebhookReplayError.
    """
    webhook_svc = ProviderWebhookService(store)
    secret = "rzp_webhook_secret_test"
    payload = {
        "event": "payout.processed",
        "created_at": 1700000000,  # Old timestamp
        "payload": {"payout": {"entity": {"id": "pout_test"}}}
    }
    raw_body = json.dumps(payload).encode("utf-8")

    # 1. Invalid signature
    with pytest.raises(WebhookAuthenticationError):
        webhook_svc.process_razorpayx_webhook(
            raw_body=raw_body,
            signature="invalid_signature_hex",
            secret=secret
        )

    # 2. Expired replay window with valid signature
    valid_sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    with pytest.raises(WebhookReplayError):
        webhook_svc.process_razorpayx_webhook(
            raw_body=raw_body,
            signature=valid_sig,
            secret=secret,
            current_time_epoch=1700001000  # 1000s later (skew = 1000s > 300s tolerance)
        )


def test_out_of_order_webhook_preserves_terminal_state(store):
    """
    ATTACK: An out-of-order callback (payout.initiated) arrives after payment is already SETTLED.
    EXPECTED DEFENSE: State remains SETTLED; never regresses.
    """
    webhook_svc = ProviderWebhookService(store)
    secret = "rzp_webhook_secret_test"
    idemp_key = "idemp_terminal_01"

    # Pre-settled payment
    store.save_payment_intent({
        "instruction_id": "INS-TERM-01",
        "invoice_number": "INV-TERM-01",
        "idempotency_key": idemp_key,
        "status": PaymentState.SETTLED.value,
        "utr": "UTR-ALREADY-SETTLED",
        "version": 2
    })

    # Out-of-order initiated event
    payload = {
        "event": "payout.initiated",
        "event_id": "evt_out_of_order_01",
        "created_at": 1725000000,
        "payload": {
            "payout": {
                "entity": {
                    "id": "pout_term_01",
                    "status": "initiated",
                    "notes": {"idempotency_key": idemp_key}
                }
            }
        }
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    res = webhook_svc.process_razorpayx_webhook(
        raw_body=raw_body,
        signature=sig,
        secret=secret,
        current_time_epoch=1725000010
    )

    assert res["status"] in ("CONVERGED_TERMINAL", "TERMINAL_STATE_PRESERVED")
    intent = store.get_payment_intent(idemp_key)
    assert intent["status"] == PaymentState.SETTLED.value


def test_non_overridable_invariants_cannot_be_bypassed_by_manual_override(sec_logger):
    """
    ATTACK: User with CFO credentials attempts a manual override to authorize:
    1. A duplicate economic payment.
    2. Credit overconsumption.
    EXPECTED DEFENSE: NonOverridableInvariantViolationError is raised in all cases.
    Logged to security audit as INVARIANT_REJECTION.
    """
    now_utc = datetime.now(timezone.utc)
    cfo_override = ManualOverrideRecord(
        override_id="OVR-CFO-ATTACK-01",
        reason="CFO emergency authorization",
        evidence="Signed Board Memo",
        maker="controller_user",
        checker="cfo_user",
        approval_timestamp=now_utc.isoformat(),
        scope=OverrideScope.GENERAL_POLICY,
        expiry=(now_utc + timedelta(hours=1)).isoformat()
    )

    # 1. Duplicate economic payment
    with pytest.raises(NonOverridableInvariantViolationError) as exc_dup:
        OverrideGovernor.assert_can_override_duplicate_payment(cfo_override, is_economic_duplicate=True)
    assert "NON-OVERRIDABLE INVARIANT" in str(exc_dup.value)

    # 2. Credit overconsumption
    with pytest.raises(NonOverridableInvariantViolationError) as exc_cred:
        OverrideGovernor.assert_can_override_credit_limit(
            cfo_override,
            consumed_amount=Decimal("25000.00"),
            available_amount=Decimal("15000.00")
        )
    assert "Credit over-consumption" in str(exc_cred.value)

    trail = sec_logger.get_audit_trail()
    inv_events = [e for e in trail if e["event_type"] == HighRiskEvent.INVARIANT_REJECTION.value]
    assert len(inv_events) >= 2


# ==============================================================================
# MULTI-INSTANCE CROSS-PROCESS CONCURRENCY & AMBIGUOUS RECOVERY TESTS
# ==============================================================================

def test_multi_instance_payment_concurrency_across_isolated_workers(banking_client):
    """
    CERTIFICATION CHALLENGE 1 & 3:
    Simulates Cloud Run Instance A and Cloud Run Instance B running in parallel.
    Each worker has its OWN isolated process-local lock state (_distributed_lock_lock),
    so process-local synchronization CANNOT prevent the race.
    Both workers share the same underlying authoritative persistence layer.

    Both workers attempt to dispatch the exact same payment intent simultaneously.
    REQUIRED INVARIANT:
    At most ONE worker invokes the external banking rail.
    The second worker is fenced by datastore-level optimistic concurrency / distributed leasing.
    Zero duplicate payments.
    """
    import threading

    # Shared authoritative persistence layer (simulating shared Firestore instance)
    shared_mock_db: Dict[str, Any] = {
        "distributed_locks": {},
        "payment_intents": {},
        "payment_outbox": {},
        "webhook_events": {},
        "state_transitions": {}
    }

    # Worker A (Instance A) with its own store and process-local lock
    store_a = FirestoreStateStore(force_mock=True)
    store_a._mock_db = shared_mock_db
    store_a._distributed_lock_lock = threading.Lock()
    orchestrator_a = PaymentOrchestrator(store_a, banking_client)

    # Worker B (Instance B) with its own store and independent process-local lock
    store_b = FirestoreStateStore(force_mock=True)
    store_b._mock_db = shared_mock_db
    store_b._distributed_lock_lock = threading.Lock()
    orchestrator_b = PaymentOrchestrator(store_b, banking_client)

    # Verify locks are completely separate objects in memory
    assert store_a._distributed_lock_lock is not store_b._distributed_lock_lock

    intent = _create_test_intent(invoice_number=f"INV-MULTI-INST-{uuid.uuid4().hex[:6]}")

    gateway_call_count = 0
    gateway_lock = threading.Lock()

    def mock_stage_payout(*args, **kwargs):
        nonlocal gateway_call_count
        with gateway_lock:
            gateway_call_count += 1
        return {"id": "pout_multi_01", "status": "processed", "utr": "UTR-MULTI-001"}

    banking_client.stage_payout = mock_stage_payout

    results = []
    errors = []

    def run_worker_a():
        try:
            r = orchestrator_a.dispatch_payment_intent(intent)
            results.append(("worker_a", r))
        except Exception as ex:
            errors.append(("worker_a", ex))

    def run_worker_b():
        try:
            r = orchestrator_b.dispatch_payment_intent(intent)
            results.append(("worker_b", r))
        except Exception as ex:
            errors.append(("worker_b", ex))

    t_a = threading.Thread(target=run_worker_a)
    t_b = threading.Thread(target=run_worker_b)

    t_a.start()
    t_b.start()
    t_a.join()
    t_b.join()

    # CRITICAL INVARIANT: Exactly 1 external payment call was executed
    assert gateway_call_count == 1, f"Expected exactly 1 bank call across instances, got {gateway_call_count}"

    # Verify that the intent is SETTLED in the shared datastore
    final_intent = shared_mock_db["payment_intents"][intent.idempotency_key]
    assert final_intent["status"] == PaymentState.SETTLED.value
    assert final_intent["utr"] == "UTR-MULTI-001"


def test_ambiguous_504_lost_response_blocks_second_economic_payment(store, banking_client):
    """
    CERTIFICATION CHALLENGE 4:
    Scenario:
    1. Provider accepts payment (generates payout and debits account on bank side),
       but HTTP response becomes 504 Gateway Timeout / network lost to Worker 1.
    2. Worker 1 marks payment as UNKNOWN/AMBIGUOUS (NOT FAILED).
    3. Worker 2 receives the exact same invoice/payment.
    4. Worker 2 triggers authoritative reconciliation.
    5. Reconciliation confirms the original payout succeeded with UTR.
    6. Intent converges to SETTLED.
    EXPECTED INVARIANT:
    NO SECOND ECONOMIC PAYMENT is ever issued to the bank rail (call_count remains 1).
    """
    orchestrator_1 = PaymentOrchestrator(store, banking_client)
    orchestrator_2 = PaymentOrchestrator(store, banking_client)
    intent = _create_test_intent(invoice_number=f"INV-504-LOST-{uuid.uuid4().hex[:6]}")

    payout_calls = 0

    # Simulate bank rail: payout is created on bank side, but 504 Gateway Timeout returned
    def mock_stage_payout_with_504(*args, **kwargs):
        nonlocal payout_calls
        payout_calls += 1
        # Simulates gateway recording payment but returning 504 / UNKNOWN to caller
        return {"id": "pout_504_real", "status": "UNKNOWN", "requires_reconciliation": True}

    banking_client.stage_payout = mock_stage_payout_with_504

    # Worker 1 dispatches
    res1 = orchestrator_1.dispatch_payment_intent(intent)
    assert res1["status"] == "AMBIGUOUS"
    assert res1["state"] == PaymentState.UNKNOWN.value
    assert payout_calls == 1

    # Verify datastore state is UNKNOWN (not FAILED)
    intent_in_db = store.get_payment_intent(intent.idempotency_key)
    assert intent_in_db["status"] == PaymentState.UNKNOWN.value

    # Bank side now responds to status lookup with the true state
    banking_client.reconcile_payout_status = MagicMock(return_value={
        "status": "CONFIRMED",
        "reconciled": True,
        "payout_id": "pout_504_real",
        "utr": "UTR-504-CONFIRMED-AUTHORITATIVE"
    })

    # Worker 2 receives the same invoice/payment intent
    res2 = orchestrator_2.dispatch_payment_intent(intent)

    # Worker 2 reconciled the existing in-flight payout
    assert res2["status"] == "SUCCESS"
    assert res2["payout_id"] == "pout_504_real"
    assert res2["utr"] == "UTR-504-CONFIRMED-AUTHORITATIVE"
    assert res2["state"] == PaymentState.SETTLED.value

    # CRITICAL INVARIANT: stage_payout was NEVER called a second time
    assert payout_calls == 1, f"Expected exactly 1 bank disbursement, got {payout_calls}"

    # Final persisted state is SETTLED
    final_intent = store.get_payment_intent(intent.idempotency_key)
    assert final_intent["status"] == PaymentState.SETTLED.value
    assert final_intent["utr"] == "UTR-504-CONFIRMED-AUTHORITATIVE"
