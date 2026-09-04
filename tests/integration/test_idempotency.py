import pytest
from starlette.testclient import TestClient
import main
import uuid

@pytest.fixture
def client():
    return TestClient(main.app)

def ensure_test_invoice():
    inv_num = "INV-IDEMP-999"
    test_inv = {
        "invoice_number": inv_num,
        "vendor_name": "Acme Industrial Tools",
        "vendor_id": "VEND-ACME-01",
        "gross_amount": 118000.0,
        "subtotal": 100000.0,
        "gst_amount": 18000.0,
        "tds_deducted": 2000.0,
        "net_payable": 116000.0,
        "status": "AUTO_APPROVED",
        "stage_7_status": "SCHEDULED",
        "payout_telemetry": {"utr": None, "payout_id": None}
    }
    history = main.load_decision_history()
    filtered = [d for d in history if d.get("invoice_number") != inv_num]
    main.GLOBAL_DECISION_HISTORY = [test_inv] + filtered
    main.save_decision_history()
    return inv_num

def test_payout_idempotency_backend_protection(client):
    """
    Asserts Level 3 Backend Idempotency:
    Repeating a disbursement request with the same X-Idempotency-Key
    returns the identical cached payout result without creating a duplicate payout.
    """
    inv_num = ensure_test_invoice()
    
    idempotency_key = f"idemp-test-{uuid.uuid4().hex}"
    headers = {
        "X-User-Role": "ROLE_CONTROLLER",
        "X-Idempotency-Key": idempotency_key
    }
    
    # First submission: should succeed and disburse
    resp1 = client.post(f"/api/v1/decisions/{inv_num}/disburse", headers=headers)
    assert resp1.status_code == 200, f"First disburse failed: {resp1.text}"
    data1 = resp1.json()
    utr1 = data1.get("bank_utr") or (data1.get("active_decision", {}).get("payout_telemetry", {}).get("utr"))
    assert utr1 is not None, "First response must contain bank UTR"
    
    # Second submission with identical idempotency key: should return cached idempotent response
    resp2 = client.post(f"/api/v1/decisions/{inv_num}/disburse", headers=headers)
    assert resp2.status_code == 200, f"Second disburse failed: {resp2.text}"
    data2 = resp2.json()
    utr2 = data2.get("bank_utr") or (data2.get("active_decision", {}).get("payout_telemetry", {}).get("utr"))
    
    # Must match the original UTR and indicate idempotent response
    assert utr1 == utr2, "Idempotent disburse must return identical UTR"
    assert "Idempotent response" in data2.get("message", "") or data2.get("status") == "SUCCESS"


def test_maker_checker_sod_enforcement(client):
    """
    Asserts Maker-Checker Segregation of Duties:
    AP Clerk (Maker) cannot execute wire disbursals and receives HTTP 403 Forbidden.
    """
    inv_num = ensure_test_invoice()
    headers = {
        "X-User-Role": "ROLE_AP_CLERK",
        "X-Idempotency-Key": f"idemp-clerk-{uuid.uuid4().hex}"
    }
    
    resp = client.post(f"/api/v1/decisions/{inv_num}/disburse", headers=headers)
    assert resp.status_code == 403, f"Expected 403 Forbidden for AP Clerk, got {resp.status_code}: {resp.text}"
    assert "Segregation of Duties" in resp.json().get("detail", "")
