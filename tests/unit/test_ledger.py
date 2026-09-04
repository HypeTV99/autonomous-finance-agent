from datetime import date
from decimal import Decimal
from compliance_engine import HardenedStatutoryLedgerEngine
from schemas import TDSSection
from tax_engine import StatutoryComplianceTaxEngine

def test_double_entry_balance_invariant():
    tax_res = StatutoryComplianceTaxEngine.compute_statutory_tax(
        Decimal("100000.00"), Decimal("18000.00"), TDSSection.SECTION_194J_TECH, "AAACA1234T", date(2026, 4, 15)
    )
    journal, challan = HardenedStatutoryLedgerEngine.generate_accounting_records(
        "INV-TEST-001", "AAACA1234T", "2026-27", Decimal("100000.00"), Decimal("0.00"), tax_res, Decimal("18000.00")
    )
    debits = sum(p.amount for p in journal.postings if p.entry_type.value == "DEBIT")
    credits = sum(p.amount for p in journal.postings if p.entry_type.value == "CREDIT")
    assert debits == credits
    assert debits == Decimal("118000.00")
