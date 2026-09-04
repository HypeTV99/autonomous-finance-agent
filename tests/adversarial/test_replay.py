import concurrent.futures
from decimal import Decimal
from razorpayx_client import RazorpayXBankingClient

def test_payout_idempotency_fencing():
    client = RazorpayXBankingClient(api_key="rzp_test_key", api_secret="rzp_test_sec", account_number="23232300411222")
    results = []

    def _attempt_payout():
        # Compute exact business key
        idemp = client.compute_idempotency_key("VEND-001", "INV-REPLAY-001", "2026-27")
        return idemp

    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(_attempt_payout) for _ in range(100)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    # All 100 concurrent requests must resolve to the identical deterministic idempotency key
    assert len(set(results)) == 1
    assert len(results) == 100
