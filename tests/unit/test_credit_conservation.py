import random
from decimal import Decimal
from compliance_engine import LedgerNettingEngine
from schemas import OpenCreditRecord

def test_credit_conservation_property_invariant():
    random.seed(42)
    for _ in range(25):
        # Generate random open credits
        credits = [
            OpenCreditRecord(credit_note_id=f"CN-{i}", available_balance=Decimal(str(random.randint(1000, 50000))))
            for i in range(random.randint(1, 5))
        ]
        orig_credit_sum = sum(c.available_balance for c in credits)
        payable = Decimal(str(random.randint(5000, 100000)))

        res = LedgerNettingEngine.apply_credits_and_advances(payable, credits)
        consumed = res.applied_credit_total
        remaining = sum(r.available_balance for r in res.updated_open_credit_records)

        # Invariant: Original Credits == Consumed + Remaining
        assert orig_credit_sum == consumed + remaining
        # Invariant: Final Net Payable == max(0, Payable - Consumed)
        assert res.net_taxable_subtotal == max(Decimal("0.00"), payable - consumed)
