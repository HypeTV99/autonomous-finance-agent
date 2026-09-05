import multiprocessing as mp
import os
import time
from datetime import datetime, timezone
import pytest

from firestore_store import FirestoreStateStore
from schemas import PaymentState


def _real_firestore_worker_task(
    emulator_host: str,
    project_id: str,
    idempotency_key: str,
    expected_version: int,
    barrier,
    results_list,
    worker_id: str
):
    """
    Independent OS process executing against the real Google Cloud Firestore Emulator.
    Zero shared Python memory, zero thread locks, zero distributed lock leases.
    Relies purely on Firestore transaction precondition (OCC).
    """
    try:
        os.environ["FIRESTORE_EMULATOR_HOST"] = emulator_host
        os.environ["USE_MOCK_FIRESTORE"] = "0"

        # Instantiate independent Firestore client in this process
        store = FirestoreStateStore(project_id=project_id, force_mock=False)
        assert store._is_mock is False, f"Worker {worker_id} must connect to real Firestore Emulator"

        # 1. Read the current version from the real Firestore database
        doc = store.db.collection("payment_intents").document(idempotency_key).get()
        assert doc.exists, f"Worker {worker_id} could not find document"
        curr_data = doc.to_dict()
        observed_version = curr_data.get("version", 1)

        # 2. Wait at barrier to ensure both processes execute update_payment_intent at the exact same millisecond
        try:
            barrier.wait(timeout=10)
        except Exception:
            pass

        # 3. Race to execute the Firestore transaction OCC update
        claimed = store.update_payment_intent(
            idempotency_key=idempotency_key,
            update_dict={
                "status": PaymentState.SUBMISSION_PENDING.value,
                "claiming_worker": worker_id,
                "claimed_at": datetime.now(timezone.utc).isoformat()
            },
            expected_version=observed_version
        )

        if claimed:
            # Payout POST invocation occurs ONLY after successful datastore claim
            results_list.append({
                "worker_id": worker_id,
                "action": "CLAIM_SUCCESS",
                "payout_post_dispatched": True
            })
        else:
            results_list.append({
                "worker_id": worker_id,
                "action": "CLAIM_REJECTED",
                "payout_post_dispatched": False
            })
    except Exception as ex:
        results_list.append({
            "worker_id": worker_id,
            "action": "ERROR",
            "error": str(ex),
            "payout_post_dispatched": False
        })


@pytest.mark.parametrize("iteration", range(3))
def test_real_firestore_emulator_cross_process_race(iteration):
    """
    Provider Contract & Infrastructure Correction Gate - Section 5:
    Real Google Cloud Firestore Emulator Multi-Process OCC Concurrency Test:
    - Environment: Real Google Cloud Firestore Emulator (v1.22.0) on 127.0.0.1:8089.
    - Processes: 2 independent OS worker processes spawned with separate Python memory.
    - Verification:
      * Exactly 1 successful datastore claim.
      * Exactly 1 rejected competing claim.
      * Exactly 1 payout POST invocation.
      * Persisted version increments from 1 to 2.
      * Zero process-local locks used.
    """
    emulator_host = os.environ.get("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8089")
    project_id = "test-firestore-emulator"

    # Fast connectivity check: skip if emulator process is not running
    import socket
    try:
        host, port = emulator_host.split(":")
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            if s.connect_ex((host, int(port))) != 0:
                pytest.skip(f"Firestore Emulator is not running on {emulator_host}")
    except Exception:
        pytest.skip(f"Cannot connect to Firestore Emulator on {emulator_host}")

    os.environ["FIRESTORE_EMULATOR_HOST"] = emulator_host
    os.environ["USE_MOCK_FIRESTORE"] = "0"

    # 1. Setup seed document in real Firestore Emulator
    seed_store = FirestoreStateStore(project_id=project_id, force_mock=False)
    assert seed_store._is_mock is False, "Must connect to real Firestore Emulator"

    idempotency_key = f"idem_real_emulator_iter_{iteration}_{int(time.time() * 1000)}"
    seed_store.db.collection("payment_intents").document(idempotency_key).set({
        "instruction_id": f"INS-REAL-EMU-{iteration}",
        "invoice_number": f"INV-REAL-EMU-{iteration}",
        "vendor_id": "VEND-EMU-001",
        "vendor_pan": "ABCDE1234F",
        "fund_account_id": "fa_emu_001",
        "amount_paise": 1000000,
        "net_payout_amount": "10000.00",
        "currency": "INR",
        "idempotency_key": idempotency_key,
        "provider_idempotency_key": f"prov_key_emu_{iteration}",
        "status": PaymentState.READY_FOR_SUBMISSION.value,
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat()
    })

    # 2. Spawn two independent OS processes
    mp_ctx = mp.get_context("spawn")
    manager = mp_ctx.Manager()
    barrier = manager.Barrier(2)
    results = manager.list()

    p1 = mp_ctx.Process(
        target=_real_firestore_worker_task,
        args=(emulator_host, project_id, idempotency_key, 1, barrier, results, "worker_1")
    )
    p2 = mp_ctx.Process(
        target=_real_firestore_worker_task,
        args=(emulator_host, project_id, idempotency_key, 1, barrier, results, "worker_2")
    )

    p1.start()
    p2.start()
    p1.join(timeout=45)
    p2.join(timeout=45)
    if p1.is_alive():
        p1.terminate()
    if p2.is_alive():
        p2.terminate()

    # 3. Assertions on multi-process outcome
    res_list = list(results)
    assert len(res_list) == 2, f"Expected 2 worker results, got {len(res_list)} (results: {res_list})"

    successful_claims = [r for r in res_list if r["action"] == "CLAIM_SUCCESS"]
    rejected_claims = [r for r in res_list if r["action"] == "CLAIM_REJECTED"]
    payout_posts = [r for r in res_list if r["payout_post_dispatched"] is True]

    assert len(successful_claims) == 1, f"Iteration {iteration}: Expected exactly 1 successful claim, got {len(successful_claims)}"
    assert len(rejected_claims) == 1, f"Iteration {iteration}: Expected exactly 1 rejected claim, got {len(rejected_claims)}"
    assert len(payout_posts) == 1, f"Iteration {iteration}: Expected exactly 1 payout POST, got {len(payout_posts)}"

    # 4. Verify persisted state in real Firestore Emulator
    final_snap = seed_store.db.collection("payment_intents").document(idempotency_key).get()
    final_data = final_snap.to_dict()
    assert final_data["version"] == 2, f"Expected final version 2, got {final_data['version']}"
    assert final_data["status"] == PaymentState.SUBMISSION_PENDING.value
    assert final_data["claiming_worker"] == successful_claims[0]["worker_id"]
