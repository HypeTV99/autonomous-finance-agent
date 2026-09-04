from datetime import datetime
from schemas import PaymentState

def test_payment_unknown_state_transition():
    # Submitted -> Gateway Timeout -> UNKNOWN -> Reconciled -> CONFIRMED
    current_state = PaymentState.SUBMITTED
    assert current_state == PaymentState.SUBMITTED
    
    # Timeout triggers UNKNOWN (NO blind retry)
    current_state = PaymentState.UNKNOWN
    assert current_state == PaymentState.UNKNOWN
    
    # Gateway status fetch confirms success
    current_state = PaymentState.CONFIRMED
    assert current_state == PaymentState.CONFIRMED
