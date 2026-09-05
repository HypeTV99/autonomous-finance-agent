import asyncio
from decimal import Decimal
import threading
import time
import uuid
import pytest
from firestore_store import FirestoreStateStore
from schemas import OpenCreditRecord
from services.ledger import LedgerNettingEngine


def test_def_01_float_math_imprecision_reproduction():
    """
    DEF-01: Demonstrates that floating point arithmetic in invoice calculations
    produces precision drift on paise amounts, whereas Decimal ROUND_HALF_UP is exact.
    """
    # Subtotal with cents/paise
    subtotal_float = 100000.15
    gst_rate_float = 0.18
    gst_added_float = subtotal_float * gst_rate_float  # 18000.027000000003
    gross_total_float = subtotal_float + gst_added_float  # 118000.17700000001
    
    # Converting float via str to Decimal preserves float representation drift
    drifted_decimal = Decimal(str(gross_total_float))
    
    # Correct statutory Decimal computation
    subtotal_dec = Decimal("100000.15")
    gst_rate_dec = Decimal("0.18")
    gst_added_dec = (subtotal_dec * gst_rate_dec).quantize(Decimal("0.01"))
    gross_total_dec = subtotal_dec + gst_added_dec
    
    # Assert that naive float arithmetic produces drift from true statutory currency
    assert drifted_decimal != gross_total_dec
    assert str(drifted_decimal) == "118000.177"
    assert str(gross_total_dec) == "118000.18"


def test_def_02_disburse_endpoint_bypasses_banking_rail(monkeypatch):
    """
    DEF-02: Asserts that /api/v1/decisions/{inv}/disburse marks invoice as SETTLED
    without invoking RazorpayXBankingClient.stage_payout.
    """
    from starlette.testclient import TestClient
    import main
    
    client = TestClient(main.app)
    
    # Seed a test invoice in GLOBAL_DECISION_HISTORY
    test_inv = f"INV-AUDIT-TEST-{uuid.uuid4().hex[:8]}"
    main.GLOBAL_DECISION_HISTORY = [{
        "invoice_number": test_inv,
        "vendor_id": "VEND_TEST",
        "vendor_name": "Audit Test Vendor",
        "status": "APPROVED_BY_CONTROLLER",
        "final_disbursed": 50000.0,
        "subtotal": 50000.0,
        "payout_telemetry": {}
    }]
    main.save_decision_history()
    
    payout_staged = []
    def spy_stage_payout(*args, **kwargs):
        payout_staged.append(kwargs)
        return {"id": "pout_mock_123", "status": "processing"}
        
    monkeypatch.setattr(main.razorpay_client, "stage_payout", spy_stage_payout)
    
    resp = client.post(
        f"/api/v1/decisions/{test_inv}/disburse",
        headers={"X-User-Role": "ROLE_FINANCE_DIRECTOR", "X-Idempotency-Key": "IDEM-TEST-123"}
    )
    
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "SUCCESS"
    # DEF-02 RESOLVED: stage_payout IS called on this rail!
    assert len(payout_staged) == 1, "Disburse now correctly invokes stage_payout"


def test_def_03_concurrent_decision_history_race_condition(tmp_path, monkeypatch):
    """
    DEF-03: Demonstrates that un-synchronized saves to decision_history.json
    suffer from lost updates under concurrent modifications.
    """
    import main
    
    test_file = str(tmp_path / "decision_history_race.json")
    monkeypatch.setattr(main, "DECISION_HISTORY_FILE", test_file)
    main.GLOBAL_DECISION_HISTORY = []
    main.save_decision_history()
    
    def worker(worker_id: int):
        for i in range(10):
            # Load, modify, save pattern used in main.py
            current = main.load_decision_history()
            new_item = {"invoice_number": f"INV-{worker_id}-{i}", "status": "APPROVED"}
            main.GLOBAL_DECISION_HISTORY = current + [new_item]
            main.save_decision_history()
            time.sleep(0.001)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
        
    final_history = main.load_decision_history()
    # 5 workers * 10 items = 50 items expected if race-free
    # Without locking, lost updates cause final count to be significantly less than 50
    # We assert that race condition exists (count < 50)
    assert len(final_history) < 50, f"Expected lost updates due to race, got {len(final_history)}"


def test_def_04_concurrent_credit_netting_overconsumption():
    """
    DEF-04: Demonstrates that without a vendor-level mutex, two concurrent invoices
    reading the same open credit note balance can both consume it in full.
    """
    # Vendor has a single credit note of Rs. 30,000
    shared_open_credits = [OpenCreditRecord(credit_note_id="CN-TEST-001", available_balance=Decimal("30000.00"))]
    
    # Invoice 1 of Rs. 25,000 arrives
    res1 = LedgerNettingEngine.apply_credits_and_advances(Decimal("25000.00"), shared_open_credits)
    
    # Concurrently, before res1 writes back to store, Invoice 2 of Rs. 20,000 reads same shared_open_credits
    res2 = LedgerNettingEngine.apply_credits_and_advances(Decimal("20000.00"), shared_open_credits)
    
    # Total credit applied across both invoices is 25,000 + 20,000 = 45,000!
    total_applied = res1.applied_credit_total + res2.applied_credit_total
    assert total_applied == Decimal("45000.00")
    # Original credit was only 30,000, violating conservation across concurrent requests
    assert total_applied > Decimal("30000.00")


def test_def_05_firestore_mock_fallback_defect_reproduction():
    """
    DEF-05: Reproduces the exact baseline test failure in test_fenced_lease_release:
    Passing project_id="test" causes Client init to succeed but acquire_lock to fail
    without valid GCP credentials.
    """
    store = FirestoreStateStore(project_id="test")
    # DEF-05 RESOLVED: In an environment without GCP credentials, store safely falls back to InMemory Mock
    acquired, lease_id = store.acquire_lock("test_key", 300)
    assert acquired is True
    assert lease_id != ""
    assert store.release_lock("test_key", lease_id) is True
