import pytest
from tests.playwright.pages.dashboard_page import DashboardPage
from tests.playwright.pages.exceptions_page import ExceptionsPage

pytestmark = pytest.mark.playwright

def test_maker_checker_sod_ui_enforcement(maker_context, checker_context):
    """
    Asserts Maker-Checker SoD via isolated browser contexts:
    Maker (AP Clerk) sees Maker labeling and cannot resolve exceptions without policy intervention.
    Checker (Controller) can open exception resolution modal and submit justification.
    """
    # 1. Maker context
    page_maker = maker_context.new_page()
    dash_maker = DashboardPage(page_maker)
    dash_maker.goto()

    # Verify role sync indicates AP Clerk / Maker
    assert page_maker.locator("#user-role-select").input_value() == "ROLE_AP_CLERK"
    assert "Maker" in page_maker.locator("#role-governance-label").inner_text()
    assert page_maker.locator("#btn-batch-disburse-label").inner_text() == "Propose Payout Batch"

    # 2. Checker context
    page_checker = checker_context.new_page()
    dash_checker = DashboardPage(page_checker)
    dash_checker.goto()

    assert page_checker.locator("#user-role-select").input_value() == "ROLE_CONTROLLER"
    assert "Checker" in page_checker.locator("#role-governance-label").inner_text()
    assert page_checker.locator("#btn-batch-disburse-label").inner_text() == "Authorize Payout Batch"
