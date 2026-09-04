from datetime import date
from decimal import Decimal
from tax_engine import StatutoryComplianceTaxEngine
from schemas import TDSSection, TaxFramework

def test_dual_act_boundary_transition():
    # 2026-03-31 -> ITA 1961
    res_old = StatutoryComplianceTaxEngine.compute_statutory_tax(
        subtotal_excluding_gst=Decimal("100000.00"),
        gst_amount=Decimal("18000.00"),
        nominated_section=TDSSection.SECTION_194J_TECH,
        vendor_pan="AAACA1234T",
        transaction_date=date(2026, 3, 31)
    )
    assert res_old.tax_framework == TaxFramework.INCOME_TAX_ACT_1961
    assert "Section 194J(1)(ba)" in res_old.statutory_provision

    # 2026-04-01 -> ITA 2025
    res_new = StatutoryComplianceTaxEngine.compute_statutory_tax(
        subtotal_excluding_gst=Decimal("100000.00"),
        gst_amount=Decimal("18000.00"),
        nominated_section=TDSSection.SECTION_194J_TECH,
        vendor_pan="AAACA1234T",
        transaction_date=date(2026, 4, 1)
    )
    assert res_new.tax_framework == TaxFramework.INCOME_TAX_ACT_2025
    assert "Section 393(1)" in res_new.statutory_provision

def test_section_197_certificate_and_fallback():
    cert_valid = {
        "is_active": True,
        "rate": Decimal("0.0300"),
        "valid_from": "2026-04-01",
        "valid_to": "2027-03-31",
        "section": "SECTION_194J_PROF"
    }
    # Valid certificate -> 3%
    res = StatutoryComplianceTaxEngine.compute_statutory_tax(
        Decimal("40000.00"), Decimal("7200.00"), TDSSection.SECTION_194J_PROF, "AAACA1234T", date(2026, 5, 1),
        sec_197_cert=cert_valid
    )
    assert res.tds_rate == Decimal("0.0300")
    assert res.tds_deducted == Decimal("1200.00")

    # Expired / Inactive certificate -> Standard 10%
    cert_expired = dict(cert_valid, is_active=False)
    res_fallback = StatutoryComplianceTaxEngine.compute_statutory_tax(
        Decimal("40000.00"), Decimal("7200.00"), TDSSection.SECTION_194J_PROF, "AAACA1234T", date(2026, 5, 1),
        sec_197_cert=cert_expired
    )
    assert res_fallback.tds_rate == Decimal("0.1000")
    assert res_fallback.tds_deducted == Decimal("4000.00")
