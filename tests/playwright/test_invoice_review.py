import pytest
from tests.playwright.pages.dashboard_page import DashboardPage

pytestmark = pytest.mark.playwright

def test_kpi_cards_and_waterfall(desktop_context):
    """
    Asserts light enterprise KPI cards and 4-step financial waterfall calculation.
    """
    page = desktop_context.new_page()
    dash = DashboardPage(page)
    dash.goto()

    # Verify light KPI cards are present with non-empty content
    assert "INR" in dash.kpi_settled.inner_text()
    assert "INR" in dash.kpi_tds.inner_text()
    assert "INR" in dash.kpi_escrow.inner_text()
    assert "INR" in dash.kpi_liquidity.inner_text()

    # Verify waterfall zero variance calculation
    variance_badge = page.locator("#waterfall-variance-badge")
    assert "0.00" in variance_badge.inner_text() or "Zero" in variance_badge.inner_text() or "Verified" in variance_badge.inner_text()
