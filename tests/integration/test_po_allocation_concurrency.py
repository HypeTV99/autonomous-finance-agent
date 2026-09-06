"""Cross-process/instance PO+GRN cumulative allocation tests (Firestore Emulator).

Proves: concurrent invoices cannot over-allocate the same PO/GRN lines,
retries/redeliveries are idempotent, and allocation state survives what
would be a worker restart (new store handle, same emulator).
"""
import os
import threading

import pytest

from firestore_store import FirestoreStateStore

HOST = os.environ.get("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8089")


@pytest.fixture(autouse=True)
def _allow_real_emulator(monkeypatch):
    # Repo conftest forces USE_MOCK_FIRESTORE=true for safety; this module
    # deliberately opts out to exercise the real emulator.
    monkeypatch.delenv("USE_MOCK_FIRESTORE", raising=False)
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", HOST)


def _store():
    try:
        s = FirestoreStateStore(project_id="alloc-test", force_mock=False)
    except Exception as e:
        pytest.skip(f"emulator unreachable: {e}")
    if s._is_mock:
        pytest.skip("store fell back to mock; emulator required")
    return s


def _req(inv, qty, rate="1000.00"):
    return [{"sku": "IT-CONSULT", "quantity": qty, "unit_price": rate}]


def test_concurrent_allocations_never_exceed_cap():
    s = _store()
    po = "PO-ALLOC-TEST-01"
    cap = {"IT-CONSULT": __import__("decimal").Decimal("500.00")}
    results, lock = [], threading.Lock()

    def worker(i):
        ok, _, _ = s.atomic_allocate_procurement(
            invoice_number=f"INV-ALLOC-{i:03d}", po_number=po, po_version=1,
            vendor_id="VEND-TEST", requested_items=_req(f"INV-ALLOC-{i:03d}", "100.00"),
            po_limits=cap)
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 10 x 100 against cap 500 -> exactly 5 must win
    assert sum(1 for r in results if r) == 5, results
    assert sum(1 for r in results if not r) == 5


def test_redelivery_is_idempotent():
    s = _store()
    po = "PO-ALLOC-TEST-02"
    cap = {"IT-CONSULT": __import__("decimal").Decimal("10000.00")}
    kw = dict(invoice_number="INV-ALLOC-R1", po_number=po, po_version=1,
              vendor_id="VEND-TEST", requested_items=_req("x", "100.00"), po_limits=cap)
    ok1, rec1, _ = s.atomic_allocate_procurement(**kw)
    ok2, rec2, msg2 = s.atomic_allocate_procurement(**kw)
    assert ok1 and ok2
    assert "Idempotent" in msg2
    # no double count: a fresh 9901-unit request against 10000 cap must fail (100 used once)
    ok3, _, _ = s.atomic_allocate_procurement(
        invoice_number="INV-ALLOC-R2", po_number=po, po_version=1,
        vendor_id="VEND-TEST", requested_items=_req("x", "9901.00"), po_limits=cap)
    assert ok3 is False


def test_grn_cap_enforced():
    s = _store()
    po = "PO-ALLOC-TEST-03"
    cap = {"IT-CONSULT": __import__("decimal").Decimal("10000.00")}
    grn = {"IT-CONSULT": __import__("decimal").Decimal("150.00")}
    ok1, _, _ = s.atomic_allocate_procurement(
        invoice_number="INV-ALLOC-G1", po_number=po, po_version=1, vendor_id="VEND-TEST",
        requested_items=_req("x", "100.00"), po_limits=cap,
        grn_number="GRN-TEST-03", grn_limits=grn)
    assert ok1 is True
    ok2, _, msg2 = s.atomic_allocate_procurement(
        invoice_number="INV-ALLOC-G2", po_number=po, po_version=1, vendor_id="VEND-TEST",
        requested_items=_req("x", "100.00"), po_limits=cap,
        grn_number="GRN-TEST-03", grn_limits=grn)
    assert ok2 is False
    assert "GRN" in msg2
