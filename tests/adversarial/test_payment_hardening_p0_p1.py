import concurrent.futures
from datetime import datetime, timezone
from decimal import Decimal
import threading
import time
from typing import Any, Dict
import uuid

import pytest
from starlette.testclient import TestClient

from firestore_store import FirestoreStateStore
import main
from razorpayx_client import RazorpayXBankingClient
from schemas import (
    OutboxEventStatus,
    OutboxWorkItem,
    PaymentInstruction,
    PaymentState,
    TDSSection
)
from services.payment_orchestrator import (
    PaymentAmbiguousOutcomeError,
    PaymentMaterialConflictError,
    PaymentOrchestrator,
    PaymentStateMachine
)


@pytest.fixture
def store():
    return FirestoreStateStore()


@pytest.fixture
def mock_client():
    return RazorpayXBankingClient(
        api_key="rzp_test_mock",
        api_secret="mock_secret_123",
        account_number="23232300411222"
    )


@pytest.fixture
def test_app_client():
    return TestClient(main.app)


def test_payment_stable_idempotency_retry(store, mock_client):
    """
    CRITICAL INVARIANT: Repeating payment requests with identical parameters
    produces at most ONE external financial effect and returns cached telemetry.
    """
    orchestrator = PaymentOrchestrator(store=store, banking_client=mock_client)
    inv_num = f"INV-PAY-IDEM-{uuid.uuid4().hex[:8]}"
    
    intent, is_new = orchestrator.get_or_create_payment_intent(
        invoice_number=inv_num,
        vendor_id="VEND-ALPHA",
        vendor_pan="AAACB1234K",
        fiscal_year="2026-27",
        fund_account_id="fa_alpha_01",
        gross_subtotal=Decimal("100000.00"),
        tax_amount=Decimal("18000.00"),
        tds_withheld=Decimal("2000.00"),
        tds_section=TDSSection.SECTION_194J_TECH,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("116000.00")
    )
    assert is_new is True
    
    # First execution: dispatches to banking client
    res1 = orchestrator.dispatch_payment_intent(intent)
    assert res1["status"] == "SUCCESS"
    assert res1["state"] == PaymentState.SETTLED.value
    payout_id_1 = res1["payout_id"]
    
    # Second execution (retry with same intent): must return cached result without calling provider
    intent_cached, is_new_2 = orchestrator.get_or_create_payment_intent(
        invoice_number=inv_num,
        vendor_id="VEND-ALPHA",
        vendor_pan="AAACB1234K",
        fiscal_year="2026-27",
        fund_account_id="fa_alpha_01",
        gross_subtotal=Decimal("100000.00"),
        tax_amount=Decimal("18000.00"),
        tds_withheld=Decimal("2000.00"),
        tds_section=TDSSection.SECTION_194J_TECH,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("116000.00")
    )
    assert is_new_2 is False
    res2 = orchestrator.dispatch_payment_intent(intent_cached)
    assert res2["status"] == "SUCCESS"
    assert res2.get("is_cached") is True
    assert res2["payout_id"] == payout_id_1


def test_payment_material_change_requires_distinct_authorization(store, mock_client):
    """
    MATERIAL CONFLICT PROTECTION: If any economically material attribute changes
    (e.g., amount, beneficiary), the system MUST NOT mutate the existing intent.
    It must reject with PaymentMaterialConflictError.
    """
    orchestrator = PaymentOrchestrator(store=store, banking_client=mock_client)
    inv_num = f"INV-CONFLICT-{uuid.uuid4().hex[:8]}"
    
    # Create intent for Rs. 50,000 to Account A
    intent1, _ = orchestrator.get_or_create_payment_intent(
        invoice_number=inv_num,
        vendor_id="VEND-BETA",
        vendor_pan="BBBCB1234K",
        fiscal_year="2026-27",
        fund_account_id="fa_beta_account_A",
        gross_subtotal=Decimal("50000.00"),
        tax_amount=Decimal("0.00"),
        tds_withheld=Decimal("0.00"),
        tds_section=TDSSection.NONE,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("50000.00")
    )
    store.save_payment_intent(intent1.model_dump(mode="json"))
    
    # Attacker / mutated call arrives with altered amount (Rs. 60,000) under same business key
    with pytest.raises(PaymentMaterialConflictError) as exc_info:
        orchestrator.get_or_create_payment_intent(
            invoice_number=inv_num,
            vendor_id="VEND-BETA",
            vendor_pan="BBBCB1234K",
            fiscal_year="2026-27",
            fund_account_id="fa_beta_account_A",
            gross_subtotal=Decimal("60000.00"),
            tax_amount=Decimal("0.00"),
            tds_withheld=Decimal("0.00"),
            tds_section=TDSSection.NONE,
            applied_credits=Decimal("0.00"),
            net_payout_amount=Decimal("60000.00")
        )
    assert "Material Conflict" in str(exc_info.value)
    assert "50000.00" in str(exc_info.value)
    assert "60000.00" in str(exc_info.value)


def test_payment_provider_timeout_moves_to_ambiguous_no_blind_retry(store, monkeypatch):
    """
    AMBIGUOUS OUTCOME MANDATE: When provider times out, state MUST move to UNKNOWN/AMBIGUOUS.
    The system MUST NOT blind retry or create a replacement payment automatically.
    """
    import httpx

    # Create a real banking client whose stage_payout triggers a timeout
    client = RazorpayXBankingClient("live_key", "live_sec", "232323001")
    def timeout_payout(*args, **kwargs):
        raise httpx.ReadTimeout("Banking gateway read timeout after 10.0s")
    monkeypatch.setattr(client, "stage_payout", timeout_payout)

    orchestrator = PaymentOrchestrator(store=store, banking_client=client)
    inv_num = f"INV-TIMEOUT-{uuid.uuid4().hex[:8]}"
    intent, _ = orchestrator.get_or_create_payment_intent(
        invoice_number=inv_num,
        vendor_id="VEND-GAMMA",
        vendor_pan="CCCB1234K",
        fiscal_year="2026-27",
        fund_account_id="fa_gamma_01",
        gross_subtotal=Decimal("80000.00"),
        tax_amount=Decimal("0.00"),
        tds_withheld=Decimal("0.00"),
        tds_section=TDSSection.NONE,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("80000.00")
    )

    res = orchestrator.dispatch_payment_intent(intent, client=client)
    assert res["status"] == "AMBIGUOUS"
    assert res["state"] == PaymentState.UNKNOWN.value
    assert res.get("requires_reconciliation") is True

    # Persisted state must reflect UNKNOWN / AMBIGUOUS
    persisted = store.get_payment_intent(intent.idempotency_key)
    assert persisted["status"] == PaymentState.UNKNOWN.value

    # Subsequent immediate dispatch call must REFUSE blind retry and demand reconciliation
    with pytest.raises(PaymentAmbiguousOutcomeError) as exc_info:
        orchestrator.dispatch_payment_intent(PaymentInstruction(**persisted), client=client)
    assert "AMBIGUOUS/UNKNOWN" in str(exc_info.value)
    assert "Blind resubmission blocked" in str(exc_info.value)


def test_payment_ambiguous_authoritative_reconciliation_settles(store, monkeypatch):
    """
    RECONCILIATION SUCCESS: Authoritative gateway lookup confirming an in-flight ambiguous
    transaction was processed transitions intent to SETTLED.
    """
    client = RazorpayXBankingClient("rzp_test_mock", "mock_sec", "232323001")
    orchestrator = PaymentOrchestrator(store=store, banking_client=client)
    inv_num = f"INV-RECON-OK-{uuid.uuid4().hex[:8]}"

    intent, _ = orchestrator.get_or_create_payment_intent(
        invoice_number=inv_num,
        vendor_id="VEND-DELTA",
        vendor_pan="DDDCB1234K",
        fiscal_year="2026-27",
        fund_account_id="fa_delta_01",
        gross_subtotal=Decimal("40000.00"),
        tax_amount=Decimal("0.00"),
        tds_withheld=Decimal("0.00"),
        tds_section=TDSSection.NONE,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("40000.00")
    )
    # Put in UNKNOWN state
    intent.status = PaymentState.UNKNOWN
    store.save_payment_intent(intent.model_dump(mode="json"))

    # Gateway reconcile returns confirmed status with UTR
    def mock_reconcile(idempotency_key, reference_id):
        return {"status": "CONFIRMED", "reconciled": True, "payout_id": "pout_confirmed_999", "utr": "RZXRECON999"}
    monkeypatch.setattr(client, "reconcile_payout_status", mock_reconcile)

    res = orchestrator.reconcile_ambiguous_intent(intent, client=client)
    assert res["status"] == "CONFIRMED"
    assert res["reconciled"] is True
    assert res["payout_id"] == "pout_confirmed_999"

    # Persisted intent transitioned to SETTLED
    updated = store.get_payment_intent(intent.idempotency_key)
    assert updated["status"] == PaymentState.SETTLED.value
    assert updated["provider_reference"] == "pout_confirmed_999"


def test_payment_duplicate_worker_and_queue_redelivery_safety(store, mock_client):
    """
    CONCURRENCY & WORKER REDELIVERY: Simulates 20 concurrent worker threads attempting
    to process the same payment intent. Exactly ONE external financial effect occurs.
    """
    orchestrator = PaymentOrchestrator(store=store, banking_client=mock_client)
    inv_num = f"INV-CONCURRENCY-WORKER-{uuid.uuid4().hex[:8]}"
    
    intent, _ = orchestrator.get_or_create_payment_intent(
        invoice_number=inv_num,
        vendor_id="VEND-EPSILON",
        vendor_pan="EEECB1234K",
        fiscal_year="2026-27",
        fund_account_id="fa_eps_01",
        gross_subtotal=Decimal("75000.00"),
        tax_amount=Decimal("0.00"),
        tds_withheld=Decimal("0.00"),
        tds_section=TDSSection.NONE,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("75000.00")
    )
    store.save_payment_intent(intent.model_dump(mode="json"))

    results = []
    payout_calls = []

    def spy_stage_payout(*args, **kwargs):
        payout_calls.append(kwargs)
        time.sleep(0.01)  # small window for interleaving
        return {"id": "pout_concurrency_safe", "status": "CONFIRMED", "amount": 7500000}

    mock_client.stage_payout = spy_stage_payout

    def worker_job():
        # Load fresh copy
        curr_data = store.get_payment_intent(intent.idempotency_key)
        curr_intent = PaymentInstruction(**curr_data)
        return orchestrator.dispatch_payment_intent(curr_intent, client=mock_client)

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(worker_job) for _ in range(20)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    # All 20 threads must return success
    assert len(results) == 20
    assert all(r["status"] == "SUCCESS" for r in results)
    # Exactly one external provider stage_payout execution happened
    assert len(payout_calls) == 1, f"Expected 1 external payout call, got {len(payout_calls)}"


def test_payment_zero_amount_credit_netting_bypass(store, mock_client):
    """
    ZERO-PAYOUT BYPASS: When an invoice is 100% covered by credits, payout_paise < 100.
    The system must execute a local bypass without calling the external banking gateway.
    """
    orchestrator = PaymentOrchestrator(store=store, banking_client=mock_client)
    inv_num = f"INV-ZERO-PAYOUT-{uuid.uuid4().hex[:8]}"
    
    stage_payout_invoked = []
    mock_client.stage_payout = lambda *a, **kw: stage_payout_invoked.append(kw)

    intent, _ = orchestrator.get_or_create_payment_intent(
        invoice_number=inv_num,
        vendor_id="VEND-ZETA",
        vendor_pan="ZZZCB1234K",
        fiscal_year="2026-27",
        fund_account_id="fa_zeta_01",
        gross_subtotal=Decimal("50000.00"),
        tax_amount=Decimal("0.00"),
        tds_withheld=Decimal("0.00"),
        tds_section=TDSSection.NONE,
        applied_credits=Decimal("50000.00"),  # 100% offset
        net_payout_amount=Decimal("0.00")
    )
    assert intent.requires_zero_payout_hold is True
    assert intent.payout_paise == 0

    res = orchestrator.dispatch_payment_intent(intent, client=mock_client)
    assert res["status"] == "SUCCESS"
    assert res["state"] == PaymentState.BYPASSED_ZERO_PAYOUT.value
    # Gateway was never invoked
    assert len(stage_payout_invoked) == 0


def test_payment_state_machine_terminal_protection():
    """
    TERMINAL STATE INVARIANT: A SETTLED or RECONCILED payment must NEVER be regressed
    to UNKNOWN, FAILED, or PENDING by late or out-of-order events.
    """
    assert PaymentStateMachine.can_transition(PaymentState.CREATED, PaymentState.VALIDATED) is True
    assert PaymentStateMachine.can_transition(PaymentState.VALIDATED, PaymentState.READY_FOR_SUBMISSION) is True
    assert PaymentStateMachine.can_transition(PaymentState.READY_FOR_SUBMISSION, PaymentState.SUBMISSION_PENDING) is True
    assert PaymentStateMachine.can_transition(PaymentState.SUBMISSION_PENDING, PaymentState.SETTLED) is True
    
    # Terminal SETTLED cannot regress
    assert PaymentStateMachine.can_transition(PaymentState.SETTLED, PaymentState.UNKNOWN) is False
    assert PaymentStateMachine.can_transition(PaymentState.SETTLED, PaymentState.FAILED) is False
    assert PaymentStateMachine.can_transition(PaymentState.SETTLED, PaymentState.SUBMISSION_PENDING) is False
    
    with pytest.raises(Exception):
        PaymentStateMachine.validate_transition(PaymentState.SETTLED, PaymentState.UNKNOWN)


def test_rest_api_disburse_calls_banking_rail_and_returns_real_telemetry(test_app_client, monkeypatch):
    """
    DEF-02 FIX VERIFICATION: Assert that calling POST /api/v1/decisions/{id}/disburse
    now invokes RazorpayX stage_payout with deterministic idempotency key and records telemetry.
    """
    test_inv = f"INV-REST-DISBURSE-{uuid.uuid4().hex[:8]}"
    main.GLOBAL_DECISION_HISTORY = [{
        "invoice_number": test_inv,
        "vendor_id": "VEND-DISBURSE-TEST",
        "vendor_name": "Disburse Test Vendor",
        "status": "APPROVED_BY_CONTROLLER",
        "final_disbursed": 90000.0,
        "subtotal": 90000.0,
        "payout_telemetry": {}
    }]
    main.save_decision_history()

    staged_calls = []
    def mock_stage_payout(fund_account_id, amount_paise, idempotency_key, reference_id, narration, notes):
        staged_calls.append({
            "fund_account_id": fund_account_id,
            "amount_paise": amount_paise,
            "idempotency_key": idempotency_key,
            "reference_id": reference_id
        })
        return {
            "id": f"pout_{idempotency_key[:14]}",
            "status": "CONFIRMED",
            "utr": "RZX_REAL_BANK_UTR_999",
            "amount": amount_paise
        }

    monkeypatch.setattr(main.razorpay_client, "stage_payout", mock_stage_payout)

    resp = test_app_client.post(
        f"/api/v1/decisions/{test_inv}/disburse",
        headers={"X-User-Role": "ROLE_CONTROLLER", "X-Idempotency-Key": f"IDEM-TEST-REST-{uuid.uuid4().hex[:8]}"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    assert data["bank_utr"] == "RZX_REAL_BANK_UTR_999"
    # stage_payout was successfully executed
    assert len(staged_calls) == 1
    assert staged_calls[0]["amount_paise"] == 9000000
    assert staged_calls[0]["reference_id"] == f"INV-{test_inv}"
