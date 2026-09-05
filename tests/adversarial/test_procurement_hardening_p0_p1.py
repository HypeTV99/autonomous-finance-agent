from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import uuid
import pytest

from firestore_store import FirestoreStateStore
from schemas import InvoiceLineItem, LineItemPOMatch
from services.po_matching import ThreeWayPOMatchingEngine
from services.po_registry import PoRegistry


@pytest.fixture(autouse=True)
def setup_teardown_procurement():
    """Isolate registry and in-memory caches between tests."""
    PoRegistry.reset()
    ThreeWayPOMatchingEngine.reset()
    yield
    PoRegistry.reset()
    ThreeWayPOMatchingEngine.reset()


@pytest.fixture
def store():
    return FirestoreStateStore()


def test_concurrent_po_allocation_competition(store):
    """
    INVARIANT: Cumulative PO allocations <= Authorized PO quantity.
    Adversarial scenario: 5 concurrent threads compete for the final 10 units of a 100-unit PO.
    Exactly one must succeed, 4 must be rejected, and total allocated must never exceed 100.
    """
    po_number = f"PO-CONCUR-{uuid.uuid4().hex[:6].upper()}"
    vendor_id = "VEND-CONCUR-01"
    sku = "IT-EQUIP"
    authorized_qty = Decimal("100.00")

    PoRegistry.register_purchase_order(
        vendor_id=vendor_id,
        po_number=po_number,
        authorized_ceiling=Decimal("500000.00"),
        rates={sku: Decimal("1000.00")},
        quantities={sku: authorized_qty}
    )

    # Initial invoice consumes 90 units
    init_inv = f"INV-INIT-{uuid.uuid4().hex[:6].upper()}"
    ok, rec, msg = store.atomic_allocate_procurement(
        invoice_number=init_inv,
        po_number=po_number,
        po_version=1,
        vendor_id=vendor_id,
        requested_items=[{"sku": sku, "quantity": Decimal("90.00"), "unit_price": Decimal("1000.00")}],
        po_limits={sku: authorized_qty}
    )
    assert ok is True, f"Initial allocation failed: {msg}"

    # 5 concurrent threads each try to allocate the remaining 10 units
    results = []

    def _compete(thread_idx: int):
        inv_num = f"INV-RACE-{thread_idx}-{uuid.uuid4().hex[:6].upper()}"
        success, record, error_msg = store.atomic_allocate_procurement(
            invoice_number=inv_num,
            po_number=po_number,
            po_version=1,
            vendor_id=vendor_id,
            requested_items=[{"sku": sku, "quantity": Decimal("10.00"), "unit_price": Decimal("1000.00")}],
            po_limits={sku: authorized_qty}
        )
        return success, error_msg

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(_compete, i) for i in range(5)]
        for f in futures:
            results.append(f.result())

    success_count = sum(1 for s, _ in results if s)
    failure_count = sum(1 for s, _ in results if not s)

    assert success_count == 1, f"Expected exactly 1 success, got {success_count}. Results: {results}"
    assert failure_count == 4, f"Expected exactly 4 failures, got {failure_count}."

    # Total allocated in store must be exactly 100.00
    totals = store.get_cumulative_po_allocations(po_number)
    assert totals[sku] == Decimal("100.00"), f"Expected exactly 100.00 allocated, found {totals[sku]}"


def test_concurrent_grn_allocation_competition(store):
    """
    INVARIANT: Cumulative GRN allocations <= Accepted GRN quantity.
    Adversarial scenario: PO has 200 units authorized, but GRN only accepts 100 units.
    10 concurrent threads compete for 20 units each. Exactly 5 must succeed (100 units total).
    """
    po_number = f"PO-GRNCONCUR-{uuid.uuid4().hex[:6].upper()}"
    grn_number = f"GRN-{uuid.uuid4().hex[:6].upper()}"
    vendor_id = "VEND-GRN-01"
    sku = "HARDWARE-SERVER"

    PoRegistry.register_purchase_order(
        vendor_id=vendor_id,
        po_number=po_number,
        authorized_ceiling=Decimal("1000000.00"),
        rates={sku: Decimal("5000.00")},
        quantities={sku: Decimal("200.00")}
    )

    PoRegistry.record_grn_receipt(
        grn_number=grn_number,
        po_number=po_number,
        vendor_id=vendor_id,
        received_quantities={sku: Decimal("120.00")},
        rejected_quantities={sku: Decimal("20.00")}  # Accepted = 100
    )

    grn_entry = PoRegistry.get_grn(grn_number)
    accepted_qty = grn_entry["accepted_quantities"][sku]
    assert accepted_qty == Decimal("100.00")

    # 10 concurrent threads try to allocate 20 units each
    results = []

    def _compete_grn(thread_idx: int):
        inv_num = f"INV-GRN-RACE-{thread_idx}-{uuid.uuid4().hex[:6].upper()}"
        success, record, error_msg = store.atomic_allocate_procurement(
            invoice_number=inv_num,
            po_number=po_number,
            po_version=1,
            vendor_id=vendor_id,
            requested_items=[{"sku": sku, "quantity": Decimal("20.00"), "unit_price": Decimal("5000.00")}],
            po_limits={sku: Decimal("200.00")},
            grn_number=grn_number,
            grn_version=1,
            grn_limits={sku: accepted_qty}
        )
        return success, error_msg

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_compete_grn, i) for i in range(10)]
        for f in futures:
            results.append(f.result())

    success_count = sum(1 for s, _ in results if s)
    failure_count = sum(1 for s, _ in results if not s)

    assert success_count == 5, f"Expected 5 successes for 100 units, got {success_count}. Results: {results}"
    assert failure_count == 5, f"Expected 5 rejections, got {failure_count}."

    grn_totals = store.get_cumulative_grn_allocations(grn_number)
    assert grn_totals[sku] == Decimal("100.00")


def test_partial_invoices_drawdown_cumulative_quantity(store):
    """
    Tests sequential partial invoices (30 + 40 + 30) drawing down a 100-unit PO/GRN.
    Verifies cumulative tracking after each partial delivery.
    """
    po_number = f"PO-PARTIAL-{uuid.uuid4().hex[:6].upper()}"
    grn_number = f"GRN-PARTIAL-{uuid.uuid4().hex[:6].upper()}"
    vendor_id = "VEND-PARTIAL-01"
    sku = "DEV-HOURS"

    PoRegistry.register_purchase_order(
        vendor_id=vendor_id,
        po_number=po_number,
        authorized_ceiling=Decimal("100000.00"),
        rates={sku: Decimal("1000.00")},
        quantities={sku: Decimal("100.00")}
    )
    PoRegistry.record_grn_receipt(
        grn_number=grn_number,
        po_number=po_number,
        vendor_id=vendor_id,
        received_quantities={sku: Decimal("100.00")}
    )

    # 1. First partial: 30 units
    inv1 = f"INV-P1-{uuid.uuid4().hex[:6]}"
    items1 = [InvoiceLineItem(sku=sku, description="Dev sprint 1", quantity=Decimal("30.00"), unit_price=Decimal("1000.00"), line_total=Decimal("30000.00"))]
    matches1, ok1, overage1 = ThreeWayPOMatchingEngine.evaluate_line_items(
        vendor_id=vendor_id,
        line_items=items1,
        po_number=po_number,
        grn_number=grn_number,
        store=store,
        invoice_number=inv1,
        auto_allocate=True
    )
    assert ok1 is True
    assert overage1 == Decimal("0.00")
    assert matches1[0].cumulative_allocated_quantity == Decimal("30.00")

    # 2. Second partial: 40 units
    inv2 = f"INV-P2-{uuid.uuid4().hex[:6]}"
    items2 = [InvoiceLineItem(sku=sku, description="Dev sprint 2", quantity=Decimal("40.00"), unit_price=Decimal("1000.00"), line_total=Decimal("40000.00"))]
    matches2, ok2, overage2 = ThreeWayPOMatchingEngine.evaluate_line_items(
        vendor_id=vendor_id,
        line_items=items2,
        po_number=po_number,
        grn_number=grn_number,
        store=store,
        invoice_number=inv2,
        auto_allocate=True
    )
    assert ok2 is True
    assert matches2[0].cumulative_allocated_quantity == Decimal("70.00")

    # 3. Third partial: 30 units (fills remaining capacity)
    inv3 = f"INV-P3-{uuid.uuid4().hex[:6]}"
    items3 = [InvoiceLineItem(sku=sku, description="Dev sprint 3", quantity=Decimal("30.00"), unit_price=Decimal("1000.00"), line_total=Decimal("30000.00"))]
    matches3, ok3, overage3 = ThreeWayPOMatchingEngine.evaluate_line_items(
        vendor_id=vendor_id,
        line_items=items3,
        po_number=po_number,
        grn_number=grn_number,
        store=store,
        invoice_number=inv3,
        auto_allocate=True
    )
    assert ok3 is True
    assert matches3[0].cumulative_allocated_quantity == Decimal("100.00")

    totals = store.get_cumulative_po_allocations(po_number)
    assert totals[sku] == Decimal("100.00")


def test_fourth_partial_invoice_exceeding_po_rejected(store):
    """
    Adversarial scenario: 100-unit PO is fully allocated by 3 partial invoices.
    A 4th invoice for 10 units (much smaller than the 100-unit PO line) arrives.
    Must be rejected for cumulative quantity violation.
    """
    po_number = f"PO-EXCEED-{uuid.uuid4().hex[:6].upper()}"
    vendor_id = "VEND-EXCEED-01"
    sku = "CONSULTING"

    PoRegistry.register_purchase_order(
        vendor_id=vendor_id,
        po_number=po_number,
        authorized_ceiling=Decimal("200000.00"),
        rates={sku: Decimal("1000.00")},
        quantities={sku: Decimal("100.00")}
    )

    # Allocate full 100 units
    inv_full = f"INV-FULL-{uuid.uuid4().hex[:6]}"
    ThreeWayPOMatchingEngine.evaluate_line_items(
        vendor_id=vendor_id,
        line_items=[InvoiceLineItem(sku=sku, description="Full delivery", quantity=Decimal("100.00"), unit_price=Decimal("1000.00"), line_total=Decimal("100000.00"))],
        po_number=po_number,
        store=store,
        invoice_number=inv_full,
        auto_allocate=True
    )

    # 4th invoice for just 10 units
    inv4 = f"INV-4TH-{uuid.uuid4().hex[:6]}"
    items4 = [InvoiceLineItem(sku=sku, description="Extra 10 hours", quantity=Decimal("10.00"), unit_price=Decimal("1000.00"), line_total=Decimal("10000.00"))]
    matches4, ok4, overage4 = ThreeWayPOMatchingEngine.evaluate_line_items(
        vendor_id=vendor_id,
        line_items=items4,
        po_number=po_number,
        store=store,
        invoice_number=inv4,
        auto_allocate=True
    )

    assert ok4 is False, "4th invoice must be rejected for cumulative PO quantity violation"
    assert matches4[0].is_quantity_compliant is False
    assert matches4[0].is_po_quantity_compliant is False
    assert matches4[0].cumulative_allocated_quantity == Decimal("110.00")

    # Store total remains unchanged at 100
    totals = store.get_cumulative_po_allocations(po_number)
    assert totals[sku] == Decimal("100.00")


def test_po_revision_capacity_amendment(store):
    """
    Tests PO revisions:
    1. PO v1 allows 100 units. Invoice 1 allocates 100 units (exhausting v1).
    2. Attempting Invoice 2 fails.
    3. PO amendment creates v2 with +50 units (total 150 units). Historical v1 revision preserved.
    4. Invoice 2 now succeeds under v2, allocating 50 units.
    5. Invoice 3 for another 10 units is rejected (150 limit reached).
    """
    po_number = f"PO-REV-{uuid.uuid4().hex[:6].upper()}"
    vendor_id = "VEND-REV-01"
    sku = "SECURITY-AUDIT"

    PoRegistry.register_purchase_order(
        vendor_id=vendor_id,
        po_number=po_number,
        authorized_ceiling=Decimal("100000.00"),
        rates={sku: Decimal("1000.00")},
        quantities={sku: Decimal("100.00")},
        po_version=1
    )

    # Invoice 1 allocates 100 units
    inv1 = f"INV-REV-1-{uuid.uuid4().hex[:6]}"
    ok1, rec1, msg1 = ThreeWayPOMatchingEngine.allocate_procurement(
        store=store,
        invoice_number=inv1,
        vendor_id=vendor_id,
        line_items=[InvoiceLineItem(sku=sku, description="Audit phase 1", quantity=Decimal("100.00"), unit_price=Decimal("1000.00"), line_total=Decimal("100000.00"))],
        po_number=po_number,
        po_version=1
    )
    assert ok1 is True
    assert rec1["po_version"] == 1

    # Invoice 2 attempts to allocate 50 units -> fails under v1
    inv2 = f"INV-REV-2-{uuid.uuid4().hex[:6]}"
    items2 = [InvoiceLineItem(sku=sku, description="Audit phase 2", quantity=Decimal("50.00"), unit_price=Decimal("1000.00"), line_total=Decimal("50000.00"))]
    ok2_fail, _, msg2_fail = ThreeWayPOMatchingEngine.allocate_procurement(
        store=store,
        invoice_number=inv2,
        vendor_id=vendor_id,
        line_items=items2,
        po_number=po_number,
        po_version=1
    )
    assert ok2_fail is False
    assert "Cumulative PO quantity exceeded" in msg2_fail

    # PO Amendment: add 50 units, incrementing version to v2
    amended = PoRegistry.amend_purchase_order(
        po_number=po_number,
        new_quantities={sku: Decimal("150.00")},
        new_ceiling=Decimal("150000.00"),
        reason="Scope expansion for penetration testing"
    )
    assert amended["version"] == 2
    assert len(amended["revisions"]) == 1
    assert amended["revisions"][0]["version"] == 1
    assert amended["revisions"][0]["authorized_quantities"][sku] == Decimal("100.00")

    # Invoice 2 now allocates successfully under v2
    ok2_pass, rec2, msg2_pass = ThreeWayPOMatchingEngine.allocate_procurement(
        store=store,
        invoice_number=inv2,
        vendor_id=vendor_id,
        line_items=items2,
        po_number=po_number,
        po_version=2
    )
    assert ok2_pass is True
    assert rec2["po_version"] == 2

    # Total allocated is now 150
    totals = store.get_cumulative_po_allocations(po_number)
    assert totals[sku] == Decimal("150.00")

    # Invoice 3 attempts to allocate another 10 units -> rejected
    inv3 = f"INV-REV-3-{uuid.uuid4().hex[:6]}"
    ok3, _, _ = ThreeWayPOMatchingEngine.allocate_procurement(
        store=store,
        invoice_number=inv3,
        vendor_id=vendor_id,
        line_items=[InvoiceLineItem(sku=sku, description="Extra work", quantity=Decimal("10.00"), unit_price=Decimal("1000.00"), line_total=Decimal("10000.00"))],
        po_number=po_number,
        po_version=2
    )
    assert ok3 is False


def test_rejected_goods_reduce_grn_allocation(store):
    """
    INVARIANT: Accepted quantity = received - rejected - returned.
    Vendor ships 100 units, but QA rejects 25 units.
    Accepted capacity is 75 units.
    Invoice 1 allocates 75 units (succeeds).
    Invoice 2 attempts 10 units (rejected).
    """
    po_number = f"PO-REJ-{uuid.uuid4().hex[:6].upper()}"
    grn_number = f"GRN-REJ-{uuid.uuid4().hex[:6].upper()}"
    vendor_id = "VEND-REJ-01"
    sku = "VALVES"

    PoRegistry.register_purchase_order(
        vendor_id=vendor_id,
        po_number=po_number,
        authorized_ceiling=Decimal("500000.00"),
        rates={sku: Decimal("500.00")},
        quantities={sku: Decimal("100.00")}
    )

    PoRegistry.record_grn_receipt(
        grn_number=grn_number,
        po_number=po_number,
        vendor_id=vendor_id,
        received_quantities={sku: Decimal("100.00")},
        rejected_quantities={sku: Decimal("25.00")}  # Accepted = 75
    )

    # Invoice 1: 75 units -> passes
    inv1 = f"INV-REJ-1-{uuid.uuid4().hex[:6]}"
    items1 = [InvoiceLineItem(sku=sku, description="75 accepted valves", quantity=Decimal("75.00"), unit_price=Decimal("500.00"), line_total=Decimal("37500.00"))]
    matches1, ok1, _ = ThreeWayPOMatchingEngine.evaluate_line_items(
        vendor_id=vendor_id,
        line_items=items1,
        po_number=po_number,
        grn_number=grn_number,
        store=store,
        invoice_number=inv1,
        auto_allocate=True
    )
    assert ok1 is True
    assert matches1[0].is_grn_quantity_compliant is True

    # Invoice 2: 10 units -> rejected because accepted capacity is 75, not 100
    inv2 = f"INV-REJ-2-{uuid.uuid4().hex[:6]}"
    items2 = [InvoiceLineItem(sku=sku, description="10 rejected valves attempt", quantity=Decimal("10.00"), unit_price=Decimal("500.00"), line_total=Decimal("5000.00"))]
    matches2, ok2, _ = ThreeWayPOMatchingEngine.evaluate_line_items(
        vendor_id=vendor_id,
        line_items=items2,
        po_number=po_number,
        grn_number=grn_number,
        store=store,
        invoice_number=inv2,
        auto_allocate=True
    )
    assert ok2 is False
    assert matches2[0].is_grn_quantity_compliant is False


def test_goods_return_releases_cumulative_capacity(store):
    """
    Tests that releasing an invoice allocation frees the capacity back to the PO/GRN pool.
    1. 100-unit PO is fully allocated by Invoice 1.
    2. Capacity is exhausted; new invoice fails.
    3. Invoice 1 is cancelled/rejected; allocation is released.
    4. New invoice can now successfully allocate the freed 100 units.
    """
    po_number = f"PO-REL-{uuid.uuid4().hex[:6].upper()}"
    vendor_id = "VEND-REL-01"
    sku = "MONITORS"

    PoRegistry.register_purchase_order(
        vendor_id=vendor_id,
        po_number=po_number,
        authorized_ceiling=Decimal("200000.00"),
        rates={sku: Decimal("2000.00")},
        quantities={sku: Decimal("100.00")}
    )

    inv1 = f"INV-REL-1-{uuid.uuid4().hex[:6]}"
    items1 = [InvoiceLineItem(sku=sku, description="100 monitors", quantity=Decimal("100.00"), unit_price=Decimal("2000.00"), line_total=Decimal("200000.00"))]
    ok1, _, _ = ThreeWayPOMatchingEngine.allocate_procurement(
        store=store,
        invoice_number=inv1,
        vendor_id=vendor_id,
        line_items=items1,
        po_number=po_number
    )
    assert ok1 is True
    assert store.get_cumulative_po_allocations(po_number)[sku] == Decimal("100.00")

    # New invoice blocked
    inv2 = f"INV-REL-2-{uuid.uuid4().hex[:6]}"
    ok2, _, _ = ThreeWayPOMatchingEngine.allocate_procurement(
        store=store,
        invoice_number=inv2,
        vendor_id=vendor_id,
        line_items=items1,
        po_number=po_number
    )
    assert ok2 is False

    # Release invoice 1
    released = ThreeWayPOMatchingEngine.release_procurement_allocation(store, inv1, po_number)
    assert released is True

    # Store cumulative allocations now reflect 0 active
    assert store.get_cumulative_po_allocations(po_number).get(sku, Decimal("0.00")) == Decimal("0.00")

    # Invoice 2 can now allocate successfully
    ok2_retry, rec2, msg2 = ThreeWayPOMatchingEngine.allocate_procurement(
        store=store,
        invoice_number=inv2,
        vendor_id=vendor_id,
        line_items=items1,
        po_number=po_number
    )
    assert ok2_retry is True
    assert store.get_cumulative_po_allocations(po_number)[sku] == Decimal("100.00")


def test_rate_tolerance_boundary_conditions():
    """
    INVARIANT: Deterministic price variance tolerance:
    - Base PO rate: ₹1000.00
    - <= 2.0% variance: Within tolerance
    - > 2.0% variance: Non-compliant unless petty rounding applies
    - Petty rounding: rupee diff <= ₹10.00 AND variance <= 5.0%
    - Micro-unit exploitation prevention: rate ₹1.00 billed at ₹10.00 (diff ₹9 <= ₹10, but 900% > 5%) is BLOCKED
    """
    vendor_id = "VEND-TOLERANCE-01"
    po_number = f"PO-TOL-{uuid.uuid4().hex[:6].upper()}"
    sku = "STANDARD-SERVICE"
    auth_rate = Decimal("1000.00")

    PoRegistry.register_purchase_order(
        vendor_id=vendor_id,
        po_number=po_number,
        authorized_ceiling=Decimal("500000.00"),
        rates={sku: auth_rate},
        quantities={sku: Decimal("100.00")}
    )

    # 1. 1.99% variance: ₹1019.90 -> PASS
    item_199 = [InvoiceLineItem(sku=sku, description="1.99% test", quantity=Decimal("10.00"), unit_price=Decimal("1019.90"), line_total=Decimal("10199.00"))]
    matches_199, ok_199, overage_199 = ThreeWayPOMatchingEngine.evaluate_line_items(vendor_id, item_199, po_number=po_number)
    assert ok_199 is True
    assert overage_199 == Decimal("0.00")
    assert matches_199[0].is_within_tolerance is True

    # 2. Exactly 2.00% variance: ₹1020.00 -> PASS
    item_200 = [InvoiceLineItem(sku=sku, description="2.00% test", quantity=Decimal("10.00"), unit_price=Decimal("1020.00"), line_total=Decimal("10200.00"))]
    matches_200, ok_200, overage_200 = ThreeWayPOMatchingEngine.evaluate_line_items(vendor_id, item_200, po_number=po_number)
    assert ok_200 is True
    assert overage_200 == Decimal("0.00")
    assert matches_200[0].is_within_tolerance is True

    # 3. 2.01% variance: ₹1020.10 -> FAIL (diff is ₹20.10, which exceeds ₹10.00 petty allowance)
    item_201 = [InvoiceLineItem(sku=sku, description="2.01% test", quantity=Decimal("10.00"), unit_price=Decimal("1020.10"), line_total=Decimal("10201.00"))]
    matches_201, ok_201, overage_201 = ThreeWayPOMatchingEngine.evaluate_line_items(vendor_id, item_201, po_number=po_number)
    assert ok_201 is False
    assert overage_201 == Decimal("201.00")  # (1020.10 - 1000) * 10
    assert matches_201[0].is_within_tolerance is False

    # 4. Petty rounding allowance: ₹100 rate billed at ₹103 (diff = ₹3.00, variance = 3.0% <= 5.0% cap) -> PASS
    sku_petty = "PETTY-ITEM"
    PoRegistry.amend_purchase_order(po_number=po_number, new_rates={sku_petty: Decimal("100.00")}, new_quantities={sku_petty: Decimal("100.00")})
    item_petty = [InvoiceLineItem(sku=sku_petty, description="Petty diff", quantity=Decimal("5.00"), unit_price=Decimal("103.00"), line_total=Decimal("515.00"))]
    matches_p, ok_p, overage_p = ThreeWayPOMatchingEngine.evaluate_line_items(vendor_id, item_petty, po_number=po_number)
    assert ok_p is True
    assert matches_p[0].is_within_tolerance is True
    assert overage_p == Decimal("0.00")

    # 5. Micro-unit rate exploitation: ₹1.00 rate billed at ₹10.00 (diff = ₹9.00 <= ₹10, but 900% variance > 5% cap) -> FAIL
    sku_micro = "MICRO-ITEM"
    PoRegistry.amend_purchase_order(po_number=po_number, new_rates={sku_micro: Decimal("1.00")}, new_quantities={sku_micro: Decimal("100.00")})
    item_micro = [InvoiceLineItem(sku=sku_micro, description="Exploit drift", quantity=Decimal("100.00"), unit_price=Decimal("10.00"), line_total=Decimal("1000.00"))]
    matches_m, ok_m, overage_m = ThreeWayPOMatchingEngine.evaluate_line_items(vendor_id, item_micro, po_number=po_number)
    assert ok_m is False
    assert matches_m[0].is_within_tolerance is False
    assert overage_m == Decimal("900.00")  # (10.00 - 1.00) * 100


def test_idempotent_allocation_redelivery(store):
    """
    Tests that duplicate allocation requests for the same invoice return the existing allocation idempotently
    without double-allocating quantity. Conflicting requests return a material conflict error.
    """
    po_number = f"PO-IDEMP-{uuid.uuid4().hex[:6].upper()}"
    vendor_id = "VEND-IDEMP-01"
    sku = "NETWORK-CABLES"
    inv_num = f"INV-IDEMP-{uuid.uuid4().hex[:6]}"

    PoRegistry.register_purchase_order(
        vendor_id=vendor_id,
        po_number=po_number,
        authorized_ceiling=Decimal("50000.00"),
        rates={sku: Decimal("50.00")},
        quantities={sku: Decimal("100.00")}
    )

    items = [{"sku": sku, "quantity": Decimal("40.00"), "unit_price": Decimal("50.00")}]

    # 1. Initial allocation
    ok1, rec1, msg1 = store.atomic_allocate_procurement(
        invoice_number=inv_num,
        po_number=po_number,
        po_version=1,
        vendor_id=vendor_id,
        requested_items=items,
        po_limits={sku: Decimal("100.00")}
    )
    assert ok1 is True
    assert rec1["allocation_id"] == f"ALLOC-{po_number}-{inv_num}"

    # 2. Duplicate redelivery
    ok2, rec2, msg2 = store.atomic_allocate_procurement(
        invoice_number=inv_num,
        po_number=po_number,
        po_version=1,
        vendor_id=vendor_id,
        requested_items=items,
        po_limits={sku: Decimal("100.00")}
    )
    assert ok2 is True
    assert "Idempotent" in msg2
    assert rec2["allocation_id"] == rec1["allocation_id"]

    # Cumulative allocated quantity must be 40, NOT 80
    totals = store.get_cumulative_po_allocations(po_number)
    assert totals[sku] == Decimal("40.00")

    # 3. Conflicting retry: different quantity (50 vs 40)
    conflicting_items = [{"sku": sku, "quantity": Decimal("50.00"), "unit_price": Decimal("50.00")}]
    ok3, rec3, msg3 = store.atomic_allocate_procurement(
        invoice_number=inv_num,
        po_number=po_number,
        po_version=1,
        vendor_id=vendor_id,
        requested_items=conflicting_items,
        po_limits={sku: Decimal("100.00")}
    )
    assert ok3 is False
    assert "Material conflict" in msg3


def test_intra_invoice_duplicate_sku_aggregation():
    """
    Tests intra-invoice cumulative tracking:
    An invoice contains two lines for the same SKU: Line 1 (60 units) + Line 2 (50 units) = 110 units.
    Authorized PO quantity is 100 units.
    Even though each line individually is <= 100, the invoice cumulative total is 110 > 100.
    Must be flagged non-compliant.
    """
    vendor_id = "VEND-INTRA-01"
    po_number = f"PO-INTRA-{uuid.uuid4().hex[:6].upper()}"
    sku = "SERVER-RAM"

    PoRegistry.register_purchase_order(
        vendor_id=vendor_id,
        po_number=po_number,
        authorized_ceiling=Decimal("200000.00"),
        rates={sku: Decimal("1000.00")},
        quantities={sku: Decimal("100.00")}
    )

    items = [
        InvoiceLineItem(sku=sku, description="RAM batch 1", quantity=Decimal("60.00"), unit_price=Decimal("1000.00"), line_total=Decimal("60000.00")),
        InvoiceLineItem(sku=sku, description="RAM batch 2", quantity=Decimal("50.00"), unit_price=Decimal("1000.00"), line_total=Decimal("50000.00"))
    ]

    matches, is_compliant, overage = ThreeWayPOMatchingEngine.evaluate_line_items(
        vendor_id=vendor_id,
        line_items=items,
        po_number=po_number
    )

    assert is_compliant is False, "Intra-invoice quantity 60 + 50 = 110 must exceed 100-unit PO"
    assert matches[0].is_quantity_compliant is True
    assert matches[0].cumulative_allocated_quantity == Decimal("60.00")

    assert matches[1].is_quantity_compliant is False
    assert matches[1].is_po_quantity_compliant is False
    assert matches[1].cumulative_allocated_quantity == Decimal("110.00")
