import concurrent.futures
from decimal import Decimal
from compliance_engine import CanonicalFinancialDecisionSerializer

def test_concurrent_canonical_serialization_race_free():
    payload = {
        "vendor": "Concurrent Test Entity",
        "subtotal": Decimal("500000.00"),
        "tax": Decimal("90000.00"),
        "tax_rate": Decimal("0.0200")
    }
    
    def _run_serialization():
        return CanonicalFinancialDecisionSerializer.serialize(payload)

    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        futures = [executor.submit(_run_serialization) for _ in range(100)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    assert len(set(results)) == 1
    assert len(results) == 100
