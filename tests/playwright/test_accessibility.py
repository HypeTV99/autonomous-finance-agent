import pytest
from tests.playwright.pages.dashboard_page import DashboardPage

pytestmark = pytest.mark.playwright

def test_skip_link_and_landmarks(desktop_context):
    page = desktop_context.new_page()
    dash = DashboardPage(page)
    dash.goto()

    # Skip link exists and targets #main-content
    assert dash.skip_link.count() == 1
    assert dash.skip_link.get_attribute("href") == "#main-content"

    # Semantic landmarks present
    assert page.locator("main#main-content").count() == 1
    assert page.locator("aside").count() == 1
    assert page.locator("header").count() == 1

def test_no_positive_tabindex(desktop_context):
    page = desktop_context.new_page()
    dash = DashboardPage(page)
    dash.goto()

    # No elements should have positive tabindex values (anti-pattern that disrupts natural tab order)
    positive_tabindex_count = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('[tabindex]'))
            .filter(el => parseInt(el.getAttribute('tabindex'), 10) > 0).length;
    }""")
    assert positive_tabindex_count == 0, f"Found {positive_tabindex_count} elements with positive tabindex"

def test_dialog_accessibility_attributes(desktop_context):
    page = desktop_context.new_page()
    dash = DashboardPage(page)
    dash.goto()

    # Check batch disburse modal has accessible labeling
    batch_modal = page.locator("#batch-disburse-confirm-modal")
    assert batch_modal.get_attribute("aria-labelledby") == "batch-modal-title"
    assert batch_modal.get_attribute("aria-describedby") == "batch-modal-desc"

    # Close button has accessible name
    close_btn = page.locator("#batch-modal-close-btn")
    assert close_btn.get_attribute("aria-label") == "Close dialog"
