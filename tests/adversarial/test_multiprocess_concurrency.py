"""
tests/adversarial/test_multiprocess_concurrency.py
Adversarial Verification of True Cross-Process (Multi-Instance) Payment Safety.

Spawns separate OS processes (different PIDs and independent Python heaps)
sharing a simulated distributed persistence layer to prove:
1. No reliance on process-local memory or single-process locks.
2. Invariant: At most ONE external banking payout is dispatched.
"""

from decimal import Decimal
import multiprocessing
import os
import time
from typing import Any, Dict
import uuid

import pytest

from schemas import (
    PaymentInstruction,
    PaymentState,
    TDSSection,
)
from firestore_store import FirestoreStateStore
from services.payment_orchestrator import PaymentOrchestrator


def _multiprocess_worker_dispatch(
    worker_id: str,
    shared_db: Any,
    lock_backend: Any,
    payout_counter: Any,
    intent_dict: Dict[str, Any],
    result_queue: Any
):
    """
    Worker running in an isolated OS process.
    Has its own independent process heap, its own store, and its own process-local lock.
    """
    from razorpayx_client import RazorpayXBankingClient

    store = FirestoreStateStore(force_mock=True, lock_backend=lock_backend)
    store._mock_db = shared_db

    client = RazorpayXBankingClient("rzp_test_key", "rzp_test_secret", "2323230000000001")

    # Mock stage_payout to increment shared atomic counter
    def mock_stage_payout(*args, **kwargs):
        with payout_counter.get_lock():
            payout_counter.value += 1
        time.sleep(0.05)  # Simulate network latency
        return {"id": f"pout_mp_{worker_id}", "status": "processed", "utr": f"UTR-MP-{worker_id}"}

    client.stage_payout = mock_stage_payout

    orchestrator = PaymentOrchestrator(store, client)
    intent = PaymentInstruction(**intent_dict)

    try:
        res = orchestrator.dispatch_payment_intent(intent)
        result_queue.put((worker_id, "SUCCESS", res))
    except Exception as ex:
        result_queue.put((worker_id, "ERROR", str(ex)))


def test_true_cross_process_payment_concurrency():
    """
    Runs two actual independent OS processes (multiprocessing.Process)
    competing to dispatch the exact same payment intent.
    Proves that cross-instance safety does not rely on single-process memory.
    """
    ctx = multiprocessing.get_context("spawn")
    manager = ctx.Manager()

    # Shared persistent storage across processes
    shared_db = manager.dict({
        "distributed_locks": manager.dict(),
        "payment_intents": manager.dict(),
        "payment_outbox": manager.dict(),
        "webhook_events": manager.dict(),
        "state_transitions": manager.dict()
    })

    payout_counter = ctx.Value("i", 0)
    result_queue = ctx.Queue()
    datastore_lock = ctx.Lock()

    intent_data = {
        "instruction_id": f"INS-MP-{uuid.uuid4().hex[:6]}",
        "invoice_number": f"INV-MP-{uuid.uuid4().hex[:6]}",
        "vendor_id": "VEND-MP-01",
        "vendor_pan": "AAACB1234K",
        "fund_account_id": "fa_mp_01",
        "gross_subtotal": "50000.00",
        "tax_amount": "9000.00",
        "tds_withheld": "5000.00",
        "tds_section": "194J_PROF",
        "applied_credits_total": "0.00",
        "net_payout_amount": "54000.00",
        "payout_paise": 5400000,
        "idempotency_key": f"idemp_mp_{uuid.uuid4().hex[:8]}",
        "requires_zero_payout_hold": False,
        "status": "READY_FOR_SUBMISSION",
        "environment": "SANDBOX",
        "version": 1
    }

    # Spawn Process 1 and Process 2
    p1 = ctx.Process(
        target=_multiprocess_worker_dispatch,
        args=("proc_1", shared_db, datastore_lock, payout_counter, intent_data, result_queue)
    )
    p2 = ctx.Process(
        target=_multiprocess_worker_dispatch,
        args=("proc_2", shared_db, datastore_lock, payout_counter, intent_data, result_queue)
    )

    p1.start()
    p2.start()

    p1.join(timeout=10)
    p2.join(timeout=10)

    # Collect outcomes
    results = []
    while not result_queue.empty():
        results.append(result_queue.get())

    print("\nRESULTS FROM WORKERS:", results)
    # CRITICAL INVARIANT: Banking rail payout executed AT MOST ONCE
    assert payout_counter.value == 1, (
        f"Multi-process violation! Bank rail was called {payout_counter.value} times instead of 1."
    )

    # Verify that both processes terminated cleanly
    assert len(results) == 2
    # At least one process succeeded
    successes = [r for r in results if r[1] == "SUCCESS"]
    assert len(successes) >= 1
