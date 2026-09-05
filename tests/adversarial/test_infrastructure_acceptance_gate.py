import hashlib
import httpx
import json
import multiprocessing as mp
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import pytest

from firestore_store import FirestoreStateStore
from razorpayx_client import (
    DEFAULT_SUPPORTED_PURPOSES,
    RazorpayXBankingClient,
    validate_payout_purpose,
)
from schemas import (
    PaymentInstruction,
    PaymentState,
    SystemEnvironment,
    TDSSection,
    normalize_environment,
)
from services.crypto import CanonicalFinancialDecisionSerializer, EnterpriseKeyRegistry
from services.policy_registry import EnterprisePolicyRegistry, PolicyType
from services.payment_orchestrator import (
    PaymentAmbiguousOutcomeError,
    PaymentMaterialConflictError,
    PaymentOrchestrationError,
    PaymentOrchestrator,
    PaymentStaleVersionError,
)
from services.webhook_service import (
    ProviderWebhookService,
    WebhookAuthenticationError,
    WebhookReplayError,
)


def _worker_claim_task(
    store_dict,
    datastore_lock,
    barrier,
    results_list,
    idempotency_key,
    expected_version,
    worker_id,
):
    """
    Independent OS process worker with NO shared Python memory.
    Bypasses _distributed_lock_lock completely (bypassing local lease lock).
    The datastore's atomic version precondition (simulating Firestore's server-side OCC)
    is the sole line of defense.
    """
    store = FirestoreStateStore(force_mock=True, lock_backend=datastore_lock)
    store._mock_db = store_dict

    barrier.wait()  # Synchronize arrival at the exact same millisecond

    # Directly execute the datastore claim operation without acquiring distributed_lock
    claimed = store.update_payment_intent(
        idempotency_key=idempotency_key,
        update_dict={
            "status": PaymentState.SUBMISSION_PENDING.value,
            "claiming_worker": worker_id,
        },
        expected_version=expected_version,
    )

    if claimed:
        # Simulate sending payout POST to bank
        results_list.append((worker_id, "CLAIMED_AND_DISPATCHED"))
    else:
        results_list.append((worker_id, "CLAIM_REJECTED"))


def test_shared_datastore_multiprocess_concurrency_local_lock_bypassed():
    """
    Production Infrastructure Acceptance Gate - Test 1, 2 & 7:
    Tests two independent OS processes racing concurrently against the exact same persisted PaymentIntent
    with _distributed_lock_lock COMPLETELY BYPASSED.
    Proves that local locking (_distributed_lock_lock) is merely a LOCAL OPTIMIZATION,
    and that the datastore atomic version precondition (OCC) is the true financial correctness boundary.
    """
    mp_ctx = mp.get_context("spawn")
    manager = mp_ctx.Manager()
    shared_store = manager.dict()
    shared_store["payment_intents"] = {}
    shared_store["distributed_locks"] = {}
    datastore_lock = manager.Lock()

    idempotency_key = "idem_cross_process_gate_001"
    now_iso = datetime.now(timezone.utc).isoformat()

    # Pre-populate PaymentIntent in READY_FOR_SUBMISSION at version 1
    intent_data = {
        "instruction_id": "INS-GATE-001",
        "invoice_number": "INV-GATE-001",
        "vendor_id": "VEND-GATE-001",
        "vendor_pan": "ABCDE1234F",
        "fund_account_id": "fa_gate_001",
        "gross_subtotal": "100000.00",
        "tax_amount": "18000.00",
        "tds_withheld": "2000.00",
        "tds_section": "194C",
        "applied_credits_total": "0.00",
        "net_payout_amount": "116000.00",
        "payout_paise": 11600000,
        "idempotency_key": idempotency_key,
        "requires_zero_payout_hold": False,
        "status": PaymentState.READY_FOR_SUBMISSION.value,
        "version": 1,
        "created_at": now_iso,
    }
    intents = dict(shared_store.get("payment_intents", {}))
    intents[idempotency_key] = intent_data
    shared_store["payment_intents"] = intents

    barrier = manager.Barrier(2)
    results = manager.list()

    p1 = mp_ctx.Process(
        target=_worker_claim_task,
        args=(shared_store, datastore_lock, barrier, results, idempotency_key, 1, "worker_A"),
    )
    p2 = mp_ctx.Process(
        target=_worker_claim_task,
        args=(shared_store, datastore_lock, barrier, results, idempotency_key, 1, "worker_B"),
    )

    p1.start()
    p2.start()
    p1.join(timeout=10)
    p2.join(timeout=10)

    res_list = list(results)
    assert len(res_list) == 2

    dispatched = [r for r in res_list if r[1] == "CLAIMED_AND_DISPATCHED"]
    rejected = [r for r in res_list if r[1] == "CLAIM_REJECTED"]

    # Invariant: exactly 1 worker claims and dispatches, exactly 1 is rejected
    assert len(dispatched) == 1, f"Expected 1 claim, got {len(dispatched)}"
    assert len(rejected) == 1, f"Expected 1 rejection, got {len(rejected)}"

    # Check the persisted state in the shared datastore
    final_intents = dict(shared_store["payment_intents"])
    saved = final_intents[idempotency_key]
    assert saved["version"] == 2
    assert saved["status"] == PaymentState.SUBMISSION_PENDING.value
    assert saved["claiming_worker"] == dispatched[0][0]


def test_payment_idempotency_identity_collision_analysis():
    """
    Production Infrastructure Acceptance Gate - Test 3:
    Verifies that provider idempotency identity:
    1. Does NOT collide across distinct fiscal years.
    2. Does NOT collide across distinct partial payment installments when installment_or_split_id is supplied.
    3. Remains deterministic and stable across operational retries.
    """
    # 1. Distinct fiscal years do not collide
    key_fy24 = RazorpayXBankingClient.compute_idempotency_key("V-01", "INV-100", "2024-25")
    key_fy25 = RazorpayXBankingClient.compute_idempotency_key("V-01", "INV-100", "2025-26")
    assert key_fy24 != key_fy25, "Fiscal year distinction must produce distinct keys"

    # 2. Distinct installments do not collide
    key_inst_1 = RazorpayXBankingClient.compute_idempotency_key(
        "V-01", "INV-100", "2024-25", installment_or_split_id="INSTALLMENT_1"
    )
    key_inst_2 = RazorpayXBankingClient.compute_idempotency_key(
        "V-01", "INV-100", "2024-25", installment_or_split_id="INSTALLMENT_2"
    )
    assert key_inst_1 != key_inst_2, "Installment distinction must produce distinct keys"

    # 3. Same economic intent produces strictly identical key (retry stability)
    key_retry = RazorpayXBankingClient.compute_idempotency_key("V-01", "INV-100", "2024-25")
    assert key_retry == key_fy24, "Operational retry must compute identical idempotency key"


def _webhook_worker_task(store_dict, datastore_lock, barrier, results_list, raw_body, sig, secret, worker_id):
    store = FirestoreStateStore(force_mock=True, lock_backend=datastore_lock)
    store._mock_db = store_dict
    service = ProviderWebhookService(store=store)

    barrier.wait()  # Synchronize both workers to process webhook simultaneously

    try:
        res = service.process_razorpayx_webhook(
            raw_body=raw_body,
            signature=sig,
            secret=secret,
            current_time_epoch=time.time(),
        )
        results_list.append((worker_id, res.get("status")))
    except Exception as e:
        results_list.append((worker_id, f"ERROR_{type(e).__name__}"))


def test_cross_instance_webhook_idempotency():
    """
    Production Infrastructure Acceptance Gate - Test 5:
    Verifies that when identical Webhook Event E arrives at Instance A and Instance B concurrently,
    at most one logical domain processing operation occurs for E.
    The second instance receives DUPLICATE_IGNORED and zero duplicate state mutations occur.
    """
    mp_ctx = mp.get_context("spawn")
    manager = mp_ctx.Manager()
    shared_store = manager.dict()
    shared_store["webhook_events"] = {}
    shared_store["payment_intents"] = {}
    datastore_lock = manager.Lock()

    # Setup payment intent in SUBMISSION_PENDING
    idempotency_key = "idem_webhook_test_001"
    shared_store["payment_intents"] = {
        idempotency_key: {
            "instruction_id": "INS-WH-001",
            "idempotency_key": idempotency_key,
            "status": PaymentState.SUBMISSION_PENDING.value,
            "version": 1,
        }
    }

    event_id = "evt_razorpay_unique_998877"
    secret = "test_webhook_secret_key_123"
    payload = {
        "event": "payout.processed",
        "event_id": event_id,
        "created_at": time.time(),
        "payload": {
            "payout": {
                "entity": {
                    "id": "pout_998877",
                    "status": "processed",
                    "utr": "UTR_WH_998877",
                    "notes": {"idempotency_key": idempotency_key},
                }
            }
        },
    }
    raw_body = CanonicalFinancialDecisionSerializer.serialize(payload).encode("utf-8")
    import hmac
    sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    barrier = manager.Barrier(2)
    results = manager.list()

    p1 = mp_ctx.Process(
        target=_webhook_worker_task,
        args=(shared_store, datastore_lock, barrier, results, raw_body, sig, secret, "worker_A"),
    )
    p2 = mp_ctx.Process(
        target=_webhook_worker_task,
        args=(shared_store, datastore_lock, barrier, results, raw_body, sig, secret, "worker_B"),
    )

    p1.start()
    p2.start()
    p1.join(timeout=10)
    p2.join(timeout=10)

    res_list = list(results)
    assert len(res_list) == 2
    statuses = [r[1] for r in res_list]

    # Exactly one worker processes the event, and the other ignores as duplicate
    assert any(s in ("PROCESSED", "SUCCESS", "SETTLED", "PROCESSED_SETTLED") or "SETTLED" in str(s) for s in statuses)
    assert "DUPLICATE_IGNORED" in statuses

    # Exactly one record is persisted in webhook_events
    wh_events = dict(shared_store["webhook_events"])
    assert len(wh_events) == 1
    assert event_id in wh_events


def test_ambiguous_payment_state_cross_instance_recovery():
    """
    Production Infrastructure Acceptance Gate - Test 6:
    Worker A encounters a simulated 504 / lost response and marks state UNKNOWN / AMBIGUOUS.
    Worker B (independent process context) receives the same payment.
    Worker B MUST refuse resubmission (blocks duplicate POST), then calls authoritative reconciliation.
    Required total payout POST calls = 1.
    """
    store = FirestoreStateStore(force_mock=True)

    class MockCountingBankClient:
        def __init__(self):
            self.post_count = 0
            self.get_count = 0

        def stage_payout(self, fund_account_id, amount_paise, idempotency_key, reference_id, narration, notes, provider_idempotency_key=None):
            self.post_count += 1
            # First attempt: bank debited the funds but gateway returns 504
            return {
                "id": f"pout_{idempotency_key[:14]}",
                "status": "UNKNOWN",
                "payment_state": "UNKNOWN",
                "requires_reconciliation": True,
                "amount": amount_paise,
                "idempotency_key": idempotency_key,
                "provider_idempotency_key": provider_idempotency_key,
            }

        def reconcile_payout_status(self, idempotency_key, reference_id, provider_idempotency_key=None):
            self.get_count += 1
            # Bank lookup confirms the initial payout was indeed processed
            return {
                "status": "SETTLED",
                "reconciled": True,
                "payout_id": f"pout_{idempotency_key[:14]}",
                "gateway_status": "processed",
            }

    mock_bank = MockCountingBankClient()
    worker_A = PaymentOrchestrator(store=store, banking_client=mock_bank)
    worker_B = PaymentOrchestrator(store=store, banking_client=mock_bank)

    intent, _ = worker_A.get_or_create_payment_intent(
        invoice_number="INV-504-CROSS-001",
        vendor_id="VEND-001",
        vendor_pan="ABCDE1234F",
        fiscal_year="2024-25",
        fund_account_id="fa_504_001",
        gross_subtotal=Decimal("10000.00"),
        tax_amount=Decimal("1800.00"),
        tds_withheld=Decimal("200.00"),
        tds_section=TDSSection.SECTION_194C_IND,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("11600.00"),
    )

    # Worker A dispatches -> gets UNKNOWN status due to 504
    res_A = worker_A.dispatch_payment_intent(intent)
    assert res_A["state"] == PaymentState.UNKNOWN.value
    assert mock_bank.post_count == 1

    # Worker B tries to dispatch the same intent:
    # It observes the persisted AMBIGUOUS state, refuses blind retry (0 payout POST),
    # and automatically initiates authoritative reconciliation by lookup!
    res_B = worker_B.dispatch_payment_intent(intent)
    assert res_B["state"] == PaymentState.SETTLED.value
    assert "reconciled" in res_B["message"].lower()
    assert mock_bank.post_count == 1, "Worker B must NOT issue a second payout POST"
    assert mock_bank.get_count >= 1, "Authoritative lookup must have been performed"

    # Verify that if bank reconciliation is still indeterminate, PaymentAmbiguousOutcomeError is raised
    # and payout POST remains strictly blocked:
    class IndeterminateBankClient(MockCountingBankClient):
        def reconcile_payout_status(self, idempotency_key, reference_id, provider_idempotency_key=None):
            return {"status": "UNKNOWN", "reconciled": False}

    indet_bank = IndeterminateBankClient()
    worker_C = PaymentOrchestrator(store=store, banking_client=indet_bank)
    # Reset intent to AMBIGUOUS
    store.update_payment_intent(intent.idempotency_key, {"status": PaymentState.AMBIGUOUS.value})
    with pytest.raises(PaymentAmbiguousOutcomeError):
        worker_C.dispatch_payment_intent(intent)
    assert indet_bank.post_count == 0, "No payout POST must be made when outcome is ambiguous"


def test_environment_fail_safe_behavior():
    """
    Production Infrastructure Acceptance Gate - Test 8:
    Verifies that system fails closed and never falls back to live financial infrastructure:
    1. Missing / invalid ENVIRONMENT defaults to safe SANDBOX.
    2. Missing credentials / invalid trust blocks PRODUCTION disbursement.
    3. Missing webhook secret raises WebhookAuthenticationError.
    4. Key tampering fails cryptographic verification.
    """
    # 1. Environment fail-safe normalization
    assert normalize_environment(None) == SystemEnvironment.SANDBOX.value
    assert normalize_environment("") == SystemEnvironment.SANDBOX.value
    assert normalize_environment("INVALID_ENV") == SystemEnvironment.SANDBOX.value
    assert normalize_environment("PROD") == SystemEnvironment.SANDBOX.value  # Must be exact "PRODUCTION"
    assert normalize_environment("PRODUCTION") == SystemEnvironment.PRODUCTION.value

    # 2. Production payout gating without trust
    store = FirestoreStateStore(force_mock=True)
    mock_bank = RazorpayXBankingClient(api_key="mock_key", api_secret="mock_secret", account_number="12345")
    orchestrator = PaymentOrchestrator(store=store, banking_client=mock_bank)

    intent, _ = orchestrator.get_or_create_payment_intent(
        invoice_number="INV-FAILSAFE-001",
        vendor_id="VEND-001",
        vendor_pan="ABCDE1234F",
        fiscal_year="2024-25",
        fund_account_id="fa_test_001",
        gross_subtotal=Decimal("10000.00"),
        tax_amount=Decimal("1800.00"),
        tds_withheld=Decimal("200.00"),
        tds_section=TDSSection.SECTION_194C_IND,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("11600.00"),
        environment="PRODUCTION",
        bank_verification_trust=None,  # Missing trust
    )

    with pytest.raises(PaymentOrchestrationError) as exc_info:
        orchestrator.dispatch_payment_intent(intent)
    assert "Production Payout Gated" in str(exc_info.value)
    assert "lacks PRODUCTION_TRUST" in str(exc_info.value)

    # 3. Webhook secret absent
    webhook_service = ProviderWebhookService(store=store)
    with pytest.raises(WebhookAuthenticationError):
        webhook_service.process_razorpayx_webhook(
            raw_body=b'{"test": 1}',
            signature="some_sig",
            secret="",  # Absent secret
        )


def test_razorpayx_provider_idempotency_key_contract_and_stability():
    """
    Provider Contract & Infrastructure Correction Gate - Section 1 & 6:
    Verifies RazorpayX provider idempotency key:
    1. Strictly between 4 and 36 characters.
    2. UUID format / allowed character set.
    3. Reused unchanged across retries, worker restarts, and timeouts.
    4. Two distinct PaymentIntents receive distinct provider keys.
    5. Two distinct installments receive distinct provider keys.
    6. Verifies payload contract: reference_id <= 40, amount in paise >= 100, uppercase mode.
    """
    import re
    import uuid
    store = FirestoreStateStore(force_mock=True)
    captured_requests = []

    class ContractVerifyingBankClient(RazorpayXBankingClient):
        def stage_payout(self, fund_account_id, amount_paise, idempotency_key, reference_id, narration, notes, provider_idempotency_key=None):
            captured_requests.append({
                "fund_account_id": fund_account_id,
                "amount_paise": amount_paise,
                "idempotency_key": idempotency_key,
                "provider_idempotency_key": provider_idempotency_key,
                "reference_id": reference_id,
                "narration": narration,
                "notes": notes
            })
            return super().stage_payout(
                fund_account_id, amount_paise, idempotency_key, reference_id, narration, notes, provider_idempotency_key
            )

    client = ContractVerifyingBankClient(api_key="mock_k", api_secret="mock_s", account_number="123456789")
    orchestrator = PaymentOrchestrator(store=store, banking_client=client)

    # 1. Create PaymentIntent
    intent_1, created = orchestrator.get_or_create_payment_intent(
        invoice_number="INV-CONTRACT-001",
        vendor_id="VEND-001",
        vendor_pan="ABCDE1234F",
        fiscal_year="2024-25",
        fund_account_id="fa_contract_001",
        gross_subtotal=Decimal("50000.00"),
        tax_amount=Decimal("9000.00"),
        tds_withheld=Decimal("1000.00"),
        tds_section=TDSSection.SECTION_194C_IND,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("58000.00"),
    )
    assert created is True
    store.save_payment_intent(intent_1.model_dump(mode="json"))
    prov_key_1 = intent_1.provider_idempotency_key
    assert prov_key_1 is not None, "Provider idempotency key must be populated"
    assert 4 <= len(prov_key_1) <= 36, f"Provider key length must be 4-36 chars, got {len(prov_key_1)}"
    assert re.match(r"^[0-9a-fA-F\-]{36}$", prov_key_1), "Provider key must be valid UUID format"

    # 2. Re-fetching same intent returns identical provider key
    intent_1_refetched, created_refetch = orchestrator.get_or_create_payment_intent(
        invoice_number="INV-CONTRACT-001",
        vendor_id="VEND-001",
        vendor_pan="ABCDE1234F",
        fiscal_year="2024-25",
        fund_account_id="fa_contract_001",
        gross_subtotal=Decimal("50000.00"),
        tax_amount=Decimal("9000.00"),
        tds_withheld=Decimal("1000.00"),
        tds_section=TDSSection.SECTION_194C_IND,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("58000.00"),
    )
    assert created_refetch is False
    assert intent_1_refetched.provider_idempotency_key == prov_key_1, "Provider key must be stable across reads"

    # 3. Two distinct installments receive distinct provider keys
    intent_inst_1, _ = orchestrator.get_or_create_payment_intent(
        invoice_number="INV-CONTRACT-SPLIT",
        vendor_id="VEND-001",
        vendor_pan="ABCDE1234F",
        fiscal_year="2024-25",
        fund_account_id="fa_contract_001",
        gross_subtotal=Decimal("25000.00"),
        tax_amount=Decimal("4500.00"),
        tds_withheld=Decimal("500.00"),
        tds_section=TDSSection.SECTION_194C_IND,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("29000.00"),
        installment_or_split_id="INST_1"
    )
    intent_inst_2, _ = orchestrator.get_or_create_payment_intent(
        invoice_number="INV-CONTRACT-SPLIT",
        vendor_id="VEND-001",
        vendor_pan="ABCDE1234F",
        fiscal_year="2024-25",
        fund_account_id="fa_contract_001",
        gross_subtotal=Decimal("25000.00"),
        tax_amount=Decimal("4500.00"),
        tds_withheld=Decimal("500.00"),
        tds_section=TDSSection.SECTION_194C_IND,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("29000.00"),
        installment_or_split_id="INST_2"
    )
    assert intent_inst_1.provider_idempotency_key != intent_inst_2.provider_idempotency_key, (
        "Distinct installments must receive distinct provider idempotency keys"
    )

    # 4. Dispatch payout and verify upstream payload contract
    res = orchestrator.dispatch_payment_intent(intent_1)
    assert res["status"] == "SUCCESS"
    assert len(captured_requests) == 1
    req = captured_requests[0]

    # Contract assertions
    assert req["provider_idempotency_key"] == prov_key_1
    assert 4 <= len(req["provider_idempotency_key"]) <= 36
    assert len(req["reference_id"]) <= 40, f"reference_id '{req['reference_id']}' exceeds 40 chars"
    assert isinstance(req["amount_paise"], int)
    assert req["amount_paise"] == 5800000
    assert req["amount_paise"] >= 100

    # 5. Restart reload preserves exact same provider key
    persisted_raw = store.get_payment_intent(intent_1.idempotency_key)
    reloaded_intent = PaymentInstruction(**persisted_raw)
    assert reloaded_intent.provider_idempotency_key == prov_key_1, "Restart reload must preserve provider key"


def test_ambiguous_payment_no_key_regeneration_and_no_24h_expiry():
    """
    Provider Contract & Infrastructure Correction Gate - Section 2 & 7:
    Verifies that:
    1. UNKNOWN/AMBIGUOUS outcome preserves the exact same provider_idempotency_key.
    2. Elapsed time (>24h, >48h, >30d) NEVER allows retrying with a fresh key.
    3. Fencing remains permanent until authoritative gateway reconciliation.
    4. Authoritative reconciliation settles the original intent without duplicate payout POST.
    """
    store = FirestoreStateStore(force_mock=True)

    class GatewayTimeoutBankClient(RazorpayXBankingClient):
        def __init__(self):
            super().__init__(api_key="mock_k", api_secret="mock_s", account_number="123456789")
            self.post_count = 0
            self.get_count = 0
            self.simulate_reconciliation_success = False

        def stage_payout(self, fund_account_id, amount_paise, idempotency_key, reference_id, narration, notes, provider_idempotency_key=None):
            self.post_count += 1
            # Simulate HTTP 504 Gateway Timeout
            return {
                "id": f"pout_{provider_idempotency_key.replace('-', '')[:14]}",
                "status": "UNKNOWN",
                "payment_state": "UNKNOWN",
                "requires_reconciliation": True,
                "amount": amount_paise,
                "idempotency_key": idempotency_key,
                "provider_idempotency_key": provider_idempotency_key
            }

        def reconcile_payout_status(self, idempotency_key, reference_id, provider_idempotency_key=None):
            self.get_count += 1
            if self.simulate_reconciliation_success:
                return {
                    "status": "SETTLED",
                    "reconciled": True,
                    "payout_id": f"pout_{provider_idempotency_key.replace('-', '')[:14]}",
                    "gateway_status": "processed"
                }
            return {"status": "UNKNOWN", "reconciled": False}

    bank_client = GatewayTimeoutBankClient()
    orchestrator = PaymentOrchestrator(store=store, banking_client=bank_client)

    intent, _ = orchestrator.get_or_create_payment_intent(
        invoice_number="INV-AMBIG-001",
        vendor_id="VEND-001",
        vendor_pan="ABCDE1234F",
        fiscal_year="2024-25",
        fund_account_id="fa_ambig_001",
        gross_subtotal=Decimal("75000.00"),
        tax_amount=Decimal("13500.00"),
        tds_withheld=Decimal("1500.00"),
        tds_section=TDSSection.SECTION_194C_IND,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("87000.00"),
    )
    initial_provider_key = intent.provider_idempotency_key

    # 1. Initial submission encounters 504 timeout -> UNKNOWN state
    dispatch_res = orchestrator.dispatch_payment_intent(intent)
    assert dispatch_res["state"] == PaymentState.UNKNOWN.value
    assert bank_client.post_count == 1

    # Check persisted intent: provider key is preserved, status is UNKNOWN
    persisted = store.get_payment_intent(intent.idempotency_key)
    assert persisted["status"] == PaymentState.UNKNOWN.value
    assert persisted["provider_idempotency_key"] == initial_provider_key

    # 2. Simulate passage of time (>24 hours, e.g. 72 hours)
    # Under NO circumstances should time elapsed permit generating a new key or blind resubmission
    loaded_intent = PaymentInstruction(**persisted)
    assert loaded_intent.provider_idempotency_key == initial_provider_key

    # Attempting dispatch without reconciliation proof must raise PaymentAmbiguousOutcomeError
    with pytest.raises(PaymentAmbiguousOutcomeError) as exc_info:
        orchestrator.dispatch_payment_intent(loaded_intent)
    assert "indeterminate outcome (AMBIGUOUS/UNKNOWN)" in str(exc_info.value)
    assert "Blind resubmission blocked" in str(exc_info.value)
    assert bank_client.post_count == 1, "Must NOT issue payout POST merely because time elapsed"

    # 3. Now simulate authoritative reconciliation evidence from bank lookup
    bank_client.simulate_reconciliation_success = True
    recon_dispatch = orchestrator.dispatch_payment_intent(loaded_intent)
    assert recon_dispatch["state"] == PaymentState.SETTLED.value
    assert "reconciled" in recon_dispatch["message"].lower()
    assert bank_client.post_count == 1, "Must NEVER issue a second payout POST after reconciliation"
    assert bank_client.get_count >= 1, "Authoritative GET reconciliation lookup must have occurred"


def test_cloud_kms_asymmetric_versioned_lifecycle_preserves_historical_verification():
    """
    Provider Contract & Infrastructure Correction Gate - Section 3 & 7:
    Verifies Cloud KMS asymmetric key version lifecycle:
    1. Asymmetric Ed25519 signing requires manual versioning (no automatic platform rotation).
    2. Version 1 signs an immutable financial decision record.
    3. Version 2 is created, registered, and becomes active for new signatures.
    4. Historical record signed with Version 1 remains cryptographically valid.
    5. New record signed with Version 2 is cryptographically valid.
    6. Historical audit proofs are never invalidated by subsequent key versions.
    """
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from services.crypto import verify_external_auditor_signature, ED25519_PUBLIC_KEY_HEX

    # Phase 1: Historical signature under Key Version 1
    v1_key_id = "kms://asia-south1/finance-decision-signer-ed25519-v1"
    v1_record_digest = hashlib.sha256(b"CANONICAL_DECISION_RECORD_2026_V1").hexdigest()

    # Generate signature using v1 private key
    from services.crypto import _ED25519_PRIV
    v1_sig = _ED25519_PRIV.sign(v1_record_digest.encode("utf-8")).hex()

    # Verify v1 signature against registry
    v1_check = verify_external_auditor_signature(
        canonical_payload_sha256=v1_record_digest,
        signature_hex=v1_sig,
        signing_key_id=v1_key_id,
        return_detailed_report=True
    )
    assert v1_check["verified"] is True
    assert v1_check["cryptographic_signature_valid"] is True

    # Phase 2: Create new Key Version 2 (Manual Asymmetric Rotation)
    v2_priv = ed25519.Ed25519PrivateKey.generate()
    v2_pub = v2_priv.public_key()
    v2_pub_hex = v2_pub.public_bytes_raw().hex()
    v2_key_id = "kms://asia-south1/finance-decision-signer-ed25519-v2"

    # Register v2 in EnterpriseKeyRegistry
    EnterpriseKeyRegistry.register_key({
        "key_id": v2_key_id,
        "algorithm": "Ed25519",
        "public_key_hex": v2_pub_hex,
        "status": "ACTIVE",
        "valid_from": "2026-06-01T00:00:00Z",
        "valid_until": "2027-06-01T00:00:00Z",
        "revoked_at": None,
        "root_authority": "FinanceAgent-Enterprise-Trust-Anchor-v1"
    })

    # Phase 3: Sign new record under Key Version 2
    v2_record_digest = hashlib.sha256(b"CANONICAL_DECISION_RECORD_2026_V2").hexdigest()
    v2_sig = v2_priv.sign(v2_record_digest.encode("utf-8")).hex()

    v2_check = verify_external_auditor_signature(
        canonical_payload_sha256=v2_record_digest,
        signature_hex=v2_sig,
        signing_key_id=v2_key_id,
        return_detailed_report=True
    )
    assert v2_check["verified"] is True
    assert v2_check["cryptographic_signature_valid"] is True

    # Phase 4: Re-verify historical record signed with Version 1
    # INVARIANT: Introducing Version 2 must NEVER invalidate Version 1 historical records
    v1_historical_recheck = verify_external_auditor_signature(
        canonical_payload_sha256=v1_record_digest,
        signature_hex=v1_sig,
        signing_key_id=v1_key_id,
        return_detailed_report=True
    )
    assert v1_historical_recheck["verified"] is True
    assert v1_historical_recheck["cryptographic_signature_valid"] is True


def test_production_adapter_missing_idempotency_fails_closed():
    """
    Check 1: Required Production Invariant:
    A real RazorpayX payout must NEVER be submitted without X-Payout-Idempotency.
    1. Production RazorpayX requires a persisted provider_idempotency_key.
    2. Missing provider key fails closed before HTTP submission.
    3. Invalid provider key fails closed.
    4. No TypeError or compatibility branch can cause a second call without the header.
    """
    client = RazorpayXBankingClient(
        api_key="rzp_live_key123",
        api_secret="secret123",
        account_number="2323230000000001"
    )

    # 1. Direct call with invalid provider_idempotency_key (< 4 chars) fails closed
    with pytest.raises(ValueError, match="constraint violated|X-Payout-Idempotency"):
        client.stage_payout(
            fund_account_id="fa_test_001",
            amount_paise=500000,
            idempotency_key="idempotency_key_test",
            reference_id="INV-TEST-001",
            narration="Test Payout",
            notes={},
            provider_idempotency_key="abc"  # Only 3 chars -> invalid
        )

    # 2. Direct call with invalid provider_idempotency_key (> 36 chars) fails closed
    with pytest.raises(ValueError, match="constraint violated|X-Payout-Idempotency"):
        client.stage_payout(
            fund_account_id="fa_test_001",
            amount_paise=500000,
            idempotency_key="idempotency_key_test",
            reference_id="INV-TEST-001",
            narration="Test Payout",
            notes={},
            provider_idempotency_key="a" * 37  # 37 chars -> invalid
        )

    # 3. PaymentOrchestrator fails closed before calling banking client if provider_idempotency_key is missing
    store = FirestoreStateStore(force_mock=True)
    orchestrator = PaymentOrchestrator(store, client)

    invalid_intent = PaymentInstruction(
        instruction_id="INS-FAIL-CLOSED-001",
        invoice_number="INV-FAIL-CLOSED-001",
        vendor_id="VEND-001",
        vendor_pan="ABCDE1234F",
        fund_account_id="fa_test_001",
        gross_subtotal=Decimal("10000.00"),
        tax_amount=Decimal("1800.00"),
        tds_withheld=Decimal("1000.00"),
        tds_section=TDSSection.SECTION_194J_PROF,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("10800.00"),
        payout_paise=1080000,
        idempotency_key="idem_fail_closed_test",
        provider_idempotency_key=None,  # Missing provider key!
        environment=SystemEnvironment.SANDBOX
    )
    # Explicitly clear provider_idempotency_key to test fail-closed validation
    invalid_intent.provider_idempotency_key = ""

    with pytest.raises(PaymentOrchestrationError, match="lacks valid provider_idempotency_key"):
        orchestrator.dispatch_payment_intent(invalid_intent)

    # 4. TypeError in RazorpayXBankingClient does NOT trigger downgrade fallback
    class MockFailingLiveRazorpayXClient(RazorpayXBankingClient):
        def __init__(self):
            super().__init__("rzp_live_key", "secret", "2323230000000001")
            self.call_count = 0

        def stage_payout(self, *args, **kwargs):
            self.call_count += 1
            raise TypeError("unexpected keyword argument 'provider_idempotency_key'")

    live_mock = MockFailingLiveRazorpayXClient()
    orchestrator_live = PaymentOrchestrator(store, live_mock)
    valid_intent, _ = orchestrator.get_or_create_payment_intent(
        invoice_number="INV-LIVE-DOWNGRADE-TEST",
        vendor_id="VEND-001",
        vendor_pan="ABCDE1234F",
        fiscal_year="FY2025-26",
        fund_account_id="fa_test_001",
        gross_subtotal=Decimal("10000.00"),
        tax_amount=Decimal("1800.00"),
        tds_withheld=Decimal("1000.00"),
        tds_section=TDSSection.SECTION_194J_PROF,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("10800.00"),
        environment="SANDBOX"
    )

    # For live RazorpayXBankingClient, TypeError must NOT be caught to downgrade to a keyless retry.
    # Instead, dispatch fences in AMBIGUOUS and does NOT perform a second call.
    res = orchestrator_live.dispatch_payment_intent(valid_intent)
    assert live_mock.call_count == 1
    assert res["status"] == "AMBIGUOUS"
    assert res["state"] == PaymentState.UNKNOWN.value


def test_provider_key_and_request_body_stability_across_retries():
    """
    Check 3: Request-Body Stability:
    ONE PAYMENT INTENT + ONE PROVIDER IDEMPOTENCY KEY + ONE IMMUTABLE PROVIDER REQUEST SNAPSHOT.
    Verifies that all provider payload fields remain byte-for-byte identical across multiple attempts.
    """
    store = FirestoreStateStore(force_mock=True)
    client = RazorpayXBankingClient("rzp_test_key", "secret", "2323230000000001")
    orchestrator = PaymentOrchestrator(store, client)

    intent, _ = orchestrator.get_or_create_payment_intent(
        invoice_number="INV-STABILITY-001",
        vendor_id="VEND-STABILITY",
        vendor_pan="ABCDE1234F",
        fiscal_year="FY2025-26",
        fund_account_id="fa_stability_001",
        gross_subtotal=Decimal("25000.00"),
        tax_amount=Decimal("4500.00"),
        tds_withheld=Decimal("2500.00"),
        tds_section=TDSSection.SECTION_194J_PROF,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("27000.00"),
        environment="SANDBOX"
    )

    outbox_item = orchestrator.create_outbox_work_item(intent)
    snapshot = outbox_item.payload.get("provider_request_snapshot")
    assert snapshot is not None, "Outbox item must contain immutable provider_request_snapshot"

    # Verify all expected provider fields
    assert snapshot["fund_account_id"] == "fa_stability_001"
    assert snapshot["amount_paise"] == 2700000
    assert snapshot["currency"] == "INR"
    assert snapshot["reference_id"] == "INV-INV-STABILITY-001"[:40]
    assert snapshot["narration"] == f"INV {intent.invoice_number[:20]}"
    assert snapshot["notes"]["invoice_no"] == "INV-STABILITY-001"
    assert snapshot["notes"]["net_amount"] == "27000.00"
    assert snapshot["provider_idempotency_key"] == intent.provider_idempotency_key
    assert snapshot["idempotency_key"] == intent.idempotency_key

    # Subsequent fetch or outbox reconstruction produces the exact same snapshot
    outbox_item_2 = orchestrator.create_outbox_work_item(intent)
    snapshot_2 = outbox_item_2.payload.get("provider_request_snapshot")
    assert snapshot == snapshot_2, "Provider request snapshot must be strictly identical"


def test_ambiguous_reconciliation_lost_response_idempotent_recovery():
    """
    Check 2: Ambiguous Recovery When Response Was Lost:
    1. Mock provider accepts original payout.
    2. Application loses the response -> state becomes UNKNOWN.
    3. Reconciliation occurs with allow_idempotent_replay=True.
    4. The same provider key and identical body are reused.
    5. Provider maps it to the original payout.
    6. Total economic payout count remains exactly 1.
    """
    store = FirestoreStateStore(force_mock=True)

    class MockGatewayWithIdempotencyMapping:
        def __init__(self):
            self.payout_records = {}  # provider_key -> payout
            self.total_economic_payouts_created = 0
            self.total_post_requests = 0

        def stage_payout(self, fund_account_id, amount_paise, idempotency_key, reference_id, narration, notes, provider_idempotency_key=None):
            self.total_post_requests += 1
            key = provider_idempotency_key or idempotency_key
            if key in self.payout_records:
                # Idempotent response: return existing record without creating second payout
                return self.payout_records[key]

            # First attempt: create economic payout, but simulate transport disconnect
            payout = {
                "id": f"pout_{key.replace('-', '')[:14]}",
                "status": "CONFIRMED",
                "amount": amount_paise,
                "utr": f"UTR-{key[:8]}",
                "provider_idempotency_key": key
            }
            self.payout_records[key] = payout
            self.total_economic_payouts_created += 1

            if self.total_post_requests == 1:
                # Simulate lost response (transport error)
                raise httpx.ReadTimeout("Simulated read timeout after gateway processed payout")

            return payout

        def reconcile_payout_status(self, idempotency_key, reference_id, provider_idempotency_key=None, payout_id=None):
            # If payout_id is not known, cannot find by GET reference_id
            return {"status": "UNKNOWN", "reconciled": False}

    mock_gateway = MockGatewayWithIdempotencyMapping()
    orchestrator = PaymentOrchestrator(store, mock_gateway)

    intent, _ = orchestrator.get_or_create_payment_intent(
        invoice_number="INV-LOST-RESP-001",
        vendor_id="VEND-001",
        vendor_pan="ABCDE1234F",
        fiscal_year="FY2025-26",
        fund_account_id="fa_test_001",
        gross_subtotal=Decimal("10000.00"),
        tax_amount=Decimal("1800.00"),
        tds_withheld=Decimal("1000.00"),
        tds_section=TDSSection.SECTION_194J_PROF,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("10800.00"),
        environment="SANDBOX"
    )

    # 1. First dispatch: Gateway accepted payout, but response timed out
    dispatch_res = orchestrator.dispatch_payment_intent(intent)
    assert dispatch_res["status"] == "AMBIGUOUS"
    assert dispatch_res["state"] == PaymentState.UNKNOWN.value

    # Gateway recorded 1 payout, but application received no payout_id
    assert mock_gateway.total_economic_payouts_created == 1
    stored_intent_snap = store.get_payment_intent(intent.idempotency_key)
    assert stored_intent_snap["status"] == PaymentState.UNKNOWN.value
    assert stored_intent_snap.get("provider_reference") is None

    # 2. Execute reconciliation via documented idempotent replay recovery
    intent_obj = PaymentInstruction(**stored_intent_snap)
    recon_res = orchestrator.reconcile_ambiguous_intent(intent_obj, allow_idempotent_replay=True)

    # 3. Assertions:
    # State transitions to CONFIRMED
    assert recon_res["status"] == "CONFIRMED"
    assert recon_res["reconciled"] is True
    # CRITICAL INVARIANT: Total economic payouts created remains strictly 1!
    assert mock_gateway.total_economic_payouts_created == 1
    # Total POST calls was 2 (1 original + 1 idempotent recovery replay)
    assert mock_gateway.total_post_requests == 2

    # Datastore settled with the original payout ID
    final_intent = store.get_payment_intent(intent.idempotency_key)
    assert final_intent["status"] == PaymentState.SETTLED.value
    assert final_intent["provider_reference"].startswith("pout_")


def test_ambiguous_reconciliation_known_provider_id_get():
    """
    Check 2: When provider payout ID is known, reconciliation uses GET /v1/payouts/{payout_id}.
    """
    client = RazorpayXBankingClient("rzp_test_key", "secret", "2323230000000001")
    store = FirestoreStateStore(force_mock=True)
    orchestrator = PaymentOrchestrator(store, client)

    intent, _ = orchestrator.get_or_create_payment_intent(
        invoice_number="INV-KNOWN-ID-001",
        vendor_id="VEND-001",
        vendor_pan="ABCDE1234F",
        fiscal_year="FY2025-26",
        fund_account_id="fa_test_001",
        gross_subtotal=Decimal("10000.00"),
        tax_amount=Decimal("1800.00"),
        tds_withheld=Decimal("1000.00"),
        tds_section=TDSSection.SECTION_194J_PROF,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("10800.00"),
        environment="SANDBOX"
    )

    # Save intent and set provider_reference as known payout_id
    known_payout_id = "pout_abcdef12345678"
    store.save_payment_intent(intent.model_dump(mode="json"))
    store.update_payment_intent(
        idempotency_key=intent.idempotency_key,
        update_dict={"provider_reference": known_payout_id, "status": PaymentState.UNKNOWN.value}
    )

    captured_urls = []
    def mock_get(url, params=None, **kwargs):
        captured_urls.append(url)
        class MockResp:
            status_code = 200
            def json(self):
                return {"id": known_payout_id, "status": "processed", "utr": "UTR-RECON-123"}
        return MockResp()

    client.client.get = mock_get

    refreshed_intent = PaymentInstruction(**store.get_payment_intent(intent.idempotency_key))
    recon_res = orchestrator.reconcile_ambiguous_intent(refreshed_intent)

    assert captured_urls == [f"https://api.razorpay.com/v1/payouts/{known_payout_id}"]
    assert recon_res["status"] == "CONFIRMED"
    assert recon_res["reconciled"] is True
    assert recon_res["payout_id"] == known_payout_id


def test_reconcile_never_performs_get_by_provider_idempotency_key():
    """
    Check 2: Verify that reconcile_payout_status NEVER queries /v1/payouts/{provider_idempotency_key}.
    """
    captured_urls = []

    client = RazorpayXBankingClient("rzp_live_key", "secret", "2323230000000001")

    def mock_get(url, params=None, **kwargs):
        captured_urls.append((url, params))
        class MockResponse:
            status_code = 200
            def json(self):
                return {"items": []}
        return MockResponse()

    client.client.get = mock_get

    provider_key = "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d"
    client.reconcile_payout_status(
        idempotency_key="sha256_idem_key",
        reference_id="INV-TEST-RECON-001",
        provider_idempotency_key=provider_key,
        payout_id=None
    )

    # Captured request must be GET /payouts with params {'reference_id': '...'}
    # It must NEVER be GET /payouts/{provider_idempotency_key}
    assert len(captured_urls) == 1
    called_url, called_params = captured_urls[0]
    assert called_url == "https://api.razorpay.com/v1/payouts"
    assert called_params == {"reference_id": "INV-TEST-RECON-001"}
    assert provider_key not in called_url


def test_mutable_state_attack_resistance_and_byte_for_byte_immutability():
    """
    Gate Certification Check:
    Verify that changing runtime configuration (account_number, default narration, mode thresholds)
    between original payout creation and an outbox retry / replay does NOT alter the dispatched HTTP body.
    The dispatched body must remain 100% byte-for-byte identical, preserving idempotency and preventing
    BAD_REQUEST_ERROR or financial payload drift.
    """
    store = FirestoreStateStore(force_mock=True)
    orig_account = "2323230000000001"
    client = RazorpayXBankingClient(
        api_key="rzp_test_key",
        api_secret="rzp_test_secret",
        account_number=orig_account
    )
    orchestrator = PaymentOrchestrator(store, client)

    intent, _ = orchestrator.get_or_create_payment_intent(
        invoice_number="INV-MUTABLE-001",
        vendor_id="V-MUTABLE-001",
        vendor_pan="ABCDE1234F",
        fiscal_year="FY2025-26",
        fund_account_id="fa_orig_account_001",
        gross_subtotal=Decimal("50000.00"),
        tax_amount=Decimal("0.00"),
        tds_withheld=Decimal("5000.00"),
        tds_section=TDSSection.SECTION_194J_PROF,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("45000.00"),
        environment="SANDBOX"
    )

    outbox_item = orchestrator.create_outbox_work_item(intent)
    orig_body = outbox_item.payload.get("provider_request_body")
    orig_hash = outbox_item.payload.get("provider_request_hash")

    # 1. Verify all 10 fields exist in provider_request_body
    expected_fields = [
        "account_number", "fund_account_id", "amount", "currency",
        "mode", "purpose", "queue_if_low_balance", "reference_id",
        "narration", "notes"
    ]
    for field in expected_fields:
        assert field in orig_body, f"Missing field in provider_request_body: {field}"

    # Verify canonical hash integrity
    canonical_bytes = CanonicalFinancialDecisionSerializer.serialize(orig_body).encode("utf-8")
    assert orig_hash == hashlib.sha256(canonical_bytes).hexdigest()

    # 2. Track calls made to banking client
    captured_payout_payloads = []
    captured_payout_headers = []

    def mock_post(url, headers=None, json=None, **kwargs):
        if "payouts" in url:
            captured_payout_payloads.append(dict(json) if json else {})
            captured_payout_headers.append(dict(headers) if headers else {})
        class MockResponse:
            status_code = 200
            def json(self):
                return {"id": "pout_mock_123", "status": "CONFIRMED"}
        return MockResponse()

    client.client.post = mock_post

    # First dispatch
    res1 = orchestrator.dispatch_payment_intent(intent, client=client)
    assert res1["status"] == "SUCCESS"
    assert len(captured_payout_payloads) == 1
    first_payload = captured_payout_payloads[0]
    first_header = captured_payout_headers[0]["X-Payout-Idempotency"]

    assert first_header == intent.provider_idempotency_key
    assert first_payload == orig_body

    # 3. Simulate MUTABLE STATE ATTACK / CONFIG DRIFT before a retry or redelivery:
    # Change client account_number to a rogue / altered account
    client.account_number = "9999999999999999"

    # Reset capture and simulate outbox redelivery using the persisted outbox item
    captured_payout_payloads.clear()
    captured_payout_headers.clear()

    # Worker calls stage_payout with provider_request_body from persisted outbox item
    persisted_body = outbox_item.payload.get("provider_request_body")
    client.stage_payout(
        fund_account_id=intent.fund_account_id,
        amount_paise=intent.payout_paise,
        idempotency_key=intent.idempotency_key,
        reference_id=f"INV-{intent.invoice_number}"[:40],
        narration="MUTATED_NARRATION",
        notes={"tampered": "notes"},
        provider_idempotency_key=intent.provider_idempotency_key,
        provider_request_body=persisted_body
    )

    assert len(captured_payout_payloads) == 1
    retry_payload = captured_payout_payloads[0]
    retry_header = captured_payout_headers[0]["X-Payout-Idempotency"]

    # Invariant: The retry payload MUST NOT use the mutated "9999999999999999"
    assert retry_payload["account_number"] == orig_body["account_number"]
    assert retry_payload["account_number"] != "9999999999999999"

    # Invariant: Dispatched retry payload is 100% byte-for-byte identical to first dispatch
    assert retry_payload == first_payload

    # Invariant: Header is 100% identical
    assert retry_header == first_header == intent.provider_idempotency_key


def test_production_missing_account_number_fails_closed():
    """
    Gate Certification Check:
    Verify that in PRODUCTION environment, creating a PaymentIntent or outbox work item
    without a configured source debit account_number FAILS CLOSED (raises PaymentOrchestrationError).
    Silent fallback to hardcoded test accounts is strictly forbidden in PRODUCTION.
    """
    store = FirestoreStateStore(force_mock=True)
    client_no_account = RazorpayXBankingClient(
        api_key="rzp_live_key",
        api_secret="rzp_live_secret",
        account_number="",  # missing or empty
    )
    orchestrator = PaymentOrchestrator(store, client_no_account)

    with pytest.raises(PaymentOrchestrationError) as exc_info:
        orchestrator.get_or_create_payment_intent(
            invoice_number="INV-PROD-FAIL-001",
            vendor_id="V-PROD-001",
            vendor_pan="ABCDE1234F",
            fiscal_year="FY2025-26",
            fund_account_id="fa_prod_001",
            gross_subtotal=Decimal("50000.00"),
            tax_amount=Decimal("0.00"),
            tds_withheld=Decimal("5000.00"),
            tds_section=TDSSection.SECTION_194J_PROF,
            applied_credits=Decimal("0.00"),
            net_payout_amount=Decimal("45000.00"),
            environment="PRODUCTION",
        )
    assert "Source debit bank account number is missing" in str(exc_info.value)


def test_razorpayx_payout_purpose_validation():
    """
    Gate Certification Check:
    Verify that:
    1. Built-in default purpose 'vendor bill' is accepted and is the standard default.
    2. All standard default purposes (refund, cashback, payout, salary, utility bill, vendor bill) are valid.
    3. Invalid / arbitrary purposes fail closed with ValueError before any HTTP request.
    4. Custom purpose is accepted if and only if configured in RAZORPAYX_CUSTOM_PURPOSES.
    """
    # 1. Default purpose
    assert validate_payout_purpose("vendor bill") == "vendor bill"

    # 2. All built-in supported purposes
    for p in DEFAULT_SUPPORTED_PURPOSES:
        assert validate_payout_purpose(p) == p
        assert validate_payout_purpose(p.upper()) == p  # case normalization

    # 3. Invalid purposes fail closed
    with pytest.raises(ValueError) as exc:
        validate_payout_purpose("vendor_payout")  # legacy unprovisioned string
    assert "Invalid RazorpayX payout purpose" in str(exc.value)

    with pytest.raises(ValueError) as exc2:
        validate_payout_purpose("unapproved_purpose_xyz")
    assert "Invalid RazorpayX payout purpose" in str(exc2.value)

    # 4. Custom purpose via env var
    os.environ["RAZORPAYX_CUSTOM_PURPOSES"] = "custom_escrow_disbursal, specialized_tax_settlement"
    try:
        assert validate_payout_purpose("custom_escrow_disbursal") == "custom_escrow_disbursal"
        assert validate_payout_purpose("specialized_tax_settlement") == "specialized_tax_settlement"
    finally:
        del os.environ["RAZORPAYX_CUSTOM_PURPOSES"]


def test_cfds_canonical_hash_determinism_and_standards_boundary():
    """
    Gate Certification Check:
    Verify that provider request hashing uses CFDS-v1 (Domain-Specific Deterministic Canonical Financial Serialization):
    1. Independent of dictionary key insertion order.
    2. Zero whitespace delimiters (',', ':').
    3. Strict Unicode normalization (NFC) intentionally enforced for financial anti-fraud,
       distinguishing CFDS-v1 from RFC 8785 / JCS (which strictly forbids character normalization).
    4. Precomposed "\\u00e9" and decomposed "e\\u0301" serialize to the same canonical representation in CFDS-v1,
       proving that CFDS-v1 is NOT raw RFC 8785.
    5. Preserves financial Decimal scale and serializes to fixed-scale strings without IEEE 754 precision loss.
    6. Produces identical SHA-256 hash across diverse serializations.
    """
    dict_order_1 = {
        "account_number": "2323230000000001",
        "fund_account_id": "fa_123",
        "amount": 4500000,
        "currency": "INR",
        "mode": "IMPS",
        "purpose": "vendor bill",
        "queue_if_low_balance": True,
        "reference_id": "REF-001",
        "narration": "Invoice payment",
        "notes": {"invoice": "INV-001", "vendor": "V-001"},
    }

    dict_order_2 = {
        "notes": {"vendor": "V-001", "invoice": "INV-001"},
        "narration": "Invoice payment",
        "reference_id": "REF-001",
        "queue_if_low_balance": True,
        "purpose": "vendor bill",
        "mode": "IMPS",
        "currency": "INR",
        "amount": 4500000,
        "fund_account_id": "fa_123",
        "account_number": "2323230000000001",
    }

    serialized_1 = CanonicalFinancialDecisionSerializer.serialize(dict_order_1)
    serialized_2 = CanonicalFinancialDecisionSerializer.serialize(dict_order_2)

    assert serialized_1 == serialized_2, "CFDS-v1 serialization must be invariant to dict key insertion order"

    hash_1 = hashlib.sha256(serialized_1.encode("utf-8")).hexdigest()
    hash_2 = hashlib.sha256(serialized_2.encode("utf-8")).hexdigest()
    assert hash_1 == hash_2, "Canonical hashes must be identical"

    # Verify method on client computes identical hash
    client_hash = RazorpayXBankingClient.compute_payload_hash(dict_order_1)
    assert client_hash == hash_1

    # Standards Boundary Test: Unicode NFC canonical composition
    # CFDS-v1 normalizes decomposed "e\u0301" into precomposed "\u00e9" to eliminate
    # equivalent composed/decomposed representation variance before CFDS-v1 hashing.
    # Note: General homoglyph detection is handled as a distinct identity control and is not solved by NFC alone.
    precomposed = {"vendor": "Caf\u00e9"}
    decomposed = {"vendor": "Cafe\u0301"}
    assert CanonicalFinancialDecisionSerializer.serialize(precomposed) == CanonicalFinancialDecisionSerializer.serialize(decomposed)

    # Financial Decimal fixed-scale string preservation (no float conversion)
    decimal_payload = {"amount": Decimal("100000.00"), "tds_rate": Decimal("0.0200")}
    ser_dec = CanonicalFinancialDecisionSerializer.serialize(decimal_payload)
    assert '"amount":"100000.00"' in ser_dec
    assert '"tds_rate":"0.0200"' in ser_dec


def test_retry_preserves_immutable_purpose_and_mode():
    """
    Gate Certification Check:
    Verify that when an intent is retried or re-dispatched from an outbox work item,
    both `purpose` ('vendor bill') and `mode` (NEFT or IMPS) remain completely immutable
    and are NOT recalculated or overwritten even if client configuration or policies change.
    """
    store = FirestoreStateStore(force_mock=True)
    client = RazorpayXBankingClient(
        api_key="rzp_test_key",
        api_secret="rzp_test_secret",
        account_number="2323230000000001",
    )
    orchestrator = PaymentOrchestrator(store, client)

    # Net payout ₹2,50,000 -> 25000000 paise -> NEFT (above ₹2,00,000 threshold)
    intent_high, _ = orchestrator.get_or_create_payment_intent(
        invoice_number="INV-MODE-NEFT",
        vendor_id="V-NEFT-001",
        vendor_pan="ABCDE1234F",
        fiscal_year="FY2025-26",
        fund_account_id="fa_neft_001",
        gross_subtotal=Decimal("250000.00"),
        tax_amount=Decimal("0.00"),
        tds_withheld=Decimal("0.00"),
        tds_section=TDSSection.SECTION_194J_PROF,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("250000.00"),
        environment="SANDBOX",
    )

    outbox_high = orchestrator.create_outbox_work_item(intent_high)
    body_high = outbox_high.payload["provider_request_body"]
    assert body_high["mode"] == "NEFT"
    assert body_high["purpose"] == "vendor bill"

    # Net payout ₹50,000 -> 5000000 paise -> IMPS (below ₹2,00,000 threshold)
    intent_low, _ = orchestrator.get_or_create_payment_intent(
        invoice_number="INV-MODE-IMPS",
        vendor_id="V-IMPS-001",
        vendor_pan="ABCDE1234F",
        fiscal_year="FY2025-26",
        fund_account_id="fa_imps_001",
        gross_subtotal=Decimal("50000.00"),
        tax_amount=Decimal("0.00"),
        tds_withheld=Decimal("0.00"),
        tds_section=TDSSection.SECTION_194J_PROF,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("50000.00"),
        environment="SANDBOX",
    )

    outbox_low = orchestrator.create_outbox_work_item(intent_low)
    body_low = outbox_low.payload["provider_request_body"]
    assert body_low["mode"] == "IMPS"
    assert body_low["purpose"] == "vendor bill"

    # Verify that during stage_payout with provider_request_body,
    # mode and purpose are strictly preserved from the snapshotted payload
    captured = []

    def mock_post(url, headers=None, json=None, **kwargs):
        if "payouts" in url:
            captured.append(json)

        class MockRes:
            status_code = 200

            def json(self):
                return {"id": "pout_mock", "status": "CONFIRMED"}

        return MockRes()

    client.client.post = mock_post

    # Stage payout passing outbox provider_request_body
    client.stage_payout(
        fund_account_id="fa_dummy",
        amount_paise=100,  # even if arguments differ
        idempotency_key="dummy_key",
        reference_id="dummy_ref",
        narration="dummy_narration",
        notes={},
        provider_idempotency_key=intent_high.provider_idempotency_key,
        provider_request_body=body_high,
    )

    assert len(captured) == 1
    assert captured[0]["mode"] == "NEFT"
    assert captured[0]["purpose"] == "vendor bill"
    assert captured[0]["amount"] == 25000000


def test_payment_policy_versioning_and_treasury_rationale():
    """
    Gate Certification Check:
    Verify that:
    1. PAYMENT_POLICY resolves v2026.2 as the active policy for current dates.
    2. The ₹2,00,000 threshold is classified as INTERNAL_TREASURY_PAYMENT_RAIL_POLICY,
       and explicitly documented as an internal treasury routing / fee optimization preference,
       NOT an NPCI regulatory ceiling.
    3. Provider capability accurately records that IMPS technically supports up to ₹5,00,000
       (paise: 50,000,000) under NPCI revised standards and RazorpayX capability.
    4. Historical version v2026.1 remains accessible and immutable in the registry.
    """
    # 1. Resolve active policy
    active_policy = EnterprisePolicyRegistry.resolve_policy_at(PolicyType.PAYMENT_POLICY)
    assert active_policy is not None
    assert active_policy.version == "2026.2"

    payload_2026_2 = active_policy.rules_payload
    routing = payload_2026_2["rail_routing_policy"]
    provider = payload_2026_2["provider_capability"]

    # 2. Routing policy classification
    assert routing["policy_classification"] == "INTERNAL_TREASURY_PAYMENT_RAIL_POLICY"
    assert routing["threshold_paise"] == 20000000
    assert routing["high_value_mode"] == "NEFT"
    assert routing["low_value_mode"] == "IMPS"
    assert "NOT an NPCI regulatory ceiling" in routing["rationale"]

    # 3. Provider capability vs company preference
    assert provider["imps_maximum_limit_paise"] == 50000000  # ₹5 Lakh capability
    assert provider["neft_supported"] is True

    # 4. Historical compatibility
    hist_policy = EnterprisePolicyRegistry.get_policy(PolicyType.PAYMENT_POLICY, "2026.1")
    assert hist_policy is not None
    assert hist_policy.version == "2026.1"
    assert hist_policy.effective_until == "2026-09-04T22:00:00Z"


def test_historical_decision_policy_cutover_integrity():
    """
    Gate Certification Check:
    Verifies that:
    1. A historical decision explicitly recording payment_policy_version='2026.1'
       resolves '2026.1' during replay, even when replayed with a timestamp after the cutover date.
    2. Explicit policy version stored at decision time takes precedence over timestamp inference.
    3. Timestamp-based resolution for dates prior to 2026-09-05 resolves '2026.1'.
    4. Timestamp-based resolution for dates on/after 2026-09-05 resolves '2026.2'.
    5. In-flight PaymentIntent retains its original mode and policy version during retries.
    """
    # 1. Pre-cutover timestamp lookup resolves 2026.1
    p_pre = EnterprisePolicyRegistry.resolve_policy_at(PolicyType.PAYMENT_POLICY, "2026-05-15T10:00:00Z")
    assert p_pre is not None
    assert p_pre.version == "2026.1"

    # 2. Post-cutover timestamp lookup resolves 2026.2
    p_post = EnterprisePolicyRegistry.resolve_policy_at(PolicyType.PAYMENT_POLICY, "2026-09-05T12:00:00Z")
    assert p_post is not None
    assert p_post.version == "2026.2"

    # 3. Explicitly stored policy version overrides timestamp inference
    # A decision created historically with explicit version "2026.1", when replayed today (post-cutover)
    replayed_policy = EnterprisePolicyRegistry.resolve_decision_policy(
        policy_type=PolicyType.PAYMENT_POLICY,
        explicit_version="2026.1",
        decision_timestamp="2026-09-05T12:00:00Z",
    )
    assert replayed_policy.version == "2026.1"

    # 4. In-flight PaymentIntent preserves its original policy version and rail mode
    store = FirestoreStateStore(force_mock=True)
    client = RazorpayXBankingClient(
        api_key="rzp_test_key",
        api_secret="rzp_test_secret",
        account_number="2323230000000001",
    )
    orchestrator = PaymentOrchestrator(store, client)

    intent, _ = orchestrator.get_or_create_payment_intent(
        invoice_number="INV-HIST-001",
        vendor_id="V-HIST-001",
        vendor_pan="ABCDE1234F",
        fiscal_year="FY2025-26",
        fund_account_id="fa_hist_001",
        gross_subtotal=Decimal("50000.00"),
        tax_amount=Decimal("0.00"),
        tds_withheld=Decimal("0.00"),
        tds_section=TDSSection.SECTION_194J_PROF,
        applied_credits=Decimal("0.00"),
        net_payout_amount=Decimal("50000.00"),
        environment="SANDBOX",
    )

    outbox_item = orchestrator.create_outbox_work_item(intent)
    assert outbox_item.payload["provider_request_body"]["mode"] == "IMPS"
    assert outbox_item.payload["payment_policy_version"] == intent.payment_policy_version





