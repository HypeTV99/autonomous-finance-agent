from datetime import date
from decimal import Decimal
from firestore_store import FirestoreStateStore
from compliance_engine import HardenedStatutoryLedgerEngine
from tax_engine import StatutoryComplianceTaxEngine
from schemas import TDSSection

def test_firestore_ledger_and_decision_persistence():
    store = FirestoreStateStore()
    tax_res = StatutoryComplianceTaxEngine.compute_statutory_tax(
        Decimal("50000.00"), Decimal("9000.00"), TDSSection.SECTION_194C_COMPANY, "AAACA1234T", date(2026, 4, 15)
    )
    journal, challan = HardenedStatutoryLedgerEngine.generate_accounting_records(
        "INV-FS-001", "AAACA1234T", "2026-27", Decimal("50000.00"), Decimal("0.00"), tax_res, Decimal("9000.00")
    )
    
    store.persist_general_ledger(journal.model_dump(mode="json"), challan.model_dump(mode="json"))
    # Check journal persistence in mock store or live
    if store._is_mock:
        assert journal.transaction_id in store._mock_db["general_ledger_journals"]
    else:
        assert store.db.collection("general_ledger_journals").document(journal.transaction_id).get().exists
