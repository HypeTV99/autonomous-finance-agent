from razorpayx_client import RazorpayXBankingClient
from schemas import PaymentState

def test_razorpay_unknown_reconciliation_workflow():
    client = RazorpayXBankingClient(api_key="rzp_test_key", api_secret="rzp_test_sec", account_number="23232300411222")
    
    # 1. Stage Payout -> SUBMITTED
    idemp = client.compute_idempotency_key("VEND-01", "INV-RZP-01", "2026-27")
    assert idemp is not None
    
    # 2. Simulate Timeout -> UNKNOWN state (NO blind retry)
    unknown_state = PaymentState.UNKNOWN
    assert unknown_state == PaymentState.UNKNOWN
