from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = (ROOT / "static" / "dag.html").read_text(encoding="utf-8")
SUPPLIERS = (ROOT / "static" / "vendor_intel.html").read_text(encoding="utf-8")
AUDIT = (ROOT / "static" / "auditor_suite.html").read_text(encoding="utf-8")


def test_approved_is_not_presented_as_paid_without_bank_proof():
    assert "function isDecisionPaid(decision)" in DASHBOARD
    assert "decision.status === 'SETTLED' || decisionHasBankProof(decision)" in DASHBOARD
    assert "function isDecisionReady(decision)" in DASHBOARD
    assert "'APPROVED_BY_CONTROLLER'" in DASHBOARD


def test_dashboard_does_not_seed_financial_totals_or_dummy_batches():
    assert "const baselineSettled" not in DASHBOARD
    assert "baselineSettled - 108000.0" not in DASHBOARD
    assert "eligible = [{ gross_amount" not in DASHBOARD
    assert "Nothing ready to pay" in DASHBOARD


def test_frontend_uses_plain_language_and_discloses_planning_balance():
    for label in (
        "Paid to suppliers",
        "Tax to deposit",
        "GST held for verification",
        "Planning balance · not a live bank feed",
        "Ready to pay",
    ):
        assert label in DASHBOARD


def test_supplier_and_audit_pages_do_not_inject_fallback_records():
    assert "Always include Section 206AB Non-Filer demo partner" not in SUPPLIERS
    assert "AUDIT_DECISIONS = DEFAULT_AUDIT_DECISIONS" not in AUDIT


def test_amicro_motion_has_reduced_motion_support_on_all_pages():
    for page in (DASHBOARD, SUPPLIERS, AUDIT):
        assert "--amicro-ease: cubic-bezier(0.22, 1, 0.36, 1)" in page
        assert "prefers-reduced-motion: reduce" in page


def test_macos_visual_language_and_requested_mono_components_are_present():
    for page in (DASHBOARD, SUPPLIERS, AUDIT):
        assert "-apple-system" in page
        assert "backdrop-filter:blur" in page
    assert "mono-rounded-kpi" in DASHBOARD
    assert "mono-rounded-sankey" in DASHBOARD
    assert "t-digit-group" in DASHBOARD
    assert "t-tabs-pill" in DASHBOARD
    assert "Illustrative trend" not in DASHBOARD
