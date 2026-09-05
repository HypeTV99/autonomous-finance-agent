from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import pytest
from typing import Any, Dict

from firestore_store import FirestoreStateStore
from schemas import (
    DuplicateCheckResult,
    DuplicateDisposition,
    ManualOverrideRecord,
    OverrideScope,
    PaymentInstruction,
    PaymentState,
    TDSSection,
)


def _make_test_payment_instruction(
    instruction_id: str,
    invoice_number: str,
    vendor_id: str,
    idempotency_key: str,
    status: PaymentState = PaymentState.UNKNOWN,
    gross_amount: Decimal = Decimal("10000.00"),
    net_payout: Decimal = Decimal("9000.00")
) -> PaymentInstruction:
    return PaymentInstruction(
        instruction_id=instruction_id,
        invoice_number=invoice_number,
        vendor_id=vendor_id,
        vendor_pan="AAACB1234K",
        fiscal_year="2026-27",
        fund_account_id="fa_test_01",
        gross_subtotal=gross_amount,
        tax_amount=Decimal("0.00"),
        tds_withheld=Decimal("0.00"),
        tds_section=TDSSection.NONE,
        applied_credits_total=Decimal("0.00"),
        net_payout_amount=net_payout,
        payout_paise=int(net_payout * 100),
        requires_zero_payout_hold=False,
        bank_account_number="1122334455",
        bank_ifsc="HDFC0001234",
        beneficiary_name="XYZ Corp",
        idempotency_key=idempotency_key,
        status=status
    )
from services.duplicate_detector import MultiSignalDuplicateDetector
from services.override_governor import (
    InsufficientOverrideScopeError,
    MakerCheckerViolationError,
    NonOverridableInvariantViolationError,
    OverrideExpiredError,
    OverrideGovernor,
)
from services.payment_orchestrator import (
    PaymentOrchestrationError,
    PaymentOrchestrator,
    PaymentStaleVersionError,
    PaymentStateMachine,
)
from services.webhook_service import (
    ProviderWebhookService,
    WebhookAuthenticationError,
    WebhookReplayError,
)


# ==============================================================================
# 1. LAYERED DUPLICATE INVOICE DEFENSES
# ==============================================================================

def test_duplicate_document_renamed_content_hash_blocked():
    """
    Layer 1: Renamed PDF with different invoice number and filename,
    but identical cryptographic SHA-256 content hash must be BLOCKed.
    """
    shared_hash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    existing = [
        {
            "id": "INV-ORIG-001",
            "invoice_number": "INV-ORIG-001",
            "vendor_id": "VEND-ACME-01",
            "vendor_name": "Acme Industrial Pvt Ltd",
            "content_hash": shared_hash,
            "gross_amount": "50000.00"
        }
    ]

    result = MultiSignalDuplicateDetector.evaluate_invoice(
        new_invoice_number="INV-RENAMED-999",
        new_vendor_id="VEND-ACME-01",
        new_vendor_name="Acme Industrial Pvt Ltd",
        new_gross_amount=Decimal("50000.00"),
        existing_decisions=existing,
        new_document_hash=shared_hash
    )

    assert result.disposition == DuplicateDisposition.BLOCK
    assert result.matched_signal == "DOCUMENT_HASH"
    assert result.is_blocked is True
    assert result.requires_review is False
    assert "Cryptographic document collision" in result.reason


def test_duplicate_hard_business_identity_blocked():
    """
    Layer 2: Exact business identity (PAN / Vendor ID + Invoice Number) must be BLOCKed.
    """
    existing = [
        {
            "id": "INV-2026-8801",
            "invoice_number": "INV-2026-8801",
            "vendor_id": "VEND-TATA-01",
            "vendor_name": "Tata Consultancy Services Ltd",
            "vendor_pan": "AAACT1234F",
            "gross_amount": "125000.00"
        }
    ]

    result = MultiSignalDuplicateDetector.evaluate_invoice(
        new_invoice_number="INV-2026-8801",
        new_vendor_id="VEND-TATA-01",
        new_vendor_name="Tata Consultancy Services Ltd",
        new_gross_amount=Decimal("125000.00"),
        existing_decisions=existing,
        new_vendor_pan="AAACT1234F"
    )

    assert result.disposition == DuplicateDisposition.BLOCK
    assert result.matched_signal == "HARD_IDENTITY"
    assert result.is_blocked is True
    assert "EXACT DUPLICATE" in result.reason


def test_duplicate_normalized_ocr_variation_blocked():
    """
    Layer 3: Cautious normalization strips hyphens, slashes, whitespace,
    and safe leading zeroes, catching OCR artifacts without false positives.
    INV-00123 must collide with INV123 under same vendor.
    """
    existing = [
        {
            "id": "INV123",
            "invoice_number": "INV123",
            "vendor_id": "VEND-BHARTI-01",
            "vendor_name": "Bharti Airtel Ltd",
            "gross_amount": "45000.00"
        }
    ]

    # Incoming variation: INV-00123
    result = MultiSignalDuplicateDetector.evaluate_invoice(
        new_invoice_number="INV-00123",
        new_vendor_id="VEND-BHARTI-01",
        new_vendor_name="Bharti Airtel Ltd",
        new_gross_amount=Decimal("45000.00"),
        existing_decisions=existing
    )

    assert result.disposition == DuplicateDisposition.BLOCK
    assert result.matched_signal == "NORMALIZED_IDENTITY"
    assert result.is_blocked is True
    assert "NORMALIZED DUPLICATE COLLISION" in result.reason


def test_similar_invoice_routes_to_review_not_blocked():
    """
    Layer 4: Fuzzy economic similarity (same vendor, same recurring amount within date window,
    but distinct invoice number) must route to REVIEW, NOT permanently BLOCKed.
    """
    now = datetime.now(timezone.utc)
    existing = [
        {
            "id": "INV-OCT-01",
            "invoice_number": "INV-OCT-01",
            "vendor_id": "VEND-OFFICE-01",
            "vendor_name": "Regus Co-working Spaces",
            "gross_amount": "80000.00",
            "decision_timestamp": (now - timedelta(days=20)).isoformat()
        }
    ]

    # November recurring rent invoice: same vendor, same amount, but distinct number
    result = MultiSignalDuplicateDetector.evaluate_invoice(
        new_invoice_number="INV-NOV-01",
        new_vendor_id="VEND-OFFICE-01",
        new_vendor_name="Regus Co-working Spaces",
        new_gross_amount=Decimal("80000.00"),
        existing_decisions=existing,
        current_time=now
    )

    # Must be REVIEW, NOT permanent BLOCK
    assert result.disposition == DuplicateDisposition.REVIEW
    assert result.matched_signal == "ECONOMIC_SIMILARITY"
    assert result.is_blocked is False
    assert result.requires_review is True
    assert "Requires human review" in result.reason


# ==============================================================================
# 2. PERSISTENCE-LEVEL ATOMIC IDEMPOTENCY
# ==============================================================================

def test_persistence_atomic_invoice_registration_race_free():
    """
    Concurrent workers attempting to register the exact same invoice business key
    must race cleanly: exactly ONE succeeds, and all other workers are safely rejected.
    """
    store = FirestoreStateStore()
    business_key = "AAACB1234K_INV-2026-CONC_2026-27"
    content_hash = "abcde1234567890abcdef1234567890abcdef1234567890abcdef1234567890"

    results = []

    def attempt_registration(worker_id: int):
        success, reason = store.atomic_register_invoice_business_key(
            business_key=business_key,
            content_hash=content_hash,
            metadata={"worker_id": worker_id}
        )
        return success, reason

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(attempt_registration, i) for i in range(8)]
        for f in futures:
            results.append(f.result())

    success_count = sum(1 for success, _ in results if success is True)
    failure_count = sum(1 for success, _ in results if success is False)

    assert success_count == 1
    assert failure_count == 7


# ==============================================================================
# 3. WEBHOOK AUTHENTICATION, DEDUPLICATION, AND REPLAY DEFENSES
# ==============================================================================

def test_webhook_invalid_signature_rejected():
    """Webhook callback with tampered body or invalid HMAC signature must fail authentication."""
    store = FirestoreStateStore()
    service = ProviderWebhookService(store=store)

    raw_body = b'{"event": "payout.processed", "id": "evt_test_01"}'
    invalid_signature = "bad_signature_deadbeef"
    secret = "whsec_super_secret"

    with pytest.raises(WebhookAuthenticationError, match="Invalid webhook signature"):
        service.process_razorpayx_webhook(
            raw_body=raw_body,
            signature=invalid_signature,
            secret=secret
        )


def test_webhook_replay_window_expired():
    """Webhook callback timestamp skew exceeding 300 seconds must be rejected."""
    store = FirestoreStateStore()
    service = ProviderWebhookService(store=store)

    secret = "whsec_super_secret"
    old_time = 1700000000  # Stale timestamp
    current_time = old_time + 400.0  # 400 seconds later (> 300s tolerance)

    payload_dict = {
        "event": "payout.processed",
        "event_id": "evt_stale_99",
        "created_at": old_time
    }
    raw_body = json.dumps(payload_dict).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    with pytest.raises(WebhookReplayError, match="exceeds replay window tolerance"):
        service.process_razorpayx_webhook(
            raw_body=raw_body,
            signature=sig,
            secret=secret,
            current_time_epoch=current_time
        )


def test_webhook_duplicate_event_id_idempotent():
    """Duplicate delivery of same webhook event_id returns idempotent acknowledgment without re-executing transitions."""
    store = FirestoreStateStore()
    service = ProviderWebhookService(store=store)
    secret = "whsec_test_secret"

    payload_dict = {
        "event": "payout.processed",
        "event_id": "evt_duplicate_claim_01",
        "created_at": 1725000000
    }
    raw_body = json.dumps(payload_dict).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    # First delivery
    res1 = service.process_razorpayx_webhook(
        raw_body=raw_body,
        signature=sig,
        secret=secret,
        current_time_epoch=1725000010
    )
    assert res1["status"] in ("ACKNOWLEDGED", "SETTLED")

    # Duplicate delivery
    res2 = service.process_razorpayx_webhook(
        raw_body=raw_body,
        signature=sig,
        secret=secret,
        current_time_epoch=1725000015
    )
    assert res2["status"] == "DUPLICATE_IGNORED"
    assert res2["event_id"] == "evt_duplicate_claim_01"


def test_webhook_out_of_order_event_does_not_regress_terminal_state():
    """
    An out-of-order callback (e.g. payout.initiated or payout.pending) arriving after
    an intent is already SETTLED must never regress the settled state.
    """
    store = FirestoreStateStore()
    service = ProviderWebhookService(store=store)
    secret = "whsec_test_secret"
    idempotency_key = "idemp_test_terminal_protection"

    # Pre-seed intent in SETTLED state
    store.save_payment_intent({
        "instruction_id": "INS-TERM-01",
        "idempotency_key": idempotency_key,
        "amount": "10000.00",
        "status": PaymentState.SETTLED.value,
        "utr": "RZX_FINAL_UTR_999",
        "version": 3
    })

    # Out-of-order payout.initiated arrives
    payload_dict = {
        "event": "payout.initiated",
        "event_id": "evt_out_of_order_01",
        "created_at": 1725000000,
        "payload": {
            "payout": {
                "entity": {
                    "id": "pout_ooo_01",
                    "status": "pending",
                    "notes": {"idempotency_key": idempotency_key}
                }
            }
        }
    }
    raw_body = json.dumps(payload_dict).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    res = service.process_razorpayx_webhook(
        raw_body=raw_body,
        signature=sig,
        secret=secret,
        current_time_epoch=1725000010
    )

    assert res["status"] == "CONVERGED_TERMINAL"
    assert res["current_state"] == PaymentState.SETTLED.value

    # Verify intent state in store was NOT regressed
    intent = store.get_payment_intent(idempotency_key)
    assert intent["status"] == PaymentState.SETTLED.value
    assert intent["utr"] == "RZX_FINAL_UTR_999"


def test_webhook_synchronous_response_race_convergence():
    """
    Synchronous response and asynchronous webhook race: both converge cleanly to SETTLED
    without conflict or error.
    """
    store = FirestoreStateStore()
    service = ProviderWebhookService(store=store)
    secret = "whsec_test_secret"
    idempotency_key = "idemp_sync_async_race"

    store.save_payment_intent({
        "instruction_id": "INS-RACE-01",
        "idempotency_key": idempotency_key,
        "amount": "25000.00",
        "status": PaymentState.SUBMITTED.value,
        "version": 1
    })

    # Webhook arrives
    payload_dict = {
        "event": "payout.processed",
        "event_id": "evt_race_webhook_01",
        "created_at": 1725000000,
        "payload": {
            "payout": {
                "entity": {
                    "id": "pout_sync_race_01",
                    "status": "processed",
                    "utr": "RZX_SYNC_RACE_UTR",
                    "notes": {"idempotency_key": idempotency_key}
                }
            }
        }
    }
    raw_body = json.dumps(payload_dict).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    res = service.process_razorpayx_webhook(
        raw_body=raw_body,
        signature=sig,
        secret=secret,
        current_time_epoch=1725000005
    )

    assert res["status"] == "SETTLED"
    assert res["utr"] == "RZX_SYNC_RACE_UTR"

    intent = store.get_payment_intent(idempotency_key)
    assert intent["status"] == PaymentState.SETTLED.value
    assert intent["utr"] == "RZX_SYNC_RACE_UTR"


def test_webhook_payout_reversed_fences_accounting_reversal():
    """
    payout.reversed callback must NOT trigger autonomous GL journal reversal.
    It must fence the intent in REVERSAL_PENDING_APPROVAL requiring human Controller signoff.
    """
    store = FirestoreStateStore()
    service = ProviderWebhookService(store=store)
    secret = "whsec_test_secret"
    idempotency_key = "idemp_reversal_fenced"

    store.save_payment_intent({
        "instruction_id": "INS-REV-01",
        "idempotency_key": idempotency_key,
        "amount": "50000.00",
        "status": PaymentState.SETTLED.value,
        "utr": "RZX_REV_ORIG_UTR",
        "version": 2
    })

    payload_dict = {
        "event": "payout.reversed",
        "event_id": "evt_bank_reversal_01",
        "created_at": 1725000000,
        "payload": {
            "payout": {
                "entity": {
                    "id": "pout_reversed_99",
                    "status": "reversed",
                    "failure_reason": "Beneficiary account frozen by bank",
                    "notes": {"idempotency_key": idempotency_key}
                }
            }
        }
    }
    raw_body = json.dumps(payload_dict).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    res = service.process_razorpayx_webhook(
        raw_body=raw_body,
        signature=sig,
        secret=secret,
        current_time_epoch=1725000010
    )

    assert res["status"] == "REVERSAL_PENDING_APPROVAL"
    assert res["requires_manual_approval"] is True

    intent = store.get_payment_intent(idempotency_key)
    assert intent.get("reversal_pending_approval") is True
    assert intent.get("reversal_payout_id") == "pout_reversed_99"


# ==============================================================================
# 4. RECONCILIATION SAFETY & HIGH-RISK FENCING
# ==============================================================================

class MockBankingClient:
    def __init__(self, recon_response: Dict[str, Any]):
        self.recon_response = recon_response

    def reconcile_payout_status(self, idempotency_key: str, reference_id: str):
        return self.recon_response


def test_reconciliation_ambiguous_payment_does_not_create_replacement():
    """
    When gateway reconciliation returns indeterminate/ambiguous status,
    system preserves UNKNOWN state and strictly refrains from creating duplicate replacement payouts.
    """
    store = FirestoreStateStore()
    client = MockBankingClient(recon_response={"status": "AMBIGUOUS", "reconciled": False})
    orchestrator = PaymentOrchestrator(store=store, banking_client=client)

    intent = _make_test_payment_instruction(
        instruction_id="INS-AMBIG-01",
        invoice_number="INV-9901",
        vendor_id="VEND-XYZ",
        gross_amount=Decimal("10000.00"),
        net_payout=Decimal("9000.00"),
        idempotency_key="idemp_ambig_01",
        status=PaymentState.UNKNOWN
    )
    store.save_payment_intent(intent.model_dump(mode="json"))

    res = orchestrator.reconcile_ambiguous_intent(intent, client=client)

    assert res["reconciled"] is False
    assert res["status"] == "AMBIGUOUS"

    # Verify intent state remains UNKNOWN and no payout was disbursed
    current = store.get_payment_intent("idemp_ambig_01")
    assert current["status"] == PaymentState.UNKNOWN.value


def test_reconciliation_safe_status_query_retry_attaches_utr():
    """
    Safe autonomous action: idempotent gateway poll detects confirmed settlement
    and safely attaches UTR evidence and marks SETTLED.
    """
    store = FirestoreStateStore()
    client = MockBankingClient(recon_response={
        "status": "PROCESSED",
        "reconciled": True,
        "payout_id": "pout_settled_123",
        "utr": "RZX_RECON_UTR_456"
    })
    orchestrator = PaymentOrchestrator(store=store, banking_client=client)

    intent = _make_test_payment_instruction(
        instruction_id="INS-RECON-01",
        invoice_number="INV-9902",
        vendor_id="VEND-XYZ",
        gross_amount=Decimal("20000.00"),
        net_payout=Decimal("18000.00"),
        idempotency_key="idemp_recon_safe_01",
        status=PaymentState.UNKNOWN
    )
    store.save_payment_intent(intent.model_dump(mode="json"))

    res = orchestrator.reconcile_ambiguous_intent(intent, client=client)

    assert res["reconciled"] is True
    assert res["status"] == "CONFIRMED"
    assert res["utr"] == "RZX_RECON_UTR_456"

    current = store.get_payment_intent("idemp_recon_safe_01")
    assert current["status"] == PaymentState.SETTLED.value
    assert current["utr"] == "RZX_RECON_UTR_456"


def test_reconciliation_high_risk_actions_require_approval():
    """
    High-risk actions (WRITE_OFF, REPLACEMENT_PAYOUT, REVERSE_GL) cannot execute autonomously
    and require explicit Controller approval token.
    """
    orchestrator = PaymentOrchestrator()
    intent = _make_test_payment_instruction(
        instruction_id="INS-RISK-01",
        invoice_number="INV-9903",
        vendor_id="VEND-XYZ",
        gross_amount=Decimal("50000.00"),
        net_payout=Decimal("45000.00"),
        idempotency_key="idemp_high_risk_01"
    )

    # 1. Autonomous execution without approval must be rejected
    with pytest.raises(PaymentOrchestrationError, match="strictly requires explicit Controller approval"):
        orchestrator.execute_high_risk_reconciliation_action(
            action_type="WRITE_OFF",
            intent=intent,
            approval_token=None,
            controller_id=None
        )

    # 2. Executing with valid dual approval succeeds
    res = orchestrator.execute_high_risk_reconciliation_action(
        action_type="WRITE_OFF",
        intent=intent,
        approval_token="tok_controller_cfo_approved_99",
        controller_id="ctrl_suresh_nair"
    )
    assert res["status"] == "APPROVED_ACTION_EXECUTED"
    assert res["controller_id"] == "ctrl_suresh_nair"


# ==============================================================================
# 5. STATE MACHINE HARDENING & VERSIONING
# ==============================================================================

def test_state_machine_illegal_transition_rejected():
    """State machine rejects illegal transition (e.g. CREATED -> SETTLED, or SETTLED -> PENDING)."""
    with pytest.raises(PaymentOrchestrationError, match="Invalid payment transition"):
        PaymentStateMachine.validate_transition(
            from_state=PaymentState.CREATED,
            to_state=PaymentState.SETTLED
        )

    with pytest.raises(PaymentOrchestrationError, match="Invalid payment transition"):
        PaymentStateMachine.validate_transition(
            from_state=PaymentState.SETTLED,
            to_state=PaymentState.PENDING
        )


def test_state_machine_stale_version_precondition_rejected():
    """Optimistic locking rejects transition if expected_version != current_version."""
    with pytest.raises(PaymentStaleVersionError, match="version precondition failed"):
        PaymentStateMachine.validate_transition(
            from_state=PaymentState.READY_FOR_SUBMISSION,
            to_state=PaymentState.SUBMISSION_PENDING,
            expected_version=1,
            current_version=2,
            idempotency_key="idemp_stale_ver_test"
        )


# ==============================================================================
# 6. MANUAL OVERRIDES: DUAL-CONTROL, SCOPE & EXPIRY
# ==============================================================================

def test_override_maker_equals_checker_rejected():
    """Manual override where maker and checker are identical violates Segregation of Duties."""
    record = ManualOverrideRecord(
        override_id="OVR-2026-001",
        reason="Expedite vendor payment",
        evidence="Vendor urgent escalation email",
        maker="ap_clerk_rajesh",
        checker="ap_clerk_rajesh",  # Maker == Checker
        approval_timestamp=datetime.now(timezone.utc).isoformat(),
        scope=OverrideScope.GENERAL_POLICY
    )

    with pytest.raises(MakerCheckerViolationError, match="Dual-control violation"):
        OverrideGovernor.validate_override(record, required_scope=OverrideScope.GENERAL_POLICY)


def test_override_expired_and_insufficient_scope_rejected():
    """Expired override or override with insufficient scope must be rejected."""
    now = datetime.now(timezone.utc)
    expired_ts = (now - timedelta(hours=2)).isoformat()

    # Expired override
    expired_record = ManualOverrideRecord(
        override_id="OVR-2026-002",
        reason="Vendor bank cooling bypass",
        evidence="CFO signoff on ticket 404",
        maker="ap_clerk_rajesh",
        checker="controller_suresh",
        approval_timestamp=(now - timedelta(hours=4)).isoformat(),
        scope=OverrideScope.BANK_COOLING_PERIOD,
        expiry=expired_ts
    )
    with pytest.raises(OverrideExpiredError, match="expired"):
        OverrideGovernor.validate_override(
            expired_record,
            required_scope=OverrideScope.BANK_COOLING_PERIOD,
            current_time=now
        )

    # Valid time, but wrong scope
    valid_record = ManualOverrideRecord(
        override_id="OVR-2026-003",
        reason="Bypass cooling period",
        evidence="Ticket approval",
        maker="ap_clerk_rajesh",
        checker="controller_suresh",
        approval_timestamp=now.isoformat(),
        scope=OverrideScope.BANK_COOLING_PERIOD,
        expiry=(now + timedelta(hours=24)).isoformat()
    )
    with pytest.raises(InsufficientOverrideScopeError, match="does not grant required authority"):
        OverrideGovernor.validate_override(
            valid_record,
            required_scope=OverrideScope.TOLERANCE_VARIANCE,
            current_time=now
        )


# ==============================================================================
# 7. NON-OVERRIDABLE INVARIANT DEFENSES
# ==============================================================================

def test_non_overridable_invariants_cannot_be_bypassed():
    """
    Even with a validly approved Dual-Control ManualOverrideRecord,
    non-overridable core invariants can NEVER be bypassed.
    """
    valid_override = ManualOverrideRecord(
        override_id="OVR-2026-SUPER-CFO",
        reason="Board executive directive",
        evidence="Executive committee resolution",
        maker="controller_suresh",
        checker="cfo_ananya",
        approval_timestamp=datetime.now(timezone.utc).isoformat(),
        scope=OverrideScope.GENERAL_POLICY
    )

    # Invariant 1: Duplicate economic payment cannot be authorized
    with pytest.raises(NonOverridableInvariantViolationError, match="Duplicate economic payment cannot be authorized"):
        OverrideGovernor.assert_can_override_duplicate_payment(
            override=valid_override,
            is_economic_duplicate=True
        )

    # Invariant 2: Credit over-consumption cannot be authorized
    with pytest.raises(NonOverridableInvariantViolationError, match="Credit over-consumption cannot be authorized"):
        OverrideGovernor.assert_can_override_credit_limit(
            override=valid_override,
            consumed_amount=Decimal("15000.00"),
            available_amount=Decimal("10000.00")
        )

    # Invariant 3: Unbalanced general ledger journals cannot be authorized
    with pytest.raises(NonOverridableInvariantViolationError, match="Unbalanced general ledger journal cannot be authorized"):
        OverrideGovernor.assert_can_override_unbalanced_journal(
            override=valid_override,
            total_debits=Decimal("10000.00"),
            total_credits=Decimal("9500.00")
        )

    # Invariant 4: Historical decision mutation cannot be authorized
    with pytest.raises(NonOverridableInvariantViolationError, match="Historical decision attestation and signed evidence cannot be mutated"):
        OverrideGovernor.assert_can_override_historical_mutation(override=valid_override)

    # Invariant 5: Simulation data cannot be authorized for live disbursals
    with pytest.raises(NonOverridableInvariantViolationError, match="Simulation / mock financial artifacts cannot be routed"):
        OverrideGovernor.assert_can_override_simulation_mode(
            override=valid_override,
            is_simulation=True,
            is_live_disbursal=True
        )

    # Invariant 6: Procurement quantity expansion beyond PO ceiling cannot be authorized without formal PO amendment
    with pytest.raises(NonOverridableInvariantViolationError, match="exceeds authorized PO quantity"):
        OverrideGovernor.assert_can_override_po_quantity(
            override=valid_override,
            cumulative_qty=Decimal("150.00"),
            authorized_po_qty=Decimal("100.00")
        )
